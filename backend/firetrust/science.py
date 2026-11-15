"""Monthly count harmonization with whole-year splits and explicit uncertainty limits."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import TweedieRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .ingestion import root

SPLITS = ('train', 'validation', 'calibration', 'test')
REQUIRED = {'region', 'month', 'modis', 'viirs', 'split', 'reference_satellite', 'modis_satellite', 'processing_status', 'source_manifest'}


def load_pairs(path):
    rows = list(csv.DictReader(Path(path).read_text(encoding='utf-8-sig').splitlines()))
    if not rows or not REQUIRED.issubset(rows[0]):
        raise ValueError('paired CSV requires ' + ','.join(sorted(REQUIRED)))
    seen = set()
    for row in rows:
        datetime.strptime(row['month'], '%Y-%m')
        if row['split'] not in SPLITS or not row['source_manifest'].strip() or not row['region'].strip():
            raise ValueError('valid split, region and source_manifest required')
        if row['processing_status'] not in {'standard', 'nrt'}:
            raise ValueError('processing_status must be standard or nrt')
        row['modis'], row['viirs'] = float(row['modis']), float(row['viirs'])
        if not all(np.isfinite(row[k]) and row[k] >= 0 and row[k].is_integer() for k in ('modis', 'viirs')):
            raise ValueError('active-cell-day counts must be finite nonnegative integers')
        key = (row['region'], row['month'])
        if key in seen:
            raise ValueError('duplicate region/month; evaluate satellites and processing modes separately')
        seen.add(key)
    for key in ('reference_satellite', 'modis_satellite', 'processing_status'):
        if len({r[key] for r in rows}) != 1:
            raise ValueError(f'fix one {key} per benchmark run')
    partitions = {s: [r for r in rows if r['split'] == s] for s in SPLITS}
    years = {s: {int(r['month'][:4]) for r in part} for s, part in partitions.items()}
    for s, part in partitions.items():
        if len(part) < 12:
            raise ValueError(f'{s} requires at least twelve monthly pairs')
    for a, b in zip(SPLITS, SPLITS[1:]):
        if max(years[a]) >= min(years[b]):
            raise ValueError('split leakage: use strictly chronological, disjoint whole years')
    if len(years['train']) < 2:
        raise ValueError('training requires at least two whole years')
    # A split cannot conceal omitted months as zero. Every region/year must be supplied explicitly.
    region_year = defaultdict(set)
    for r in rows:
        region_year[(r['region'], r['month'][:4])].add(r['month'][5:])
    if any(len(months) != 12 for months in region_year.values()):
        raise ValueError('incomplete region/year; do not fill missing archive months with inferred zeros')
    return rows, partitions, years


def feature_rows(rows):
    return np.array([[np.log1p(r['modis']), np.sin(2 * np.pi * int(r['month'][5:]) / 12),
                      np.cos(2 * np.pi * int(r['month'][5:]) / 12), r['region']] for r in rows], dtype=object)


def fit_ratio(rows, shrinkage=24):
    total_m, total_v = sum(r['modis'] for r in rows), sum(r['viirs'] for r in rows)
    if total_m <= 0:
        raise ValueError('ratio baseline cannot be calibrated without MODIS activity')
    global_ratio = total_v / total_m
    groups = defaultdict(list)
    for r in rows:
        groups[(r['region'], r['month'][5:])].append(r)
    ratios = {}
    for (region, month), members in groups.items():
        m, v = sum(r['modis'] for r in members), sum(r['viirs'] for r in members)
        ratios[f'{region}|{month}'] = (v + shrinkage * global_ratio) / (m + shrinkage)
    return {'global': global_ratio, 'ratios': ratios, 'shrinkage_pseudocount': shrinkage}


def ratio_predict(model, rows):
    return np.array([r['modis'] * model['ratios'].get(f"{r['region']}|{r['month'][5:]}", model['global']) for r in rows])


def metrics(rows, prediction, lower=None, upper=None):
    y = np.array([r['viirs'] for r in rows])
    error = prediction - y
    denominator = float(np.abs(y).sum())
    groups = defaultdict(list)
    for i, row in enumerate(rows):
        groups[(row['region'], row['month'][:4])].append(i)
    peak_matches = []
    for indices in groups.values():
        observed = [i for i in indices if y[i] == max(y[indices])]
        estimated = [i for i in indices if prediction[i] == max(prediction[indices])]
        peak_matches.append(bool(set(observed) & set(estimated)))
    output = {'mae': float(mean_absolute_error(y, prediction)),
              'wape': float(np.abs(error).sum() / denominator) if denominator > 0 else None,
              'signed_bias': float(error.mean()), 'peak_month_concordance': float(np.mean(peak_matches)),
              'annual_total_bias': {f'{region}|{year}': float(error[idx].sum()) for (region, year), idx in groups.items()}}
    if lower is not None:
        output.update(empirical_interval_coverage=float(np.mean((y >= lower) & (y <= upper))),
                      mean_interval_width=float(np.mean(upper - lower)))
    return output


def fit_loglinear(rows):
    """B3: log1p(V) = a + b*log1p(M), Duan smearing for back-transformation. Captures the activity-dependent
    VIIRS/MODIS ratio (ratio falls as activity rises) that a single multiplicative ratio cannot."""
    x = np.log1p(np.array([r['modis'] for r in rows], dtype=float))
    y = np.log1p(np.array([r['viirs'] for r in rows], dtype=float))
    if len(set(x)) < 2:
        raise ValueError('log-linear calibration requires varying MODIS activity')
    b, a = np.polyfit(x, y, 1)
    return {'intercept': float(a), 'slope': float(b), 'smearing': float(np.mean(np.exp(y - (a + b * x))))}


def loglinear_predict(model, rows):
    x = np.log1p(np.array([r['modis'] for r in rows], dtype=float))
    return np.maximum(0, model['smearing'] * np.exp(model['intercept'] + model['slope'] * x) - 1)


def rolling_origin(rows, min_train_years=3):
    """Expanding-window temporal evaluation of B0/B1. Each fold fits on whole years strictly before the
    forecast year, so no future information is used and no single selection year decides the result.
    Only regions with at least min_train_years of earlier data contribute; others are not evaluated."""
    years = sorted({int(r['month'][:4]) for r in rows})
    folds = []
    for year in years:
        for region in sorted({r['region'] for r in rows}):
            earlier = [r for r in rows if int(r['month'][:4]) < year and r['region'] == region]
            target = [r for r in rows if int(r['month'][:4]) == year and r['region'] == region]
            if len({int(r['month'][:4]) for r in earlier}) < min_train_years or not target or sum(r['modis'] for r in earlier) <= 0:
                continue
            ratio = fit_ratio(earlier)
            y = np.array([r['viirs'] for r in target])
            folds.append({'region': region, 'year': year, 'train_years': len({int(r['month'][:4]) for r in earlier}),
                          'B0_mae': float(np.abs(np.array([r['modis'] for r in target]) - y).mean()),
                          'B1_mae': float(np.abs(ratio_predict(ratio, target) - y).mean()),
                          'B1_wape': float(np.abs(ratio_predict(ratio, target) - y).sum() / y.sum()) if y.sum() > 0 else None})
    if not folds:
        return None
    return {'protocol': 'expanding window; fit on all earlier whole years of the same region, forecast one year',
            'min_train_years': min_train_years, 'folds': folds, 'n_folds': len(folds),
            'B0_mean_mae': float(np.mean([f['B0_mae'] for f in folds])), 'B1_mean_mae': float(np.mean([f['B1_mae'] for f in folds])),
            'B1_beats_B0_folds': int(sum(f['B1_mae'] < f['B0_mae'] for f in folds))}


def benchmark(path: Path, output: Path, seed=42):
    rows, partitions, years = load_pairs(path)
    train = partitions['train']
    ratio = fit_ratio(train)
    transform = ColumnTransformer([('numeric', StandardScaler(), [0, 1, 2]),
                                   ('region', OneHotEncoder(handle_unknown='ignore', sparse_output=False), [3])])
    tweedie = make_pipeline(transform, TweedieRegressor(power=1.5, alpha=1.0, link='log', max_iter=3000))
    tweedie.fit(feature_rows(train), np.array([r['viirs'] for r in train]))
    loglinear = fit_loglinear(train)
    predictors = {'B0_raw_modis': lambda rs: np.array([r['modis'] for r in rs]),
                  'B1_shrunk_ratio': lambda rs: ratio_predict(ratio, rs),
                  'B2_tweedie': lambda rs: np.maximum(0, tweedie.predict(feature_rows(rs))),
                  'B3_loglinear': lambda rs: loglinear_predict(loglinear, rs)}
    validation = {name: metrics(partitions['validation'], predict(partitions['validation'])) for name, predict in predictors.items()}
    # Pre-specified rule, unchanged: smallest selection-year (validation split) MAE among fitted candidates.
    selected = min(('B1_shrunk_ratio', 'B2_tweedie', 'B3_loglinear'), key=lambda name: validation[name]['mae'])
    rng = np.random.default_rng(seed)
    results, radii = {}, {}
    for name, predict in predictors.items():
        calibration = partitions['calibration']
        residual = np.abs(predict(calibration) - np.array([r['viirs'] for r in calibration]))
        q = min(1.0, np.ceil((len(residual) + 1) * .9) / len(residual))
        radius = float(np.quantile(residual, q, method='higher'))
        radii[name] = radius
        test = partitions['test']
        p = predict(test)
        result = metrics(test, p, np.maximum(0, p - radius), p + radius)
        # Domain of applicability: the constant residual band under-covers when activity exceeds the calibration
        # year's maximum MODIS input (absolute errors grow with activity). Below the range the constant band is
        # conservative, so only the upper bound withholds. Out-of-sample evidence: experiments.rolling_band_evaluation.
        cal_lo, cal_hi = min(r['modis'] for r in calibration), max(r['modis'] for r in calibration)
        inside = np.array([r['modis'] <= cal_hi for r in test])
        y_test = np.array([r['viirs'] for r in test])
        result['band_within_calibration_activity'] = {
            'calibration_modis_range': [cal_lo, cal_hi], 'months_with_band': int(inside.sum()), 'months_band_withheld': int((~inside).sum()),
            'coverage_where_band_shown': float(np.mean(np.abs(y_test[inside] - p[inside]) <= radius)) if inside.any() else None,
            'coverage_where_band_withheld': float(np.mean(np.abs(y_test[~inside] - p[~inside]) <= radius)) if (~inside).any() else None}
        event_years = np.array([int(r['month'][:4]) for r in test])
        block_ids = np.unique(event_years)
        bootstrap_mae = []
        for _ in range(500):
            indices = np.concatenate([np.flatnonzero(event_years == y) for y in rng.choice(block_ids, len(block_ids), replace=True)])
            bootstrap_mae.append(float(np.mean(np.abs(p[indices] - np.array([test[i]['viirs'] for i in indices])))))
        result['year_block_bootstrap_mae_95_interval'] = np.quantile(bootstrap_mae, [.025, .975]).tolist() if len(block_ids) >= 3 else None
        result['test_year_blocks'] = len(block_ids)
        # More conservative resampling unit (region-year): still few blocks; see experiments.bootstrap_block_sensitivity.
        region_year = np.array([r['region'] + r['month'][:4] for r in test])
        ry_blocks = [np.flatnonzero(region_year == b) for b in np.unique(region_year)]
        ry_boot = [float(np.mean(np.abs(p[idx] - y_test[idx]))) for idx in
                   (np.concatenate([ry_blocks[i] for i in rng.integers(0, len(ry_blocks), len(ry_blocks))]) for _ in range(500))]
        result['region_year_block_bootstrap_mae_95_interval'] = np.quantile(ry_boot, [.025, .975]).tolist() if len(ry_blocks) >= 3 else None
        result['region_year_blocks'] = len(ry_blocks)
        result['by_region'] = {region: metrics([r for r in test if r['region'] == region], p[[i for i, r in enumerate(test) if r['region'] == region]], np.maximum(0,p[[i for i,r in enumerate(test) if r['region']==region]]-radius), p[[i for i,r in enumerate(test) if r['region']==region]]+radius) for region in sorted({r['region'] for r in test})}
        results[name] = result
    held_out_regions = sorted({r['region'] for r in partitions['test']} - {r['region'] for r in train})
    report = {'model_id': hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16],
              'dataset_sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest(),
              'created_at': datetime.now(timezone.utc).isoformat(), 'seed': seed,
              'target': 'VIIRS-reference H3 r7 active_cell_days per UTC month',
              'reference_satellite': rows[0]['reference_satellite'], 'modis_satellite': rows[0]['modis_satellite'],
              'processing_status': rows[0]['processing_status'], 'region_scopes': {r['region']:{'bbox':r.get('bbox'),'country':r.get('country')} for r in rows}, 'years': {s: sorted(y) for s, y in years.items()},
              'partition_sizes': {s: len(p) for s, p in partitions.items()},
              'validation': validation, 'test': results, 'selected_model': selected,
              'rolling_origin': rolling_origin(rows),
              'geographically_held_out_regions': held_out_regions,
              'independent_ground_validation': 'not_performed',
              'limitations': ['Sensor-reference agreement is not ground truth validation.',
                             'Calibration residual bands have no guaranteed coverage under temporal or spatial dependence.',
                             'Year-block confidence intervals require at least three test years and remain unstable with few blocks.',
                             'No biome covariates or cloud/overpass denominators supplied.',
                             'Paired count provenance and archive completeness must be independently audited.',
                             'Pre-reference and unseen-region conversions are extrapolations.']}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    registry = root() / 'models' / report['model_id']
    registry.mkdir(parents=True, exist_ok=True)
    joblib.dump(tweedie, registry / 'tweedie.joblib')
    configuration = {**report, 'ratio': ratio, 'loglinear': loglinear, 'radii': radii, 'train_regions': sorted({r['region'] for r in train}),
                     'modis_range': [min(r['modis'] for r in train), max(r['modis'] for r in train)],
                     'calibration_modis_range': [min(r['modis'] for r in partitions['calibration']), max(r['modis'] for r in partitions['calibration'])]}
    (registry / 'report.json').write_text(json.dumps(configuration, indent=2), encoding='utf-8')
    (root() / 'models' / 'latest.json').write_text(json.dumps({'model_id': report['model_id']}), encoding='utf-8')
    by_input = root() / 'models' / 'by_modis_satellite.json'
    registry_map = json.loads(by_input.read_text(encoding='utf-8')) if by_input.exists() else {}
    registry_map[report['modis_satellite']] = report['model_id']
    by_input.write_text(json.dumps(registry_map), encoding='utf-8')
    return report


def registered_model(modis_satellite=None):
    pointer = root() / 'models' / 'latest.json'
    by_input = root() / 'models' / 'by_modis_satellite.json'
    if modis_satellite and by_input.exists():
        mapped = json.loads(by_input.read_text(encoding='utf-8')).get(modis_satellite)
        if mapped:
            return json.loads((pointer.parent / mapped / 'report.json').read_text(encoding='utf-8'))
    if not pointer.exists():
        return None
    model_id = json.loads(pointer.read_text(encoding='utf-8'))['model_id']
    return json.loads((pointer.parent / model_id / 'report.json').read_text(encoding='utf-8'))


def predict_reference(rows, region, reference_satellite, modis_satellite, processing_status, bbox=None, country=None):
    model = registered_model(modis_satellite)
    if not model:
        return {'status': 'unavailable', 'reason': 'No historical calibration and held-out benchmark has been registered.', 'items': []}
    for key, value in [('reference_satellite', reference_satellite), ('modis_satellite', modis_satellite), ('processing_status', processing_status)]:
        if model[key] != value:
            return {'status': 'unavailable', 'reason': f'Registered model uses a different {key}.', 'items': []}
    scope=model.get('region_scopes',{}).get(region)
    if scope and (scope.get('country') != country or scope.get('bbox') != bbox):
        return {'status':'unavailable','reason':'Selected area differs from the registered regional scope.','items':[]}
    input_rows = [{'month': r['month'], 'modis': r['active_cell_days'], 'region': region} for r in rows]
    if not input_rows:
        return {'status': 'unavailable', 'reason': 'No MODIS observations in selection.', 'items': []}
    selected = model['selected_model']
    if selected == 'B3_loglinear':
        prediction = loglinear_predict(model['loglinear'], input_rows)
    elif selected == 'B1_shrunk_ratio':
        prediction = ratio_predict(model['ratio'], input_rows)
    else:
        pipeline = joblib.load(root() / 'models' / model['model_id'] / 'tweedie.joblib')
        prediction = pipeline.predict(feature_rows(input_rows))
    radius = model['radii'][selected]
    output = []
    for row, value in zip(input_rows, prediction):
        extrapolated = region not in model['train_regions'] or not model['modis_range'][0] <= row['modis'] <= model['modis_range'][1] or int(row['month'][:4]) < min(model['years']['train'])
        cal = model.get('calibration_modis_range')
        outside_calibration = bool(cal) and row['modis'] > cal[1]
        banded = not extrapolated and not outside_calibration
        output.append({'month': row['month'], 'estimate': float(value), 'lower': max(0, float(value) - radius) if banded else None, 'upper': float(value) + radius if banded else None,
                       'interval_status': 'unavailable_extrapolation' if extrapolated else 'unavailable_outside_calibration_activity' if outside_calibration else 'empirical_calibration_band',
                       'model_status': 'extrapolated' if extrapolated else 'low_support', 'coverage_status': 'unknown', 'model_id': model['model_id']})
    limitations = list(model['limitations'])
    if region not in model['train_regions']:
        limitations.append('Unseen-region estimates: in every evaluated transfer region (Greece, Chile, Zambia, 2022-2025) the '
                           'registered models under-predicted the S-NPP reference (negative bias); treat these estimates as likely low. '
                           'Residual bands are not provided because out-of-sample band coverage in other regions was well below nominal.')
    return {'status': 'available', 'items': output, 'model_id': model['model_id'], 'method': selected, 'limitations': limitations,
            'target': 'S-NPP-reference active-cell days (agreement with another satellite, not true fire activity)'}
