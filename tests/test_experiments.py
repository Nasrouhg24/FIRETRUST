"""Engineering tests for the evaluation protocols. All data are synthetic fixtures, not satellite observations."""
import numpy as np
import pytest

from firetrust import experiments as E


def fixture_pairs(regions=('a','b','c'),years=range(2012,2020),noise=0.0,seed=0):
    rng=np.random.default_rng(seed);rows=[]
    for k,region in enumerate(regions):
        for year in years:
            for month in range(1,13):
                m=float(5+month*(k+1)*3)
                for sat,factor in (('A',3.0),('T',2.0+0.3*(year-2012))):  # Terra ratio drifts by design
                    v=round(factor*m*(1+noise*rng.standard_normal()))
                    rows.append(dict(region=region,month=f'{year}-{month:02d}',year=year,calendar_month=month,satellite=sat,modis=m,viirs=float(max(0,v)),archive_zero=False))
    return rows


def test_candidates_nonnegative_and_exact_on_proportional_data():
    rows=[r for r in fixture_pairs() if r['satellite']=='A']
    for name in E.TRANSFERABLE:
        p=E.CANDIDATES[name](rows)(rows)
        assert (p>=0).all()
    assert np.allclose(E.fit_global_ratio(rows)(rows),[r['viirs'] for r in rows])


def test_nested_selection_never_sees_outer_year(monkeypatch):
    pairs=fixture_pairs(regions=('portugal_mainland',))
    base=E.nested_temporal(pairs,outer_from=2016)
    # Corrupt the outer year 2019: folds for earlier outer years must be unchanged.
    corrupted=[{**r,'viirs':r['viirs']*50} if r['year']==2019 else r for r in pairs]
    other=E.nested_temporal(corrupted,outer_from=2016)
    for a,b in zip(base['folds'][:-1],other['folds'][:-1]):
        assert a['selected']==b['selected'] and a['outer_mae_selected']==b['outer_mae_selected']
    assert base['folds'][-1]['inner_scores']==other['folds'][-1]['inner_scores']
    assert other['folds'][-1]['outer_mae_selected']>base['folds'][-1]['outer_mae_selected']
    assert base['status']==E.PROTOCOL_STATUS


def test_nested_selection_prefers_stable_satellite():
    result=E.nested_temporal(fixture_pairs(regions=('portugal_mainland',)),outer_from=2016)
    assert all(f['selected'].startswith('A:') for f in result['folds'])


def test_loro_excludes_held_out_region_from_fit_and_calibration():
    pairs=fixture_pairs(regions=('a','b','c'),years=range(2022,2026))
    base=E.leave_one_region_out(pairs,'A')
    altered=[{**r,'viirs':r['viirs']*10} if r['region']=='c' else r for r in pairs]
    other=E.leave_one_region_out(altered,'A')
    # Region 'c' changes cannot affect predictions for... region 'c' itself except through its observed targets.
    assert base['regions']['c']['global_ratio']['total_ratio_pred_over_obs']==pytest.approx(1.0)
    assert other['regions']['c']['global_ratio']['total_ratio_pred_over_obs']==pytest.approx(0.1)


def test_conformal_bands_shapes_and_nonnegative():
    res=[(10.0,12.0),(100.0,80.0),(5.0,5.0),(50.0,70.0)]
    bands=E.conformal_bands(res,np.array([0.0,20.0,2000.0]))
    for lo,hi in bands.values():
        assert (lo>=0).all() and (hi>=lo).all()
    abs_w=bands['absolute'][1]-bands['absolute'][0];mul_w=bands['multiplicative'][1]-bands['multiplicative'][0]
    assert mul_w[2]>mul_w[1] and abs_w[2]==abs_w[1]
    empty=E.conformal_bands([],np.array([1.0]))
    assert np.isnan(empty['absolute'][0]).all()


def test_paired_comparison_reports_dependence_caveat():
    result=E.paired_satellite_comparison(fixture_pairs(regions=('a',)))
    assert result['aqua_better_folds']==result['n_folds'] and 'overstate' in result['caveat']


def test_season_flips_for_southern_hemisphere():
    assert E.season('portugal_mainland',7)=='JJA' and E.season('uruguay',1)=='JJA' and E.season('zambia',7)=='DJF'


def test_rolling_band_evaluation_is_out_of_fold():
    pairs=fixture_pairs(regions=('portugal_mainland','b'),years=range(2012,2021),noise=0.2)
    base=E.rolling_band_evaluation(pairs,'A',first_test_year=2016)
    # Inflating the last year's targets only affects that fold's scored months, never calibration of earlier folds.
    changed=E.rolling_band_evaluation([{**r,'viirs':r['viirs']*20} if r['year']==2020 else r for r in pairs],'A',first_test_year=2016)
    assert base['n_folds']==changed['n_folds']==5
    assert changed['strata']['all_temporal']['absolute']['coverage_all']<base['strata']['all_temporal']['absolute']['coverage_all']
    for k in ('absolute','normalized_sqrt','multiplicative'):
        s=base['strata']['all_temporal'][k];assert 0<=s['coverage_all']<=1 and s['median_width']>=0


def test_unseen_region_limitation_states_measured_bias(tmp_path):
    import csv
    from firetrust.science import benchmark,predict_reference
    rows=[]
    for year in range(2012,2019):
        split='train' if year<2014 else 'validation' if year==2014 else 'calibration' if year==2015 else 'test'
        for month in range(1,13):rows.append(dict(region='fixture',month=f'{year}-{month:02d}',modis=month+5,viirs=2*(month+5),split=split,reference_satellite='N',modis_satellite='A',processing_status='standard',source_manifest='synthetic'))
    path=tmp_path/'p.csv'
    with path.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    benchmark(path,tmp_path/'r.json')
    unseen=predict_reference([{'month':'2018-01','active_cell_days':8}],'elsewhere','N','A','standard')
    seen=predict_reference([{'month':'2018-01','active_cell_days':8}],'fixture','N','A','standard')
    assert any('under-predicted' in x for x in unseen['limitations']) and not any('under-predicted' in x for x in seen['limitations'])
    assert 'not true fire activity' in unseen['target']
