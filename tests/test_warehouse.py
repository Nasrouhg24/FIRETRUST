import json

import h3
import pytest

from firetrust.ingestion import ingest_bytes,root
from firetrust.series import calendar_matrix,monthly_series,summary
from firetrust.warehouse import build_snapshot


def test_h3_active_days_union_without_satellite_or_daynight_double_count(payload):
    for satellite,time,daynight in [('N20','0100','D'),('N21','0200','D'),('N20','0300','N')]:
        ingest_bytes(payload({'satellite':satellite,'acq_time':time,'daynight':daynight}),'fixture')
    build_snapshot();series=monthly_series()
    assert series['union_by_sensor'][0]['active_cell_days']==1
    assert sum(r['active_cell_days'] for r in series['items'])==2
    data=summary();assert data['detections']==3 and data['cell_count']==1
    assert data['cells'][0]['cell_area_km2']==pytest.approx(h3.cell_area(data['cells'][0]['grid_id'],unit='km^2'))


def test_snapshot_replay_and_checksums(payload):
    import hashlib
    ingest_bytes(payload(),'fixture');a=build_snapshot();b=build_snapshot()
    assert a==b
    for path,digest in a['files'].items():
        assert hashlib.sha256((root()/'warehouse'/a['snapshot_id']/path).read_bytes()).hexdigest()==digest


def test_missing_month_unknown_not_zero(payload):
    ingest_bytes(payload(),'fixture');build_snapshot()
    cells=calendar_matrix(start='2024-01-01',end='2024-03-01')['cells']
    feb=next(r for r in cells if r['key']=='2024-02')
    assert feb['active_cell_days'] is None and feb['series']==[] and feb['state']=='no_records_coverage_unknown'
    # No observations is represented by state, not a claim that zero fires occurred.
    assert feb['coverage_status']=='unknown'


def test_zero_only_with_complete_archive_manifest(payload):
    source='https://firms.modaps.eosdis.nasa.gov/data/country/viirs-snpp/2024/viirs-snpp_2024_Portugal.csv'
    ingest_bytes(payload({'satellite':'N'}),source);build_snapshot()
    folder=root()/'manifests';folder.mkdir()
    manifest={'files':{'file':{'sensor':'viirs-snpp','year':2024,'archive_query_status':'complete_file','processing_statuses':['standard'],'batch_id':'test'}}}
    (folder/'country-Portugal-2024-2024.json').write_text(json.dumps(manifest))
    series=monthly_series(country='Portugal',processing_status='standard')
    feb=next(r for r in series['items'] if r['month']=='2024-02')
    assert feb['active_cell_days']==0 and feb['archive_status']=='complete_country_file_no_matching_records' and feb['coverage_status']=='unknown'
    bounded=monthly_series(country='Portugal',processing_status='standard',start='2024-01-01',end='2024-02-01')
    assert all(r['month']=='2024-01' for r in bounded['items'])


@pytest.mark.parametrize('kwargs',[{'bbox':'-1,0,-2,2'},{'start':'bad'},{'sensor':'LANDSAT'},{'country':"Portugal';drop"}])
def test_invalid_query_inputs(kwargs):
    with pytest.raises(ValueError):summary(**kwargs)


def test_mixed_sensor_frp_not_summed(payload):
    ingest_bytes(payload(),'fixture')
    ingest_bytes(payload({'instrument':'MODIS','satellite':'T','confidence':'80'}),'fixture')
    build_snapshot()
    assert summary()['frp_mw_sum'] is None


def test_anomaly_target_range_does_not_remove_historical_baseline(payload):
    from firetrust.series import anomalies
    for year in range(2018,2025):
        ingest_bytes(payload({'acq_date':f'{year}-01-03'}),'fixture')
        ingest_bytes(payload({'acq_date':f'{year}-02-03'}),'fixture')
    build_snapshot()
    result=anomalies(start='2024-01-01',end='2024-02-01')
    assert len(result['items'])==1
    assert result['items'][0]['baseline_years']==6 and result['items'][0]['delta']==0


def _complete_archive_manifest(sensor,year,country='Portugal'):
    folder=root()/'manifests';folder.mkdir(exist_ok=True)
    manifest={'files':{'file':{'sensor':sensor,'year':year,'archive_query_status':'complete_file','processing_statuses':['standard'],'batch_id':'test'}}}
    (folder/f'country-{country}-{year}-{year}.json').write_text(json.dumps(manifest))


def test_zero_fill_does_not_depend_on_requested_window(payload):
    source='https://firms.modaps.eosdis.nasa.gov/data/country/viirs-snpp/2024/viirs-snpp_2024_Portugal.csv'
    rows=[dict(latitude='39.5',longitude='-8.1',acq_date=d,acq_time='0100',satellite='N',instrument='VIIRS',confidence='n',frp='5',scan='.4',track='.5',daynight='N',version='2',type='0') for d in ('2024-02-03','2024-04-03')]
    ingest_bytes(payload(rows=rows),source);build_snapshot();_complete_archive_manifest('viirs-snpp',2024)
    full={r['month']:r['active_cell_days'] for r in monthly_series(country='Portugal',processing_status='standard')['items']}
    window=monthly_series(country='Portugal',processing_status='standard',start='2024-03-01',end='2024-04-01')['items']
    assert full['2024-03']==0
    assert [(r['month'],r['active_cell_days']) for r in window]==[('2024-03',0)]
    assert '2024-01' not in full  # before the satellite's first recorded month: unknown, not zero


def test_anomalies_honor_processing_status(payload):
    from firetrust.series import anomalies
    for year in range(2018,2025):
        ingest_bytes(payload({'acq_date':f'{year}-01-03','version':'2'}),'fixture')
    build_snapshot()
    assert anomalies(processing_status='standard')['items']
    nrt=anomalies(processing_status='nrt')
    assert nrt['items']==[] and nrt['status']=='insufficient_history'


def test_failed_archive_file_never_zero_filled(payload):
    # MODIS file complete; the VIIRS file for the same year failed (absent from manifest['files']).
    source='https://firms.modaps.eosdis.nasa.gov/data/country/modis/2023/modis_2023_Zambia.csv'
    ingest_bytes(payload({'instrument':'MODIS','satellite':'Aqua','confidence':'80','acq_date':'2023-03-03','version':'6.1'}),source)
    ingest_bytes(payload({'satellite':'N','acq_date':'2022-03-03'}),'https://firms.modaps.eosdis.nasa.gov/data/country/viirs-snpp/2022/viirs-snpp_2022_Zambia.csv')
    build_snapshot()
    folder=root()/'manifests';folder.mkdir(exist_ok=True)
    manifest={'files':{'modis_2023_Zambia.csv':{'sensor':'modis','year':2023,'archive_query_status':'complete_file','processing_statuses':['standard'],'batch_id':'m'},
                       'viirs-snpp_2022_Zambia.csv':{'sensor':'viirs-snpp','year':2022,'archive_query_status':'complete_file','processing_statuses':['standard'],'batch_id':'v'}},
              'failures':[{'file':'viirs-snpp_2023_Zambia.csv','error':'OperationalError'}]}
    (folder/'country-Zambia-2022-2025.json').write_text(json.dumps(manifest))
    items=monthly_series(country='Zambia',processing_status='standard')['items']
    assert not [r for r in items if r['satellite']=='N' and r['month'].startswith('2023')]
    assert any(r['satellite']=='N' and r['month']=='2022-04' and r['active_cell_days']==0 for r in items)
    assert any(r['satellite']=='A' and r['month']=='2023-04' and r['active_cell_days']==0 for r in items)


def test_summary_cells_carry_resolvable_evidence_ids_and_stream_aggregates(payload):
    from firetrust.api import app
    from fastapi.testclient import TestClient
    rows=[dict(latitude='39.5',longitude='-8.1',acq_date=f'2024-01-0{d}',acq_time='0100',satellite=s,instrument=i,confidence='n' if i=='VIIRS' else '80',frp='5',scan='.4',track='.5',daynight='N',version='2',type='0') for d in (1,2) for s,i in (('N','VIIRS'),('Terra','MODIS'))]
    ingest_bytes(payload(rows=rows),'fixture');build_snapshot()
    data=summary()
    assert data['detections']==4 and data['cell_count']==2 and data['sensors']=={'VIIRS':2,'MODIS':2}
    client=TestClient(app)
    for cell in data['cells']:
        assert cell['evidence_ids'][0] and client.get('/api/evidence/'+cell['evidence_ids'][0]).status_code==200
    # Filtered selections keep the evidence lookup inside the filter.
    filtered=summary(sensor='MODIS')
    assert filtered['detections']==2 and all(client.get('/api/evidence/'+c['evidence_ids'][0]).json()['detection']['sensor']=='MODIS' for c in filtered['cells'])
