import csv
import io

from fastapi.testclient import TestClient

from firetrust.api import app
from firetrust.ingestion import ingest_bytes
from firetrust.warehouse import build_snapshot


def test_api_filters_provenance_and_export(payload):
    batch=ingest_bytes(payload(),'fixture');build_snapshot();client=TestClient(app)
    assert client.get('/api/health').json()['detections']==1
    data=client.get('/api/detections?bbox=-9,39,-7,40').json();assert data['total']==1
    evidence=client.get('/api/evidence/'+data['items'][0]['id']).json()
    assert evidence['batches'][0]['id']==batch['id']
    summary=client.get('/api/analytics');assert summary.status_code==200 and summary.json()['detections']==1
    response=client.get('/api/v1/exports/csv');assert response.status_code==200
    rows=list(csv.DictReader(io.StringIO(response.text)));assert len(rows)==1 and rows[0]['coverage_status']=='unknown'
    assert client.get('/api/v1/method').json()['model_status']=='unavailable'
    comparison=client.get('/api/v1/sensor-comparison').json();assert comparison['harmonized']['status']=='unavailable'
    assert client.get('/api/v1/calendar?start=2024-01-01&end=2024-12-31').status_code==200


def test_bad_filter_and_limits():
    client=TestClient(app)
    assert client.get('/api/detections?bbox=nan,1,2,3').status_code==422
    assert client.get('/api/detections?limit=999999').status_code==422
    assert client.get('/api/detections?start=2025-01-01&end=2024-01-01').status_code==422
    assert client.get('/api/evidence/not-found').status_code==404
    assert client.get('/api/v1/tiles/30/0/0').status_code==422


def test_refresh_disabled_and_invalid_token(monkeypatch):
    client=TestClient(app)
    assert client.post('/api/refresh',json={'sensor':'viirs'}).status_code==503
    monkeypatch.setenv('FIRETRUST_WRITE_TOKEN','test-token')
    assert client.post('/api/refresh',json={'sensor':'viirs'},headers={'Authorization':'Bearer incorrect'}).status_code==401


def test_tile_is_bounded_geojson(payload):
    ingest_bytes(payload(),'fixture');client=TestClient(app)
    response=client.get('/api/v1/tiles/0/0/0');assert response.status_code==200
    result=response.json();assert result['type']=='FeatureCollection' and len(result['features'])==1


def test_aggregate_export(payload):
    ingest_bytes(payload(),'fixture');build_snapshot();client=TestClient(app)
    result=client.get('/api/v1/exports/csv?mode=aggregate')
    assert 'active_cell_days' in result.text and 'snapshot_id' in result.text


def test_offset_dates_are_compared_in_utc(payload):
    ingest_bytes(payload(),'fixture');client=TestClient(app)
    response=client.get('/api/detections',params={'start':'2024-01-03T02:00:00+02:00','end':'2024-01-03T01:30:00Z'})
    assert response.status_code==200 and response.json()['total']==1


def test_aggregate_export_honors_processing_filter(payload):
    ingest_bytes(payload({'version':'2.0NRT'}),'fixture');build_snapshot();client=TestClient(app)
    standard=list(csv.DictReader(io.StringIO(client.get('/api/v1/exports/csv?mode=aggregate&processing=standard').text)))
    nrt=list(csv.DictReader(io.StringIO(client.get('/api/v1/exports/csv?mode=aggregate&processing=nrt').text)))
    assert standard==[] and len(nrt)==1 and nrt[0]['processing_status']=='nrt'


def test_bbox_wrong_arity_has_clear_error():
    response=TestClient(app).get('/api/analytics?bbox=1,2,3')
    assert response.status_code==422 and 'west,south,east,north' in response.json()['detail']


def test_stored_area_limit(monkeypatch):
    from firetrust import api
    monkeypatch.setattr(api,'MAX_STORED_AREAS',1)
    client=TestClient(app)
    square=lambda x:{'geometry':{'type':'Polygon','coordinates':[[[x,0],[x+1,0],[x+1,1],[x,1],[x,0]]]}}
    assert client.post('/api/v1/areas/validate',json=square(0)).status_code==200
    assert client.post('/api/v1/areas/validate',json=square(0)).status_code==200  # replay of a stored area
    assert client.post('/api/v1/areas/validate',json=square(5)).status_code==507


def test_frontend_data_contract_keys(payload):
    # Field names consumed by frontend/src/ScienceViews.tsx and CalendarView.tsx.
    for year in range(2018,2025):
        ingest_bytes(payload({'acq_date':f'{year}-01-03','satellite':'N','version':'2'}),'fixture')
    build_snapshot();client=TestClient(app)
    series=client.get('/api/v1/sensor-comparison?processing=standard').json()
    assert {'items','unit','harmonized'}<=set(series)
    assert {'month','sensor','satellite','active_cell_days','detection_count','processing_status','coverage_status'}<=set(series['items'][0])
    assert {'status','reason','items'}<=set(series['harmonized'])
    anomalies=client.get('/api/v1/anomalies?processing=standard').json()
    assert {'month','sensor','satellite','active_cell_days','baseline_median','delta','baseline_years','robust_z'}<=set(anomalies['items'][0])
    calendar=client.get('/api/v1/calendar?start=2024-01-01&end=2024-12-31').json()
    assert {'year','month','key','active_cell_days','coverage_status','state'}<=set(calendar['cells'][0])
    method=client.get('/api/v1/method').json()
    assert {'model','independent_ground_validation','snapshot'}<=set(method) and method['independent_ground_validation']=='not_performed'
    analytics=client.get('/api/analytics').json()
    assert {'detections','sensors','confidence','frp_mw_sum','flagged_cell_count','cell_count','calendar','monthly','cells','limitations'}<=set(analytics)


def test_validation_summary_serves_reviewed_evidence_without_computing():
    data=TestClient(app).get('/api/v1/validation').json()
    assert 'not true fire activity' in data['target'] and data['status'].startswith('exploratory')
    # Evidence files ship with the repository; values must equal the files, not be recomputed.
    import json
    from pathlib import Path
    stored=json.loads((Path(__file__).parents[1]/'docs'/'evidence'/'transfer-eval.json').read_text(encoding='utf-8'))
    for region,v in stored['regions'].items():
        assert data['transfer']['A'][region]['model_wape']==v['registered_model']['wape']
        assert data['transfer']['A'][region]['model_bias']<0
    assert 0<data['bands']['A']['other_regions']['coverage_all']<data['bands']['A']['fitted_region']['coverage_all']


def test_method_endpoint_accepts_modis_satellite():
    client=TestClient(app)
    assert client.get('/api/v1/method?modis=A').status_code==200
    assert client.get('/api/v1/method?modis=X').status_code==422
