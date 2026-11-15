"""Leakage-resistant scientific evaluation of MODIS->S-NPP count conversion.

Everything here re-analyses observations that earlier project iterations had already inspected
(Portugal 2012-2025, Uruguay/Greece/Chile/Zambia 2022-2025). Nested protocols remove *procedural*
leakage (no candidate is chosen with the year or region it is scored on), but they cannot make
previously inspected data an untouched holdout. Results are labelled exploratory accordingly.

Unit: H3 r7 active-cell days per UTC month (see METHOD.md). Target: S-NPP count. Not ground truth.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .series import monthly_series

REGIONS = {
    'portugal_mainland': {'country': 'Portugal', 'bbox': '-9.6,36.8,-6,42.2'},
    'uruguay': {'country': 'Uruguay', 'bbox': '-58.5,-35,-53,-30'},
    'greece': {'country': 'Greece'}, 'chile': {'country': 'Chile'}, 'zambia': {'country': 'Zambia'},
}
SOUTHERN = {'uruguay', 'chile', 'zambia'}
PROTOCOL_STATUS = 'exploratory_reanalysis_of_previously_inspected_data'


# ---------------------------------------------------------------- data

def load_monthly_pairs(regions=REGIONS, satellites=('T', 'A'), reference='N', first_year=2012, last_year=2025):
    """Monthly (MODIS, S-NPP) pairs. A month is used only if the archive supplies a value for both satellites
    (recorded counts, or archive-backed zeros from complete country files). Absent months are skipped, never zero."""
    pairs = []
    provenance = {}
    for region, scope in regions.items():
        series = monthly_series(**scope, processing_status='standard')
        provenance[region] = {'scope': scope, 'snapshot_id': series.get('snapshot_id')}
        values = defaultdict(dict)
        for r in series['items']:
            if r['satellite'] in (*satellites, reference) and first_year <= int(r['month'][:4]) <= last_year:
                values[r['month']][r['satellite']] = (r['active_cell_days'], r.get('archive_status', 'recorded'))
        for month, v in sorted(values.items()):
            if reference not in v:
                continue
            for sat in satellites:
                if sat in v:
                    pairs.append({'region': region, 'month': month, 'year': int(month[:4]), 'calendar_month': int(month[5:]),
                                  'satellite': sat, 'modis': float(v[sat][0]), 'viirs': float(v[reference][0]),
                                  'archive_zero': 'complete_country_file' in v[sat][1] or 'complete_country_file' in v[reference][1]})
    return pairs, provenance


def season(region, calendar_month):
    """Meteorological season, flipped for the southern hemisphere so 'summer' means local summer."""
    m = calendar_month if region not in SOUTHERN else (calendar_month + 5) % 12 + 1
    return {12: 'DJF', 1: 'DJF', 2: 'DJF', 3: 'MAM', 4: 'MAM', 5: 'MAM', 6: 'JJA', 7: 'JJA', 8: 'JJA'}.get(m, 'SON')


# ---------------------------------------------------------------- candidate models
# Each candidate: fit(train_rows) -> predict(rows) -> np.ndarray, nonnegative.

def _arr(rows, key):
    return np.array([r[key] for r in rows], dtype=float)


def fit_identity(train):
    return lambda rows: _arr(rows, 'modis')


def fit_global_ratio(train):
    m, v = _arr(train, 'modis').sum(), _arr(train, 'viirs').sum()
    ratio = v / m if m > 0 else np.nan
    return lambda rows: _arr(rows, 'modis') * ratio


def fit_seasonal_ratio(train, shrinkage=24):
    """Existing B1: region/calendar-month ratio shrunk toward the global ratio (unseen keys fall back to global)."""
    m, v = _arr(train, 'modis').sum(), _arr(train, 'viirs').sum()
    if m <= 0:
        return lambda rows: np.full(len(rows), np.nan)
    g = v / m
    groups = defaultdict(lambda: [0.0, 0.0])
    for r in train:
        groups[(r['region'], r['calendar_month'])][0] += r['modis']
        groups[(r['region'], r['calendar_month'])][1] += r['viirs']
    ratios = {k: (vv + shrinkage * g) / (mm + shrinkage) for k, (mm, vv) in groups.items()}
    return lambda rows: np.array([r['modis'] * ratios.get((r['region'], r['calendar_month']), g) for r in rows])


def fit_linear(train):
    x, y = _arr(train, 'modis'), _arr(train, 'viirs')
    b, a = np.polyfit(x, y, 1) if len(set(x)) > 1 else (np.nan, np.nan)
    return lambda rows: np.maximum(0, a + b * _arr(rows, 'modis'))


def fit_loglinear(train):
    """log1p(V) = a + b log1p(M); back-transformed with a smearing factor (Duan) estimated on training residuals."""
    x, y = np.log1p(_arr(train, 'modis')), np.log1p(_arr(train, 'viirs'))
    if len(set(x)) < 2:
        return lambda rows: np.full(len(rows), np.nan)
    b, a = np.polyfit(x, y, 1)
    smear = float(np.mean(np.exp(y - (a + b * x))))
    return lambda rows: np.maximum(0, smear * np.exp(a + b * np.log1p(_arr(rows, 'modis'))) - 1)


def fit_climatology(train):
    """VIIRS-only persistence baseline: mean S-NPP count for the same region/calendar month in earlier years.
    It ignores MODIS entirely, testing whether MODIS adds information. Undefined for unseen regions."""
    groups = defaultdict(list)
    for r in train:
        groups[(r['region'], r['calendar_month'])].append(r['viirs'])
    return lambda rows: np.array([np.mean(groups[(r['region'], r['calendar_month'])]) if groups.get((r['region'], r['calendar_month'])) else np.nan for r in rows])


CANDIDATES = {'raw': fit_identity, 'global_ratio': fit_global_ratio, 'seasonal_ratio_B1': fit_seasonal_ratio,
              'linear': fit_linear, 'loglinear': fit_loglinear, 'climatology': fit_climatology}
TRANSFERABLE = ('raw', 'global_ratio', 'seasonal_ratio_B1', 'linear', 'loglinear')  # climatology needs local history


def summarize_errors(rows, prediction):
    y = _arr(rows, 'viirs')
    e = prediction - y
    total = y.sum()
    return {'n': len(rows), 'mae': float(np.abs(e).mean()), 'signed_bias': float(e.mean()),
            'wape': float(np.abs(e).sum() / total) if total > 0 else None,
            'total_ratio_pred_over_obs': float(prediction.sum() / total) if total > 0 else None,
            'median_log_ratio': float(np.median(np.log((prediction + 1) / (y + 1))))}


# ---------------------------------------------------------------- nested temporal selection

def _inner_score(rows, candidate, before_year, min_train_years=3):
    """Mean MAE of one-year-ahead forecasts strictly before `before_year`, fit on earlier years only."""
    years = sorted({r['year'] for r in rows if r['year'] < before_year})
    errors, residuals = [], []
    for y in years:
        train = [r for r in rows if r['year'] < y]
        target = [r for r in rows if r['year'] == y]
        if len({r['year'] for r in train}) < min_train_years or not target:
            continue
        p = CANDIDATES[candidate](train)(target)
        if np.isnan(p).any():
            return None, []
        errors.append(np.abs(p - _arr(target, 'viirs')).mean())
        residuals.extend(zip(p, _arr(target, 'viirs')))
    return (float(np.mean(errors)) if errors else None), residuals


def nested_temporal(pairs, region='portugal_mainland', outer_from=2016, min_train_years=3, coverage=0.9):
    """Outer loop: forecast year Y. Inner loop: choose satellite x candidate by rolling-origin MAE on years < Y.
    The outer year is never seen during selection or interval calibration."""
    by_sat = {s: [r for r in pairs if r['region'] == region and r['satellite'] == s] for s in ('T', 'A')}
    years = sorted({r['year'] for r in by_sat['A']} & {r['year'] for r in by_sat['T']})
    folds = []
    for Y in [y for y in years if y >= outer_from]:
        inner = {}
        for sat, rows in by_sat.items():
            for cand in CANDIDATES:
                score, _ = _inner_score(rows, cand, Y, min_train_years)
                if score is not None:
                    inner[(sat, cand)] = score
        if not inner:
            continue
        sat, cand = min(inner, key=inner.get)
        rows = by_sat[sat]
        train = [r for r in rows if r['year'] < Y]
        target = [r for r in rows if r['year'] == Y]
        prediction = CANDIDATES[cand](train)(target)
        _, inner_residuals = _inner_score(rows, cand, Y, min_train_years)
        bands = conformal_bands(inner_residuals, prediction, coverage)
        y = _arr(target, 'viirs')
        fixed = {}
        for s2, rows2 in by_sat.items():
            t2 = [r for r in rows2 if r['year'] == Y]
            for c2 in CANDIDATES:
                p2 = CANDIDATES[c2]([r for r in rows2 if r['year'] < Y])(t2)
                if not np.isnan(p2).any():
                    fixed[f'{s2}:{c2}'] = float(np.abs(p2 - _arr(t2, 'viirs')).mean())
        folds.append({'outer_year': Y, 'selected': f'{sat}:{cand}', 'inner_scores': {f'{k[0]}:{k[1]}': v for k, v in inner.items()},
                      'outer_mae_selected': float(np.abs(prediction - y).mean()), 'outer_mae_fixed': fixed,
                      'band_coverage': {k: float(np.mean((y >= lo) & (y <= hi))) for k, (lo, hi) in bands.items()},
                      'band_mean_width': {k: float(np.mean(hi - lo)) for k, (lo, hi) in bands.items()},
                      'calibration_residuals': len(inner_residuals)})
    if not folds:
        return None
    keys = set.intersection(*[set(f['outer_mae_fixed']) for f in folds])
    return {'region': region, 'protocol': 'nested rolling origin; inner selection over satellite x candidate on years < outer year',
            'folds': folds, 'n_outer_folds': len(folds),
            'selection_frequency': {k: sum(f['selected'] == k for f in folds) for k in sorted({f['selected'] for f in folds})},
            'mean_outer_mae_selected': float(np.mean([f['outer_mae_selected'] for f in folds])),
            'mean_outer_mae_fixed': {k: float(np.mean([f['outer_mae_fixed'][k] for f in folds])) for k in sorted(keys)},
            'mean_band_coverage': {k: float(np.mean([f['band_coverage'][k] for f in folds])) for k in ('absolute', 'multiplicative')},
            'status': PROTOCOL_STATUS}


# ---------------------------------------------------------------- paired satellite comparison

def paired_satellite_comparison(pairs, candidate='seasonal_ratio_B1', min_train_years=3, seed=42, draws=5000):
    """For every region-year forecastable by rolling origin with both satellites, compare Aqua and Terra errors
    for the same candidate on the same months. Bootstrap resamples whole region-year folds."""
    folds = []
    for region in sorted({r['region'] for r in pairs}):
        sat_rows = {s: [r for r in pairs if r['region'] == region and r['satellite'] == s] for s in ('T', 'A')}
        common = {(r['month']) for r in sat_rows['T']} & {(r['month']) for r in sat_rows['A']}
        sat_rows = {s: [r for r in rs if r['month'] in common] for s, rs in sat_rows.items()}
        for Y in sorted({r['year'] for r in sat_rows['A']}):
            mae = {}
            for s, rows in sat_rows.items():
                train = [r for r in rows if r['year'] < Y]
                target = [r for r in rows if r['year'] == Y]
                if len({r['year'] for r in train}) < min_train_years or not target:
                    break
                p = CANDIDATES[candidate](train)(target)
                mae[s] = float(np.abs(p - _arr(target, 'viirs')).mean())
            if len(mae) == 2:
                folds.append({'region': region, 'year': Y, 'terra_mae': mae['T'], 'aqua_mae': mae['A'], 'difference_terra_minus_aqua': mae['T'] - mae['A']})
    if not folds:
        return None
    d = np.array([f['difference_terra_minus_aqua'] for f in folds])
    rng = np.random.default_rng(seed)
    boot = [float(rng.choice(d, len(d), replace=True).mean()) for _ in range(draws)]
    wins = int((d > 0).sum())
    # Scale-free paired effect: MAE differences across regions with 100x different activity are not commensurable.
    log_ratio = np.array([np.log(f['terra_mae'] / f['aqua_mae']) for f in folds if f['aqua_mae'] > 0 and f['terra_mae'] > 0])
    boot_lr = [float(np.median(rng.choice(log_ratio, len(log_ratio), replace=True))) for _ in range(draws)] if len(log_ratio) else []
    from scipy.stats import binomtest
    return {'candidate': candidate, 'folds': folds, 'n_folds': len(folds), 'aqua_better_folds': wins,
            'mean_difference': float(d.mean()), 'median_difference': float(np.median(d)),
            'bootstrap_mean_difference_95': np.quantile(boot, [.025, .975]).tolist(),
            'sign_test_p_two_sided': float(binomtest(wins, len(d)).pvalue),
            'median_terra_over_aqua_mae': float(np.exp(np.median(log_ratio))) if len(log_ratio) else None,
            'bootstrap_median_terra_over_aqua_mae_95': np.exp(np.quantile(boot_lr, [.025, .975])).tolist() if boot_lr else None,
            'note_on_mean': 'Mean count difference is dominated by the highest-activity region; use the median ratio and fold counts.',
            'caveat': 'Folds share training years and are serially dependent; the bootstrap and sign test treat folds as exchangeable and therefore overstate precision. Descriptive only.'}


# ---------------------------------------------------------------- geographic transfer

def leave_one_region_out(pairs, satellite='A', years=(2022, 2025), coverage=0.9):
    """Fit on all other regions' months in the common period, score the held-out region. Interval radius is
    calibrated by an inner leave-one-region-out among the training regions only (nested)."""
    rows = [r for r in pairs if r['satellite'] == satellite and years[0] <= r['year'] <= years[1]]
    regions = sorted({r['region'] for r in rows})
    out = {}
    for held in regions:
        train = [r for r in rows if r['region'] != held]
        test = [r for r in rows if r['region'] == held]
        if len({r['region'] for r in train}) < 2 or not test:
            continue
        result = {'months': len(test), 'train_regions': sorted({r['region'] for r in train}),
                  'domain': domain_check(train, test)}
        for cand in TRANSFERABLE:
            prediction = CANDIDATES[cand](train)(test)
            if np.isnan(prediction).any():
                continue
            inner_res = []
            for inner_held in sorted({r['region'] for r in train}):
                inner_train = [r for r in train if r['region'] != inner_held]
                inner_test = [r for r in train if r['region'] == inner_held]
                ip = CANDIDATES[cand](inner_train)(inner_test)
                if not np.isnan(ip).any():
                    inner_res.extend(zip(ip, _arr(inner_test, 'viirs')))
            bands = conformal_bands(inner_res, prediction, coverage)
            y = _arr(test, 'viirs')
            result[cand] = {**summarize_errors(test, prediction),
                            'by_activity': by_activity(test, prediction),
                            'band_coverage': {k: float(np.mean((y >= lo) & (y <= hi))) for k, (lo, hi) in bands.items()},
                            'band_median_width': {k: float(np.median(hi - lo)) for k, (lo, hi) in bands.items()}}
        out[held] = result
    return {'satellite': satellite, 'years': list(years), 'protocol': 'leave one region out, same calendar period; nested inner LORO for band calibration',
            'regions': out, 'status': PROTOCOL_STATUS,
            'caveat': 'Train and test share calendar years, so this isolates geographic transfer, not temporal transfer.'}


def domain_check(train, test):
    tm = _arr(train, 'modis')
    x = _arr(test, 'modis')
    lo, hi = float(tm.min()), float(tm.max())
    train_ratio = _arr(train, 'viirs').sum() / tm.sum() if tm.sum() else None
    test_ratio = _arr(test, 'viirs').sum() / x.sum() if x.sum() else None
    return {'train_modis_range': [lo, hi], 'test_modis_range': [float(x.min()), float(x.max())],
            'fraction_test_months_outside_train_range': float(np.mean((x < lo) | (x > hi))),
            'pooled_ratio_train': train_ratio, 'pooled_ratio_test_observed': test_ratio}


ACTIVITY_BINS = [(0, 10), (10, 100), (100, 1000), (1000, float('inf'))]


def by_activity(rows, prediction):
    """Errors stratified by observed MODIS activity level (input-side bins, available at prediction time)."""
    x = _arr(rows, 'modis')
    out = {}
    for lo, hi in ACTIVITY_BINS:
        idx = np.flatnonzero((x >= lo) & (x < hi))
        if len(idx):
            out[f'modis_{lo}_{hi if hi != float("inf") else "inf"}'] = summarize_errors([rows[i] for i in idx], prediction[idx])
    return out


# ---------------------------------------------------------------- intervals

def conformal_bands(residual_pairs, prediction, coverage=0.9):
    """Two split-conformal style residual bands from held-out (prediction, observed) pairs:
    absolute |y-p| (constant width) and multiplicative |log((y+1)/(p+1))| (width scales with activity).
    Exchangeability is NOT satisfied (temporal/spatial dependence); coverage must be checked empirically."""
    if not residual_pairs:
        nan = np.full(len(prediction), np.nan)
        return {'absolute': (nan, nan), 'multiplicative': (nan, nan)}
    p0 = np.array([a for a, _ in residual_pairs])
    y0 = np.array([b for _, b in residual_pairs])
    n = len(p0)
    level = min(1.0, np.ceil((n + 1) * coverage) / n)
    qa = float(np.quantile(np.abs(y0 - p0), level, method='higher'))
    qm = float(np.quantile(np.abs(np.log((y0 + 1) / (p0 + 1))), level, method='higher'))
    return {'absolute': (np.maximum(0, prediction - qa), prediction + qa),
            'multiplicative': (np.maximum(0, (prediction + 1) * np.exp(-qm) - 1), (prediction + 1) * np.exp(qm) - 1)}


def benchmark_interval_strata(pairs_csv, satellite_label, coverage=0.9):
    """Re-score the registered fixed-split benchmark (train<=2019, cal=2021, test 2022-2025) with absolute and
    multiplicative bands calibrated on 2021 only, stratified by region, season and activity."""
    from .science import fit_ratio, load_pairs, ratio_predict
    rows, parts, _ = load_pairs(pairs_csv)
    ratio = fit_ratio(parts['train'])
    cal, test = parts['calibration'], parts['test']
    bands = conformal_bands(list(zip(ratio_predict(ratio, cal), [r['viirs'] for r in cal])), ratio_predict(ratio, test), coverage)
    y = np.array([r['viirs'] for r in test])
    p = ratio_predict(ratio, test)
    strata = defaultdict(list)
    for i, r in enumerate(test):
        x = r['modis']
        act = next(f'modis_{lo}_{hi if hi != float("inf") else "inf"}' for lo, hi in ACTIVITY_BINS if lo <= x < hi)
        for key in ('all', f'region:{r["region"]}', f'season:{season(r["region"], int(r["month"][5:]))}', f'activity:{act}'):
            strata[key].append(i)
    out = {}
    for key, idx in sorted(strata.items()):
        idx = np.array(idx)
        out[key] = {'n': len(idx), 'mae': float(np.abs(p[idx] - y[idx]).mean())}
        for kind, (lo, hi) in bands.items():
            out[key][f'{kind}_coverage'] = float(np.mean((y[idx] >= lo[idx]) & (y[idx] <= hi[idx])))
            out[key][f'{kind}_median_width'] = float(np.median(hi[idx] - lo[idx]))
    return {'satellite': satellite_label, 'model': 'B1_shrunk_ratio', 'calibration_months': len(cal), 'nominal': coverage,
            'strata': out, 'caveat': 'One calibration year (12 months); small strata have very imprecise coverage estimates.'}


def bootstrap_block_sensitivity(pairs_csv, seed=42, draws=2000):
    """MAE 95% bootstrap interval for B1 on the fixed test split under different resampling units."""
    from .science import fit_ratio, load_pairs, ratio_predict
    _, parts, _ = load_pairs(pairs_csv)
    test = parts['test']
    err = np.abs(ratio_predict(fit_ratio(parts['train']), test) - np.array([r['viirs'] for r in test]))
    units = {'year (both regions)': [r['month'][:4] for r in test],
             'region-year': [r['region'] + r['month'][:4] for r in test],
             'region-quarter': [r['region'] + r['month'][:4] + str((int(r['month'][5:]) - 1) // 3) for r in test],
             'month (iid, ignores dependence)': [r['region'] + r['month'] for r in test]}
    rng = np.random.default_rng(seed)
    out = {}
    for name, labels in units.items():
        labels = np.array(labels)
        blocks = [np.flatnonzero(labels == b) for b in np.unique(labels)]
        boot = [float(err[np.concatenate([blocks[i] for i in rng.integers(0, len(blocks), len(blocks))])].mean()) for _ in range(draws)]
        lo, hi = np.quantile(boot, [.025, .975])
        out[name] = {'blocks': len(blocks), 'interval_95': [float(lo), float(hi)], 'width': float(hi - lo)}
    return {'point_mae': float(err.mean()), 'units': out,
            'interpretation': 'Smaller blocks give narrower intervals only because they ignore seasonal and inter-annual dependence; with four test years no unit gives a reliable interval.'}


# ---------------------------------------------------------------- activity-dependent ratio

def ratio_by_activity(pairs, satellite='A'):
    out = {}
    for region in sorted({r['region'] for r in pairs}):
        rows = [r for r in pairs if r['region'] == region and r['satellite'] == satellite and r['year'] >= 2022]
        out[region] = {}
        for lo, hi in ACTIVITY_BINS:
            sel = [r for r in rows if lo <= r['modis'] < hi]
            m = sum(r['modis'] for r in sel)
            out[region][f'modis_{lo}_{hi if hi != float("inf") else "inf"}'] = {'months': len(sel), 'pooled_ratio': (sum(r['viirs'] for r in sel) / m) if m else None}
    return out


def run_all(output=Path('artifacts/science-eval.json'), pilot_pairs=Path('artifacts/pilot-pairs.csv'), pilot_pairs_aqua=Path('artifacts/pilot-pairs-A.csv')):
    pairs, provenance = load_monthly_pairs()
    digest = hashlib.sha256(json.dumps(pairs, sort_keys=True).encode()).hexdigest()
    report = {'created_at': datetime.now(timezone.utc).isoformat(), 'status': PROTOCOL_STATUS,
              'pairs_sha256': digest, 'n_pairs': len(pairs), 'provenance': provenance,
              'months_by_region_satellite': {f'{reg}:{s}': sum(1 for r in pairs if r['region'] == reg and r['satellite'] == s) for reg in REGIONS for s in ('T', 'A')},
              'nested_temporal_portugal': nested_temporal(pairs),
              'paired_satellite_B1': paired_satellite_comparison(pairs),
              'paired_satellite_loglinear': paired_satellite_comparison(pairs, 'loglinear'),
              'loro_aqua': leave_one_region_out(pairs, 'A'), 'loro_terra': leave_one_region_out(pairs, 'T'),
              'ratio_by_activity_aqua': ratio_by_activity(pairs, 'A'),
              'rolling_band_aqua': rolling_band_evaluation(pairs, 'A'), 'rolling_band_terra': rolling_band_evaluation(pairs, 'T'),
              'interval_strata': {lab: benchmark_interval_strata(p, lab) for lab, p in (('T', pilot_pairs), ('A', pilot_pairs_aqua)) if Path(p).exists()},
              'bootstrap_block_sensitivity': {lab: bootstrap_block_sensitivity(p) for lab, p in (('T', pilot_pairs), ('A', pilot_pairs_aqua)) if Path(p).exists()}}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


# ---------------------------------------------------------------- out-of-sample band evaluation

BAND_METHODS = ('absolute', 'normalized_sqrt', 'multiplicative')


def _band(kind, cal_pred, cal_obs, prediction, coverage=0.9):
    n = len(cal_pred)
    level = min(1.0, np.ceil((n + 1) * coverage) / n)
    if kind == 'absolute':
        q = np.quantile(np.abs(cal_obs - cal_pred), level, method='higher')
        return np.maximum(0, prediction - q), prediction + q
    if kind == 'normalized_sqrt':  # |y-p|/sqrt(p+1): width grows like a Poisson-type standard deviation
        q = np.quantile(np.abs(cal_obs - cal_pred) / np.sqrt(cal_pred + 1), level, method='higher')
        s = np.sqrt(prediction + 1)
        return np.maximum(0, prediction - q * s), prediction + q * s
    q = np.quantile(np.abs(np.log((cal_obs + 1) / (cal_pred + 1))), level, method='higher')
    return np.maximum(0, (prediction + 1) * np.exp(-q) - 1), (prediction + 1) * np.exp(q) - 1


def _activity_label(x):
    return next(f'modis_{lo}_{hi if hi != float("inf") else "inf"}' for lo, hi in ACTIVITY_BINS if lo <= x < hi)


def rolling_band_evaluation(pairs, satellite='A', candidate='seasonal_ratio_B1', fit_region='portugal_mainland',
                            first_test_year=2016, coverage=0.9):
    """Out-of-sample test of residual-band methods and of the 'withhold above calibration range' rule.
    Each fold: fit on fit_region years < Y-1, calibrate on fit_region year Y-1 (12 months), score year Y in
    fit_region (temporal) and in every other region (temporal + geographic). Nothing from year Y is used to fit,
    calibrate or choose the rule; the rule and band shapes were defined before this evaluation was run on these folds,
    but the data had been inspected earlier (exploratory)."""
    rows = [r for r in pairs if r['satellite'] == satellite]
    home = [r for r in rows if r['region'] == fit_region]
    records = []
    for Y in sorted({r['year'] for r in home}):
        if Y < first_test_year:
            continue
        train = [r for r in home if r['year'] < Y - 1]
        cal = [r for r in home if r['year'] == Y - 1]
        if len({r['year'] for r in train}) < 3 or len(cal) < 12:
            continue
        model = CANDIDATES[candidate](train)
        cp, co = model(cal), _arr(cal, 'viirs')
        cal_max = float(_arr(cal, 'modis').max())
        target = [r for r in rows if r['year'] == Y]
        if not target:
            continue
        p, y = model(target), _arr(target, 'viirs')
        bands = {k: _band(k, cp, co, p, coverage) for k in BAND_METHODS}
        for i, r in enumerate(target):
            records.append({'year': Y, 'region': r['region'], 'scope': 'temporal' if r['region'] == fit_region else 'temporal+geographic',
                            'activity': _activity_label(r['modis']), 'above_calibration_range': bool(r['modis'] > cal_max),
                            **{f'covered_{k}': bool(lo[i] <= y[i] <= hi[i]) for k, (lo, hi) in bands.items()},
                            **{f'width_{k}': float(hi[i] - lo[i]) for k, (lo, hi) in bands.items()}})

    def summarize(sel):
        if not sel:
            return None
        out = {'months': len(sel), 'share_above_calibration_range': float(np.mean([r['above_calibration_range'] for r in sel]))}
        for k in BAND_METHODS:
            shown = [r for r in sel if not r['above_calibration_range']]
            out[k] = {'coverage_all': float(np.mean([r[f'covered_{k}'] for r in sel])),
                      'coverage_when_shown_under_rule': float(np.mean([r[f'covered_{k}'] for r in shown])) if shown else None,
                      'coverage_withheld': float(np.mean([r[f'covered_{k}'] for r in sel if r['above_calibration_range']])) if len(shown) < len(sel) else None,
                      'median_width': float(np.median([r[f'width_{k}'] for r in sel]))}
        return out
    strata = {'all_temporal': [r for r in records if r['scope'] == 'temporal'],
              'all_geographic': [r for r in records if r['scope'] != 'temporal']}
    for r in records:
        strata.setdefault(f"{r['scope']}|{r['activity']}", []).append(r)
        strata.setdefault(f"region|{r['region']}", []).append(r)
    return {'satellite': satellite, 'candidate': candidate, 'fit_region': fit_region, 'nominal': coverage,
            'protocol': 'rolling: fit < Y-1, calibrate Y-1 (12 months), score Y', 'status': PROTOCOL_STATUS,
            'n_folds': len({r['year'] for r in records}), 'strata': {k: summarize(v) for k, v in sorted(strata.items())},
            'caveat': 'Months within a fold share one calibration year and are dependent; coverage proportions are descriptive.'}
