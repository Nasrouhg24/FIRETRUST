import hashlib
from pathlib import Path

import pytest

from firetrust.ingestion import connect,fetch_area,ingest_bytes


def test_idempotent_raw_evidence(payload):
    data=payload();first=ingest_bytes(data,'NASA test fixture');second=ingest_bytes(data,'NASA test fixture')
    assert first['inserted']==1 and second['replayed'] and second['inserted']==0
    with connect() as db:
        row=db.execute('SELECT * FROM batches').fetchone()
        assert hashlib.sha256(Path(row['raw_path']).read_bytes()).hexdigest()==first['id']
        assert db.execute('SELECT count(*) FROM detections').fetchone()[0]==1


@pytest.mark.parametrize('confidence',['low','nominal','high','l','n','h'])
def test_nasa_viirs_confidence_spellings(payload,confidence):
    assert ingest_bytes(payload({'confidence':confidence}),'fixture')['accepted']==1


@pytest.mark.parametrize('overrides',[{'latitude':'NaN'},{'longitude':'181'},{'frp':'-1'},{'acq_time':'2500'},{'confidence':'101'},{'acq_date':'2024-02-30'},{'daynight':'X'},{'latitude':'inf'}])
def test_bad_science_rows_quarantined(payload,overrides):
    result=ingest_bytes(payload(overrides),'fixture')
    assert result['accepted']==0 and result['rejected']==1 and result['errors'][0]['line']==2


def test_public_feed_without_instrument(payload):
    raw=payload().decode().replace('instrument,','').replace('VIIRS,','').replace('latitude,','bright_ti4,latitude,').replace('39.5,','320,39.5,')
    assert ingest_bytes(raw.encode(),'fixture')['accepted']==1


def test_schema_error_does_not_create_batch():
    with pytest.raises(ValueError,match='required columns'):
        ingest_bytes(b'<html>Invalid MAP_KEY</html>','fixture')
    with connect() as db:assert db.execute('SELECT count(*) FROM batches').fetchone()[0]==0


def test_overlap_preserves_both_sources(payload):
    a=payload();b=a+b'\n'
    first=ingest_bytes(a,'first');second=ingest_bytes(b,'second')
    assert first['id']!=second['id'] and second['inserted']==0
    with connect() as db:assert db.execute('SELECT count(*) FROM batch_detections').fetchone()[0]==2


def test_canonical_satellite_and_type_retained(payload):
    ingest_bytes(payload({'satellite':'Terra','instrument':'MODIS','confidence':'82','version':'61.03','type':'2'}),'fixture')
    with connect() as db:
        row=db.execute('SELECT * FROM detections').fetchone()
        assert row['satellite']=='T' and row['type_raw']=='2' and row['confidence_class']=='high'


def test_missing_optional_frp_is_not_zero(payload):
    ingest_bytes(payload({'frp':''}),'fixture')
    with connect() as db:assert db.execute('SELECT frp FROM detections').fetchone()[0] is None


@pytest.mark.parametrize('bbox,days',[('-190,0,10,5',1),('0,0,5,5',6),('5,0,0,5',1),('nan,0,5,5',1)])
def test_invalid_area_rejected_before_network(bbox,days):
    with pytest.raises(ValueError):fetch_area('MODIS_SP',bbox,days)


def test_short_and_surplus_rows_are_quarantined_not_fatal(payload):
    good=payload().decode()
    header,row=good.strip().splitlines()
    fields=row.split(',')
    short=','.join(fields[:5])
    surplus=row+',unexpected'
    result=ingest_bytes('\n'.join([header,row,short,surplus]).encode(),'fixture')
    assert result['accepted']==1 and result['rejected']==2
    assert {e['line'] for e in result['errors']}=={3,4}
    assert all('malformed row' in e['reason'] for e in result['errors'])


def test_non_ascii_digit_time_rejected(payload):
    result=ingest_bytes(payload({'acq_time':'０１３０'}),'fixture')
    assert result['accepted']==0 and result['rejected']==1


def test_area_request_day_limit_message():
    with pytest.raises(ValueError,match='1-5 days'):fetch_area('MODIS_SP','0,0,5,5',6)


def test_parallel_ingestion_serializes_sqlite_writes(payload):
    from concurrent.futures import ThreadPoolExecutor
    batches=[payload({'acq_date':f'2024-01-{d:02d}'}) for d in range(1,13)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        results=list(pool.map(lambda b:ingest_bytes(b,'fixture'),batches))
    assert sum(r['inserted'] for r in results)==12
    with connect() as db:assert db.execute('SELECT count(*) FROM batches').fetchone()[0]==12


class _Response:
    def __init__(self,body,length):self.body=body;self.headers={'Content-Length':str(length)}
    def read(self,n):return self.body
    def __enter__(self):return self
    def __exit__(self,*a):return False


def test_download_retries_truncated_payload_then_succeeds(payload,monkeypatch):
    import urllib.request,time
    from firetrust import ingestion
    body=payload();calls=[]
    def fake(request,timeout):
        calls.append(1)
        return _Response(body[:-5],len(body)) if len(calls)==1 else _Response(body,len(body))
    monkeypatch.setattr(urllib.request,'urlopen',fake);monkeypatch.setattr(time,'sleep',lambda s:None)
    assert ingestion.download('https://example.invalid/x.csv','fixture')['accepted']==1 and len(calls)==2


def test_download_gives_up_on_persistent_truncation(payload,monkeypatch):
    import urllib.request,time
    from firetrust import ingestion
    body=payload()
    monkeypatch.setattr(urllib.request,'urlopen',lambda r,timeout:_Response(body[:-5],len(body)));monkeypatch.setattr(time,'sleep',lambda s:None)
    with pytest.raises(RuntimeError,match='truncated'):ingestion.download('https://example.invalid/x.csv','fixture')
    with connect() as db:assert db.execute('SELECT count(*) FROM batches').fetchone()[0]==0


def test_evidence_lookup_by_detection_uses_index():
    with connect() as db:
        plan=' '.join(str(tuple(r)) for r in db.execute('EXPLAIN QUERY PLAN SELECT b.* FROM batches b JOIN batch_detections bd ON b.id=bd.batch_id WHERE bd.detection_id=?',('x',)))
    assert 'batch_detection_lookup' in plan
