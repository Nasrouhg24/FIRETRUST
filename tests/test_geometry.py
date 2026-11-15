import pytest
from fastapi.testclient import TestClient
from firetrust.api import app
from firetrust.geometry import validate_geometry,within_area
from firetrust.ingestion import ingest_bytes
from firetrust.warehouse import build_snapshot


def test_polygon_filter_is_exact_not_just_bbox(payload):
    client=TestClient(app)
    ingest_bytes(payload(),'fixture');build_snapshot()
    triangle={'type':'Polygon','coordinates':[[[-9,39],[-7,39],[-9,41],[-9,39]]]}
    area=client.post('/api/v1/areas/validate',json={'geometry':triangle})
    assert area.status_code==200
    result=client.get('/api/detections',params={'area_id':area.json()['area_id']})
    assert result.json()['total']==1
    excluding={'type':'Polygon','coordinates':[[[-9,39],[-7,39],[-7,39.2],[-9,39]]]}
    aid=client.post('/api/v1/areas/validate',json={'geometry':excluding}).json()['area_id']
    assert client.get('/api/detections',params={'area_id':aid}).json()['total']==0
    assert client.get('/api/analytics',params={'area_id':aid}).json()['detections']==0


@pytest.mark.parametrize('coordinates',[
    [[[0,0],[1,1],[1,0],[0,1],[0,0]]],
    [[[0,0],[1,0],[1,1]]],
    [[[0,0],[1,0],[1,0],[0,0]]],
    [[[0,0],[300,0],[1,1],[0,0]]]
])
def test_bad_polygons_rejected(coordinates):
    with pytest.raises(ValueError):validate_geometry({'type':'Polygon','coordinates':coordinates})
