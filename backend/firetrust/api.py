"""FastAPI read API; optional authenticated NASA refresh for local operation."""
from __future__ import annotations

import hmac
import os
import threading
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .analytics import analytics, query
from .ingestion import PUBLIC, connect, download

app = FastAPI(title='FIRETRUST', version='0.1.0', description='Traceable NASA fire detections; research prototype, not emergency guidance.')
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'], allow_methods=['GET', 'POST'], allow_headers=['Authorization', 'Content-Type'])
app.add_middleware(GZipMiddleware,minimum_size=1000,compresslevel=5)
_refresh_lock = threading.Lock()
MAX_STORED_AREAS = 10_000


def filters(start: str | None = None, end: str | None = None, sensor: str | None = None, bbox: str | None = None, country: str | None = None,area_id: str | None = None):
    return dict(start=start, end=end, sensor=sensor, bbox=bbox,country=country,area_id=area_id)


def safe_call(fn, **args):
    try:
        return fn(**args)
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from None


@app.get('/api/health')
def health():
    with connect() as db:
        count = db.execute('SELECT count(*) FROM detections').fetchone()[0]
        batches = db.execute('SELECT count(*) FROM batches').fetchone()[0]
    return {'status': 'ok', 'detections': count, 'batches': batches, 'mode': 'observational', 'independent_validation': 'pending'}


@app.get('/api/detections')
def detections(f: dict = Depends(filters), limit: int = Query(1000, ge=1, le=10000), offset: int = Query(0, ge=0)):
    return safe_call(query, **f, limit=limit, offset=offset)


@app.get('/api/analytics')
def overview(f: dict = Depends(filters)):
    return safe_call(analytics, **f)


@app.get('/api/batches')
def batches():
    with connect() as db:
        rows = db.execute('SELECT * FROM batches ORDER BY fetched_at DESC LIMIT 100').fetchall()
    return {'items': [dict(r) for r in rows]}


@app.get('/api/evidence/{detection_id}')
def evidence(detection_id: str):
    with connect() as db:
        row = db.execute('SELECT * FROM detections WHERE id=?', (detection_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Detection not found')
        batches = db.execute('SELECT b.* FROM batches b JOIN batch_detections bd ON b.id=bd.batch_id WHERE bd.detection_id=?', (detection_id,)).fetchall()
    return {'detection': dict(row), 'batches': [dict(b) for b in batches], 'interpretation': 'Satellite active-fire observation. No causal attribution established.'}


class Refresh(BaseModel):
    sensor: str = Field(default='viirs', pattern='^(viirs|modis|noaa20|noaa21)$')


def require_write(credentials: HTTPAuthorizationCredentials | None = Security(HTTPBearer(auto_error=False))):
    token = os.getenv('FIRETRUST_WRITE_TOKEN', '')
    if not token:
        raise HTTPException(503, 'Refresh disabled: configure FIRETRUST_WRITE_TOKEN or use the CLI')
    if credentials is None or not hmac.compare_digest(credentials.credentials, token):
        raise HTTPException(401, 'Invalid bearer token')


@app.post('/api/refresh', dependencies=[Depends(require_write)])
def refresh(body: Refresh):
    if not _refresh_lock.acquire(blocking=False):
        raise HTTPException(409, 'A refresh is already running')
    try:
        result=download(PUBLIC[body.sensor], f'NASA FIRMS public {body.sensor} global 24h')
        from .warehouse import build_snapshot
        if result['accepted']:
            build_snapshot()
        return result
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(502, str(exc)) from None
    finally:
        _refresh_lock.release()


from fastapi.responses import StreamingResponse
from . import series
from .warehouse import snapshot_manifest


@app.get('/api/v1/calendar')
def calendar_api(f: dict = Depends(filters), view: str = Query('activity',pattern='^(activity|reliability)$')):
    return safe_call(series.calendar_matrix,**f,view=view)


@app.get('/api/v1/timeseries')
def timeseries_api(f: dict = Depends(filters), aggregation: str = Query('month',pattern='^month$'), view: str = Query('raw',pattern='^(raw|harmonized)$'),
                   reference: str = 'N', modis: str = 'T', region_id: str = 'custom', processing: str = Query('nrt',pattern='^(standard|nrt)$')):
    data=safe_call(series.monthly_series,**f,processing_status=processing,reference_satellite=reference,modis_satellite=modis)
    if view=='harmonized':
        from .science import predict_reference
        source=[r for r in data['items'] if r['sensor']=='MODIS' and r['satellite']==modis]
        data['harmonized']=predict_reference(source,region_id,reference,modis,processing,bbox=f.get('bbox'),country=f.get('country'))
    return data


@app.get('/api/v1/sensor-comparison')
def sensor_comparison(f: dict = Depends(filters),reference: str='N',modis: str='T',processing: str=Query('nrt',pattern='^(standard|nrt)$'),region_id: str='custom'):
    return timeseries_api(f,'month','harmonized',reference,modis,region_id,processing)


@app.get('/api/v1/anomalies')
def anomaly_api(f: dict = Depends(filters),view:str=Query('raw',pattern='^(raw|harmonized)$'),region_id:str='custom',
                reference:str='N',modis:str='T',processing:str=Query('standard',pattern='^(standard|nrt)$')):
    return safe_call(series.anomalies,**f,view=view,region_id=region_id,reference_satellite=reference,
                     modis_satellite=modis,processing_status=processing)


_EVIDENCE = Path(__file__).resolve().parents[2] / 'docs' / 'evidence'


def _evidence(name):
    import json
    path = _EVIDENCE / name
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


@app.get('/api/v1/validation')
def validation_summary():
    """Read-only summary of the reviewed evidence files (docs/evidence). Nothing is computed or altered here."""
    out = {'status': 'exploratory_reanalysis_of_previously_inspected_data', 'target': 'agreement with the S-NPP satellite reference, not true fire activity',
           'sources': [], 'transfer': {}, 'bands': {}, 'nested_selection': None, 'paired_satellite': None, 'overpass': None}
    for sat, name in (('A', 'transfer-eval.json'), ('T', 'transfer-eval-T.json')):
        data = _evidence(name)
        if data:
            out['sources'].append(name)
            out['transfer'][sat] = {region: {'months': v['months'], 'model_wape': v['registered_model']['wape'], 'model_bias': v['registered_model']['signed_bias'],
                                             'raw_wape': v['B0_raw']['wape'], 'model_mae': v['registered_model']['mae'], 'raw_mae': v['B0_raw']['mae']}
                                    for region, v in data['regions'].items() if 'registered_model' in v}
    science = _evidence('science-eval.json')
    if science:
        out['sources'].append('science-eval.json')
        for sat, key in (('A', 'rolling_band_aqua'), ('T', 'rolling_band_terra')):
            block = science.get(key)
            if block:
                def pick(s):
                    return None if not s else {'months': s['months'], 'share_withheld': s['share_above_calibration_range'], 'coverage_all': s['absolute']['coverage_all'],
                                               'coverage_when_shown': s['absolute']['coverage_when_shown_under_rule'], 'coverage_withheld': s['absolute']['coverage_withheld']}
                out['bands'][sat] = {'nominal': block['nominal'], 'folds': block['n_folds'], 'fitted_region': pick(block['strata'].get('all_temporal')),
                                     'other_regions': pick(block['strata'].get('all_geographic'))}
        nested = science.get('nested_temporal_portugal')
        if nested:
            out['nested_selection'] = {k: nested[k] for k in ('n_outer_folds', 'selection_frequency', 'mean_outer_mae_selected', 'mean_outer_mae_fixed')}
        paired = science.get('paired_satellite_B1')
        if paired:
            out['paired_satellite'] = {k: paired[k] for k in ('n_folds', 'aqua_better_folds', 'median_terra_over_aqua_mae', 'caveat')}
    diagnostics = _evidence('observing-system-diagnostics.json')
    if diagnostics:
        out['sources'].append('observing-system-diagnostics.json')
        out['overpass'] = {'scope': diagnostics['scope'], 'daytime_median_local_solar_hour': {
            sat: {year: v['median_local_solar_hour'] for year, v in diagnostics['by_satellite'].get(sat, {}).get('D', {}).items()} for sat in ('T', 'A', 'N')},
            'limits': diagnostics['interpretation_limits']}
    untouched = _evidence('zambia-2023-2024-first-acquired.json')
    if untouched:
        out['sources'].append('zambia-2023-2024-first-acquired.json')
        out['first_acquired_after_choice'] = {'note': untouched['note'], 'results': {sat: {'months': v['months'], 'model_wape': v['registered_model']['wape']} for sat, v in untouched['results'].items()}}
    return out


@app.get('/api/v1/method')
def method(modis: str | None = Query(None, pattern='^(T|A)$')):
    from .science import registered_model
    model=registered_model(modis)
    snapshot=snapshot_manifest()
    return {'version':'0.1.0','unit':'H3 r7 active_cell_days per UTC month','grid':'H3 resolution 7, actual cell areas retained',
            'coverage_status':'unknown','model_status':'low_support' if model else 'unavailable',
            'model':model,'snapshot':snapshot,
            'baseline_methods':['B0 unharmonized MODIS','B1 seasonal/region ratio with global shrinkage','B2 log-link Tweedie count regression'],
            'validation_protocol':'Whole chronological years: training, selection, interval calibration, final test; report geographical holdout separately.',
            'independent_ground_validation':'not_performed',
            'limits':['No inferred fire-free months from absent records.','Counts are not unique fires or burned area.','Live feeds do not establish a historical calibration.','NRT and standard processing are evaluated separately.'],
            'sources':[{'title':'NASA FIRMS API','url':'https://firms.modaps.eosdis.nasa.gov/api/area/'},
                       {'title':'NASA FIRMS archive','url':'https://firms.modaps.eosdis.nasa.gov/download/'}]}


def csv_escape(value):
    if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')):
        return "'"+value
    return value


@app.get('/api/v1/exports/csv')
def csv_export(f: dict = Depends(filters),mode: str=Query('raw',pattern='^(raw|aggregate|harmonized)$'),
               reference:str='N',modis:str='T',region_id:str='custom',processing:str=Query('standard',pattern='^(standard|nrt)$')):
    import csv
    import io
    # Validate and determine size before sending streaming headers.
    result=safe_call(query,**f,limit=1)
    if result['total']>250000:
        raise HTTPException(413,'Export exceeds 250000 rows; narrow the area or date range')
    if mode=='harmonized':
        data=timeseries_api(f,'month','harmonized',reference,modis,region_id,processing)
        converted=data['harmonized']
        if converted['status']!='available':
            raise HTTPException(409,converted['reason'])
        items=[{**r,'snapshot_id':data.get('snapshot_id'),'reference_satellite':reference,
                'input_satellite':modis,'processing_status':processing} for r in converted['items']]
        columns=['month','estimate','lower','upper','interval_status','coverage_status','model_status','model_id',
                 'reference_satellite','input_satellite','processing_status','snapshot_id']
    elif mode=='aggregate':
        data=safe_call(series.monthly_series,**f,processing_status=processing)
        items=[{**r,'snapshot_id':data.get('snapshot_id'),'model_status':'unavailable'} for r in data['items']]
        columns=['month','sensor','satellite','processing_status','detection_count','active_cell_days','coverage_status','snapshot_id','model_status']
    else:
        columns=['id','latitude','longitude','acquired_at','sensor','satellite','confidence','confidence_class','frp','scan','track','daynight','version','type_raw','country','batch_id','coverage_status','processing_status']
        items=None
    def generate():
        from .warehouse import processing
        buffer=io.StringIO(newline='')
        writer=csv.DictWriter(buffer,fieldnames=columns,extrasaction='ignore')
        writer.writeheader();yield buffer.getvalue();buffer.seek(0);buffer.truncate(0)
        if items is not None:
            for row in items:
                writer.writerow({k:csv_escape(v) for k,v in row.items()});yield buffer.getvalue();buffer.seek(0);buffer.truncate(0)
        else:
            clause,args=series.predicate(**f)
            with connect() as db:
                cursor=db.execute('SELECT * FROM detections'+clause+' ORDER BY acquired_at,id',args)
                while True:
                    batch=cursor.fetchmany(1000)
                    if not batch: break
                    for entry in batch:
                        row=dict(entry);row.update(coverage_status='unknown',processing_status=processing(row['version']))
                        writer.writerow({k:csv_escape(v) for k,v in row.items()})
                    yield buffer.getvalue();buffer.seek(0);buffer.truncate(0)
    return StreamingResponse(generate(),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="firetrust-{mode}.csv"','X-Coverage-Status':'unknown'})


@app.get('/api/v1/tiles/{z}/{x}/{y}')
def tile(z:int,x:int,y:int,f:dict=Depends(filters)):
    import math
    if not 0<=z<=16 or not 0<=x<2**z or not 0<=y<2**z:
        raise HTTPException(422,'invalid tile coordinates')
    n=2**z
    west,east=x/n*360-180,(x+1)/n*360-180
    north=math.degrees(math.atan(math.sinh(math.pi*(1-2*y/n))))
    south=math.degrees(math.atan(math.sinh(math.pi*(1-2*(y+1)/n))))
    if f.get('bbox'):
        safe_call(series.predicate,**f)
        w,s,e,no=map(float,f['bbox'].split(','))
        west,south,east,north=max(west,w),max(south,s),min(east,e),min(north,no)
        if west>=east or south>=north:
            return {'type':'FeatureCollection','features':[],'truncated':False}
    f={**f,'bbox':f'{west},{south},{east},{north}'}
    data=safe_call(query,**f,limit=1000)
    return {'type':'FeatureCollection','features':[{'type':'Feature','id':r['id'],'geometry':{'type':'Point','coordinates':[r['longitude'],r['latitude']]},'properties':{'sensor':r['sensor'],'confidence_class':r['confidence_class'],'acquired_at':r['acquired_at']}} for r in data['items']],
            'total':data['total'],'truncated':data['truncated'],'limit':1000,'coverage_status':'unknown'}


class AreaRequest(BaseModel):
    geometry: dict


@app.post('/api/v1/areas/validate')
def validate_area(body:AreaRequest):
    from .geometry import validate_geometry
    result=safe_call(validate_geometry,geometry=body.geometry)
    with connect() as db:
        if not db.execute('SELECT 1 FROM areas WHERE id=?',(result['area_id'],)).fetchone() and db.execute('SELECT count(*) FROM areas').fetchone()[0]>=MAX_STORED_AREAS:
            raise HTTPException(507,'Stored area limit reached')
        db.execute('INSERT OR IGNORE INTO areas VALUES (?,?,?,?)',(result['area_id'],result['geometry'],result['bbox'],result['approx_area_km2']))
    return {**result,'coverage_status':'unknown','geometry':body.geometry,'area_measurement':'spherical approximation; exact point inclusion uses longitude/latitude segments'}


_dist = Path(__file__).resolve().parents[2] / 'frontend' / 'dist'
if _dist.is_dir():
    app.mount('/', StaticFiles(directory=_dist, html=True), name='frontend')
