import csv

import numpy as np
import pytest

from firetrust.science import benchmark,fit_ratio,load_pairs,metrics,predict_reference,ratio_predict


def synthetic_pairs(path):
    # Deterministic engineering fixture, never scientific validation data.
    rows=[]
    for year in range(2012,2019):
        split='train' if year<2014 else 'validation' if year==2014 else 'calibration' if year==2015 else 'test'
        for month in range(1,13):
            rows.append(dict(region='fixture',month=f'{year}-{month:02d}',modis=month+year%3,viirs=2*(month+year%3),split=split,reference_satellite='N',modis_satellite='T',processing_status='standard',source_manifest='synthetic-test-only'))
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    return rows


def test_count_models_and_registry_run_on_engineering_fixture(tmp_path):
    path=tmp_path/'synthetic.csv';synthetic_pairs(path)
    report=benchmark(path,tmp_path/'report.json')
    assert report['selected_model'] in {'B1_shrunk_ratio','B2_tweedie'}
    assert report['test']['B1_shrunk_ratio']['mae']<1e-8
    assert report['geographically_held_out_regions']==[]
    assert report['independent_ground_validation']=='not_performed'
    assert len(report['test']['B1_shrunk_ratio']['year_block_bootstrap_mae_95_interval'])==2
    prediction=predict_reference([{'month':'2018-01','active_cell_days':5}],'fixture','N','T','standard')
    assert prediction['items'][0]['lower']>=0 and prediction['items'][0]['estimate']>=0
    assert predict_reference([],'fixture','N20','T','standard')['status']=='unavailable'
    old=predict_reference([{'month':'2001-01','active_cell_days':5}],'fixture','N','T','standard')['items'][0]
    assert old['lower'] is None and old['upper'] is None and old['model_status']=='extrapolated'


def test_no_model_does_not_invent_prediction():
    assert predict_reference([{'month':'2018-01','active_cell_days':10}],'region','N','T','standard')['status']=='unavailable'


def test_zero_denominator_not_hidden():
    report=metrics([{'month':'2024-01','region':'fixture','viirs':0}],np.array([0]))
    assert report['wape'] is None
    with pytest.raises(ValueError):fit_ratio([{'modis':0,'viirs':1}])


def test_year_leakage_rejected(tmp_path):
    path=tmp_path/'pairs.csv';rows=synthetic_pairs(path);rows[12]['split']='test'
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    with pytest.raises(ValueError):load_pairs(path)


def test_missing_month_not_imputed(tmp_path):
    path=tmp_path/'pairs.csv';rows=synthetic_pairs(path);rows.pop()
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    with pytest.raises(ValueError,match='incomplete'):load_pairs(path)


def _write(path,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def test_benchmark_is_deterministic_for_fixed_seed(tmp_path):
    path=tmp_path/'p.csv';synthetic_pairs(path)
    a=benchmark(path,tmp_path/'a.json',seed=7);b=benchmark(path,tmp_path/'b.json',seed=7)
    for report in (a,b):report.pop('created_at')
    assert a==b


@pytest.mark.parametrize('field,value',[('modis','-1'),('viirs','nan'),('modis','inf'),('viirs','2.5'),('modis','abc')])
def test_invalid_counts_rejected(tmp_path,field,value):
    path=tmp_path/'p.csv';rows=synthetic_pairs(path);rows[0][field]=value;_write(path,rows)
    with pytest.raises(ValueError):load_pairs(path)


def test_duplicate_month_and_mixed_processing_rejected(tmp_path):
    path=tmp_path/'p.csv';rows=synthetic_pairs(path);rows[1]['month']=rows[0]['month'];_write(path,rows)
    with pytest.raises(ValueError,match='duplicate'):load_pairs(path)
    rows=synthetic_pairs(path);rows[0]['processing_status']='nrt';_write(path,rows)
    with pytest.raises(ValueError,match='processing_status'):load_pairs(path)


def test_predictions_nonnegative_and_zero_input_handling(tmp_path):
    path=tmp_path/'p.csv';synthetic_pairs(path);benchmark(path,tmp_path/'r.json')
    items=predict_reference([{'month':f'2018-{m:02d}','active_cell_days':v} for m,v in [(1,0),(2,3),(3,10**6)]],'fixture','N','T','standard')['items']
    assert all(i['estimate']>=0 and (i['lower'] is None or i['lower']>=0) for i in items)
    assert items[0]['estimate']==0 or items[0]['model_status']=='extrapolated'
    # Input far outside the training count support and an unseen region carry no calibrated band.
    assert items[2]['model_status']=='extrapolated' and items[2]['upper'] is None
    unseen=predict_reference([{'month':'2018-01','active_cell_days':5}],'elsewhere','N','T','standard')['items'][0]
    assert unseen['model_status']=='extrapolated' and unseen['interval_status']=='unavailable_extrapolation'
    assert all(i['coverage_status']=='unknown' for i in items+[unseen])


def test_registered_scope_mismatch_unavailable(tmp_path):
    path=tmp_path/'p.csv';rows=synthetic_pairs(path)
    for r in rows:r.update(country='Portugal',bbox='-9.6,36.8,-6,42.2')
    _write(path,rows);benchmark(path,tmp_path/'r.json')
    item=[{'month':'2018-01','active_cell_days':5}]
    assert predict_reference(item,'fixture','N','T','standard',bbox='-9.6,36.8,-6,42.2',country='Portugal')['status']=='available'
    assert predict_reference(item,'fixture','N','T','standard',bbox='0,0,1,1',country='Portugal')['status']=='unavailable'
    assert predict_reference(item,'fixture','N','T','nrt',bbox='-9.6,36.8,-6,42.2',country='Portugal')['status']=='unavailable'


def test_calibration_data_never_in_training_partition(tmp_path):
    path=tmp_path/'p.csv';synthetic_pairs(path)
    rows,parts,years=load_pairs(path)
    train_months={r['month'] for r in parts['train']}
    assert not train_months & {r['month'] for r in parts['validation']+parts['calibration']+parts['test']}
    assert max(years['train'])<min(years['validation'])<min(years['calibration'])<min(years['test'])


def test_rolling_origin_uses_only_earlier_years(tmp_path):
    path=tmp_path/'p.csv';rows=synthetic_pairs(path)
    from firetrust.science import rolling_origin
    rows,_,_=load_pairs(path)
    result=rolling_origin(rows)
    assert result['n_folds']==4 and [f['year'] for f in result['folds']]==[2015,2016,2017,2018]
    assert all(f['train_years']==f['year']-2012 for f in result['folds'])
    # Changing the forecast year's targets must not change that fold's training: perturb 2018 only.
    for r in rows:
        if r['month'].startswith('2018'):r['viirs']+=1000
    changed=rolling_origin(rows)
    assert [f['B1_mae'] for f in changed['folds'][:3]]==[f['B1_mae'] for f in result['folds'][:3]]
    assert changed['folds'][3]['B1_mae']>result['folds'][3]['B1_mae']
    assert rolling_origin(rows,min_train_years=50) is None


def test_registry_selects_model_by_modis_satellite(tmp_path):
    path=tmp_path/'t.csv';rows=synthetic_pairs(path)
    benchmark(path,tmp_path/'t.json')
    for r in rows:r['modis_satellite']='A'
    aqua=tmp_path/'a.csv';_write(aqua,rows);benchmark(aqua,tmp_path/'a.json')
    item=[{'month':'2018-01','active_cell_days':5}]
    t=predict_reference(item,'fixture','N','T','standard');a=predict_reference(item,'fixture','N','A','standard')
    assert t['status']==a['status']=='available' and t['model_id']!=a['model_id']


def test_transfer_evaluation_requires_registered_model():
    from firetrust.pilot import transfer_evaluation
    with pytest.raises(ValueError,match='register a benchmark'):transfer_evaluation('A')


def test_band_withheld_outside_calibration_activity(tmp_path):
    path=tmp_path/'p.csv';synthetic_pairs(path);report=benchmark(path,tmp_path/'r.json')
    info=report['test']['B1_shrunk_ratio']['band_within_calibration_activity']
    lo,hi=info['calibration_modis_range']
    assert info['months_with_band']+info['months_band_withheld']==report['partition_sizes']['test']
    inside=predict_reference([{'month':'2018-01','active_cell_days':lo}],'fixture','N','T','standard')['items'][0]
    outside=predict_reference([{'month':'2018-01','active_cell_days':hi+1}],'fixture','N','T','standard')['items'][0]
    assert inside['interval_status']=='empirical_calibration_band' and inside['lower'] is not None
    below=predict_reference([{'month':'2018-01','active_cell_days':max(0,lo-1)}],'fixture','N','T','standard')['items'][0]
    if below['model_status']!='extrapolated':assert below['interval_status']=='empirical_calibration_band'
    if outside['model_status']!='extrapolated':
        assert outside['interval_status']=='unavailable_outside_calibration_activity' and outside['lower'] is None
    assert report['test']['B1_shrunk_ratio']['region_year_blocks']==3


def test_loglinear_candidate_selected_by_unchanged_rule_on_power_law_fixture(tmp_path):
    # Synthetic power-law relation (ratio falls with activity), never satellite data.
    rows=[]
    for year in range(2012,2019):
        split='train' if year<2014 else 'validation' if year==2014 else 'calibration' if year==2015 else 'test'
        for month in range(1,13):
            m=(month*7+year%5*30)**1.3
            rows.append(dict(region='fixture',month=f'{year}-{month:02d}',modis=round(m),viirs=round(12*(m+1)**0.6-1),split=split,reference_satellite='N',modis_satellite='T',processing_status='standard',source_manifest='synthetic-test-only'))
    path=tmp_path/'p.csv';_write(path,rows)
    report=benchmark(path,tmp_path/'r.json')
    assert 'B3_loglinear' in report['validation'] and report['selected_model']=='B3_loglinear'
    assert report['test']['B3_loglinear']['mae']<report['test']['B1_shrunk_ratio']['mae']
    out=predict_reference([{'month':'2018-06','active_cell_days':200}],'fixture','N','T','standard')
    assert out['method']=='B3_loglinear' and out['items'][0]['estimate']>0
