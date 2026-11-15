"""Pinned pilot recipe: Portugal mainland temporal holdout, Uruguay spatial holdout."""
import csv
from pathlib import Path

from .science import benchmark
from .series import monthly_series

SCOPES={'portugal_mainland':{'country':'Portugal','bbox':'-9.6,36.8,-6,42.2'},
        'uruguay':{'country':'Uruguay','bbox':'-58.5,-35,-53,-30'}}


def prepare_pilot(output=Path('artifacts/pilot-pairs.csv'),modis='T'):
    if modis not in {'T','A'}:
        raise ValueError('MODIS input satellite must be T (Terra) or A (Aqua)')
    pairs=[]
    for region,scope in SCOPES.items():
        series=monthly_series(**scope,processing_status='standard')
        grouped={}
        for r in series['items']:
            if r['satellite'] not in {modis,'N'}:continue
            year=int(r['month'][:4])
            if year<2012 or year>2025 or (region=='uruguay' and year<2022):continue
            grouped.setdefault(r['month'],{})[r['satellite']]=r
        for month,values in sorted(grouped.items()):
            if set(values)!={modis,'N'}:continue
            year=int(month[:4])
            split='train' if year<=2019 else 'validation' if year==2020 else 'calibration' if year==2021 else 'test'
            pairs.append({'region':region,**scope,'month':month,'modis':values[modis]['active_cell_days'],'viirs':values['N']['active_cell_days'],
                          'split':split,'reference_satellite':'N','modis_satellite':modis,'processing_status':'standard','source_manifest':series['snapshot_id']})
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    if not pairs:raise ValueError('No historical pilot pairs; acquire the indexed country archives first')
    with output.open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(pairs[0]));writer.writeheader();writer.writerows(pairs)
    return output


def run_pilot(modis='T'):
    suffix='' if modis=='T' else f'-{modis}'
    path=prepare_pilot(Path(f'artifacts/pilot-pairs{suffix}.csv'),modis=modis)
    return benchmark(path,Path(f'artifacts/pilot-benchmark{suffix}.json'))


TRANSFER_SCOPES={'greece':{'country':'Greece'},'chile':{'country':'Chile'},'zambia':{'country':'Zambia'}}


def transfer_evaluation(modis='A',years=(2022,2025),output=None):
    """Score the already-registered model on regions never used for fitting, selection or calibration.
    No refitting happens here. Regions are whole countries (no bbox); estimates are extrapolations by design
    and are evaluated only to measure transfer error against the fixed S-NPP reference."""
    import json
    from .science import metrics, predict_reference, registered_model
    model = registered_model(modis)
    if not model:
        raise ValueError('register a benchmark for this MODIS input first (run-pilot)')
    report = {'modis_satellite': modis, 'model_id': model['model_id'], 'selected_model': model['selected_model'],
              'refit': False, 'regions': {}, 'status': 'transfer_to_unseen_regions_vs_sensor_reference_not_ground_truth'}
    for region, scope in TRANSFER_SCOPES.items():
        items = monthly_series(**scope, processing_status='standard')['items']
        grouped = {}
        for r in items:
            if r['satellite'] in {modis, 'N'} and years[0] <= int(r['month'][:4]) <= years[1]:
                grouped.setdefault(r['month'], {})[r['satellite']] = r['active_cell_days']
        rows = [{'month': m, 'region': region, 'modis': v[modis], 'viirs': v['N']} for m, v in sorted(grouped.items()) if set(v) == {modis, 'N'}]
        if len(rows) < 12:
            report['regions'][region] = {'status': 'insufficient_months', 'months': len(rows)}
            continue
        estimate = predict_reference([{'month': r['month'], 'active_cell_days': r['modis']} for r in rows], region, 'N', modis, 'standard')
        import numpy as np
        prediction = np.array([i['estimate'] for i in estimate['items']])
        report['regions'][region] = {'months': len(rows), 'status': 'extrapolated_unseen_region',
                                     'B0_raw': metrics(rows, np.array([r['modis'] for r in rows], dtype=float)),
                                     'registered_model': metrics(rows, prediction), 'total_viirs': sum(r['viirs'] for r in rows)}
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report
