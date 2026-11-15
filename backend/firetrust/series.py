"""Snapshot-backed aggregates. No missing month is silently made a fire-free month."""
from __future__ import annotations

import calendar
import hashlib
import json
import math
from collections import defaultdict
from datetime import date, datetime, timezone
from functools import lru_cache

import duckdb

from .ingestion import root
from .warehouse import snapshot_manifest


def as_utc(value):
    stamp=datetime.fromisoformat(value.replace('Z','+00:00'))
    return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)


def predicate(start=None, end=None, sensor=None, bbox=None, satellite=None, processing_status=None,country=None,area_id=None):
    clauses, values = [], []
    parsed_bounds = {}
    for value, op in [(start, '>='), (end, '<')]:
        if value:
            stamp = as_utc(value)
            parsed_bounds[op] = stamp
            clauses.append(f'acquired_at{op}?')
            values.append(stamp.isoformat())
    if start and end and parsed_bounds['>='] >= parsed_bounds['<']:
        raise ValueError('start must be before end')
    if sensor:
        if sensor not in {'VIIRS', 'MODIS'}:
            raise ValueError('sensor must be VIIRS or MODIS')
        clauses.append('sensor=?'); values.append(sensor)
    if bbox:
        parts = bbox.split(',')
        if len(parts) != 4:
            raise ValueError('bbox must be west,south,east,north')
        w, s, e, n = [float(x) for x in parts]
        if not all(math.isfinite(x) for x in (w,s,e,n)) or not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
            raise ValueError('bbox must be west,south,east,north; split antimeridian requests')
        clauses.extend(['longitude>=?', 'longitude<=?', 'latitude>=?', 'latitude<=?']); values.extend([w,e,s,n])
    if area_id:
        from .geometry import load_area
        area=load_area(area_id)
        clauses.append('within_area(longitude,latitude,?)');values.append(area['geometry'])
    if country:
        if not country.replace('_','').isalpha(): raise ValueError('invalid country identifier')
        clauses.append('country=?'); values.append(country)
    if satellite:
        clauses.append('satellite=?'); values.append(satellite)
    if processing_status:
        if processing_status not in {'standard', 'nrt', 'rt', 'unknown'}:
            raise ValueError('invalid processing_status')
        clauses.append('processing_status=?'); values.append(processing_status)
    return (' WHERE ' + ' AND '.join(clauses) if clauses else ''), values


def open_snapshot(snapshot_id):
    db = duckdb.connect()
    from .geometry import within_area
    db.create_function('within_area',within_area,['DOUBLE','DOUBLE','VARCHAR'],'BOOLEAN')
    path = str(root() / 'warehouse' / snapshot_id / 'observations' / '**' / '*.parquet')
    safe_path=path.replace("'", "''")
    db.execute(f"CREATE VIEW observations AS SELECT * FROM read_parquet('{safe_path}', hive_partitioning=true)")
    return db


def dictionaries(cursor):
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns,row)) for row in cursor.fetchall()]


def summary(**filters):
    clause, args = predicate(**filters)
    manifest = snapshot_manifest()
    if not manifest:
        from .analytics import query, summarize, harmonize
        data = query(limit=100001, **filters)
        if data['total'] > 100000:
            raise ValueError('Build a warehouse snapshot for large selections')
        cells = harmonize(data['items'])
        return {**summarize(data['items']), 'cells': cells[:1000], 'cell_count': len(cells),
                'flagged_cell_count': sum(bool(c['flags']) for c in cells), 'snapshot_id': None,
                'coverage': 'unknown', 'validation_status': 'not_independently_validated', 'grid': 'H3 r7'}
    key = json.dumps(filters, sort_keys=True)
    return _summary(str(root().resolve()), manifest['snapshot_id'], key)


@lru_cache(maxsize=32)
def _summary(data_dir, snapshot_id, key):
    clause,args = predicate(**json.loads(key))
    with open_snapshot(snapshot_id) as db:
        db.execute('CREATE TEMP TABLE selected AS SELECT * FROM observations' + clause, args)
        totals = db.execute('SELECT count(*),sum(frp),count(frp),min(acquired_at),max(acquired_at) FROM selected').fetchone()
        sensors = dict(db.execute('SELECT sensor,count(*) FROM selected GROUP BY sensor').fetchall())
        confidence = dict(db.execute('SELECT confidence_class,count(*) FROM selected GROUP BY confidence_class').fetchall())
        days = dictionaries(db.execute('SELECT utc_day AS date,count(*) AS count FROM selected GROUP BY utc_day ORDER BY utc_day'))
        months = dictionaries(db.execute('SELECT month,count(*) AS count FROM selected GROUP BY month ORDER BY month'))
        db.execute('''CREATE TEMP TABLE cells AS SELECT grid_id,utc_day AS date,
            count(*) AS count,count(DISTINCT sensor) sensor_count,
            sum(CASE WHEN sensor='MODIS' THEN 1 ELSE 0 END) modis,
            sum(CASE WHEN sensor='VIIRS' THEN 1 ELSE 0 END) viirs,
            max(CASE WHEN confidence_class='low' THEN 1 ELSE 0 END) low,
            min(scan*track) min_footprint,max(scan*track) max_footprint,
            min(id) evidence_id FROM selected GROUP BY grid_id,utc_day''')
        cell_count, flagged = db.execute('SELECT count(*),count(*) FILTER (WHERE sensor_count=1 OR low=1 OR max_footprint/nullif(min_footprint,0)>4) FROM cells').fetchone()
        cells = dictionaries(db.execute('SELECT * FROM cells ORDER BY low DESC,sensor_count,date DESC,grid_id LIMIT 1000'))
    import h3
    for c in cells:
        lat,lon = h3.cell_to_latlng(c['grid_id'])
        c.update(south=lat,west=lon,cell_area_km2=h3.cell_area(c['grid_id'],unit='km^2'),
                 sensors={k:int(v) for k,v in [('MODIS',c.pop('modis')),('VIIRS',c.pop('viirs'))] if v},
                 flags=(['single_sensor_observation'] if c['sensor_count']==1 else []) + (['low_confidence_present'] if c['low'] else []) + (['footprint_heterogeneity'] if c['min_footprint'] and c['max_footprint']/c['min_footprint']>4 else []),
                 evidence_ids=[c.pop('evidence_id')])
    from .analytics import LIMITS
    return dict(detections=totals[0], frp_mw_sum=(totals[1] or 0) if len(sensors)<=1 else None, frp_observed=totals[2], first_observation=totals[3], last_observation=totals[4],
                sensors=sensors, confidence=confidence, calendar=days, monthly=months, cells=cells,
                cell_count=cell_count, flagged_cell_count=flagged or 0, cell_sample_limit=1000,
                coverage='unknown', validation_status='not_independently_validated', snapshot_id=snapshot_id,
                limitations=LIMITS, grid='H3 resolution 7')


def monthly_series(reference_satellite='N', modis_satellite='T', **filters):
    predicate(**filters)
    manifest=snapshot_manifest()
    if not manifest:
        return {'items':[],'status':'unavailable','reason':'Build the H3 warehouse first.'}
    archive_signature=hashlib.sha256(b''.join(p.read_bytes() for p in sorted((root()/'manifests').glob('country-*.json')))).hexdigest()
    return dict(_monthly(str(root().resolve()),manifest['snapshot_id'],json.dumps(filters,sort_keys=True),reference_satellite,modis_satellite,archive_signature))


@lru_cache(maxsize=32)
def _monthly(data_dir,snapshot_id,key,reference_satellite,modis_satellite,archive_signature):
    filters=json.loads(key)
    clause,args=predicate(**filters)
    manifest={'snapshot_id':snapshot_id}
    with open_snapshot(manifest['snapshot_id']) as db:
        db.execute('CREATE TEMP TABLE selected AS SELECT * FROM observations' + clause,args)
        items = dictionaries(db.execute('''SELECT month,sensor,satellite,processing_status,
            count(*) detection_count,count(DISTINCT (grid_id,utc_day)) active_cell_days,
            'unknown' coverage_status FROM selected GROUP BY ALL ORDER BY month,sensor,satellite,processing_status'''))
        # Union across satellites and day/night; never sum satellite subtotals.
        union = dictionaries(db.execute('''SELECT month,sensor,processing_status,
            count(DISTINCT (grid_id,utc_day)) active_cell_days,count(*) detection_count,
            'unknown' coverage_status FROM selected GROUP BY ALL ORDER BY month,sensor,processing_status'''))
        # First recorded month per satellite ignores the date window, so zero-filling of a month
        # does not depend on which window was requested.
        unwindowed,unwindowed_args=predicate(**{k:v for k,v in filters.items() if k not in {'start','end'}})
        first_recorded=dict(db.execute('SELECT satellite,min(month) FROM observations'+unwindowed+' GROUP BY satellite',unwindowed_args).fetchall())
    items=fill_manifest_zeros(items,filters,first_recorded)
    return {'items': items, 'union_by_sensor': union, 'status': 'available', 'reference_satellite': reference_satellite,
            'modis_satellite': modis_satellite, 'unit': 'H3 r7 active cell days', 'calendar': 'UTC',
            'snapshot_id': manifest['snapshot_id'], 'coverage_status': 'unknown'}


def calendar_matrix(start=None,end=None,view='activity',**filters):
    series = monthly_series(start=start,end=end,**filters)
    summary_data = summary(start=start,end=end,**filters)
    dates = summary_data['calendar']
    first = int(start[:4]) if start else 2000
    last = int(end[:4]) if end else date.today().year
    if not 2000 <= first <= last <= 2100 or last-first>100:
        raise ValueError('calendar years must be between 2000 and 2100 with at most 100 years')
    by_month = defaultdict(list)
    for item in series.get('union_by_sensor',[]):
        by_month[item['month']].append(item)
    cells = []
    for year in range(first,last+1):
        for month in range(1,13):
            key=f'{year:04d}-{month:02d}'
            items=by_month.get(key,[])
            cells.append({'year':year,'month':month,'key':key,'series':items,
                          'active_cell_days':sum(r['active_cell_days'] for r in items) if items and len(items)<=1 else None,
                          'coverage_status':'unknown','processing_status':sorted({r['processing_status'] for r in items}),
                          'model_status':'unavailable','state':'recorded' if items else 'no_records_coverage_unknown'})
    return {'cells':cells,'unit':'active cell days, separately by instrument','view':view,'coverage_status':'unknown',
            'range_observed':[dates[0]['date'],dates[-1]['date']] if dates else [],'snapshot_id':series.get('snapshot_id')}


def anomalies(reference_satellite='N',modis_satellite='T',view='raw',region_id='custom',processing_status='standard',**filters):
    if view not in {'raw','harmonized'}:
        raise ValueError('view must be raw or harmonized')
    predicate(**filters)
    history_filters={k:v for k,v in filters.items() if k not in {'start','end'}}
    series=monthly_series(reference_satellite=reference_satellite,modis_satellite=modis_satellite,**history_filters)
    rows=[r for r in series['items'] if r['processing_status']==processing_status]
    if view=='harmonized':
        from .science import predict_reference
        source=[r for r in rows if r['satellite']==modis_satellite and r['processing_status']==processing_status]
        converted=predict_reference(source,region_id,reference_satellite,modis_satellite,processing_status,
                                    bbox=filters.get('bbox'),country=filters.get('country'))
        if converted['status']!='available':
            return {'items':[],'status':'unavailable','reason':converted['reason'],'view':view}
        rows=[{**r,'active_cell_days':r['estimate'],'sensor':'VIIRS_reference_estimate',
               'satellite':modis_satellite,'reference_satellite':reference_satellite,
               'processing_status':processing_status,'anomaly_uncertainty_status':'not_propagated'}
              for r in converted['items'] if r['model_status']!='extrapolated']
    history=defaultdict(list)
    today=datetime.now(timezone.utc).date()
    for row in rows:
        year,month=map(int,row['month'].split('-'))
        # A current/incomplete archive month is not comparable to full historical months.
        if (year,month)>=(today.year,today.month):
            continue
        history[(row['sensor'],row['satellite'],row['processing_status'],month)].append(row)
    results=[]
    import statistics
    for group,rows in history.items():
        for row in rows:
            beginning=as_utc(row['month']+'-01')
            ending=beginning.replace(year=beginning.year+1,month=1) if beginning.month==12 else beginning.replace(month=beginning.month+1)
            if filters.get('start') and beginning<as_utc(filters['start']):continue
            if filters.get('end') and ending>as_utc(filters['end']):continue
            baseline=[r['active_cell_days'] for r in rows if r['month']!=row['month']]
            if len(baseline)<5:
                continue
            median=statistics.median(baseline)
            mad=statistics.median(abs(x-median) for x in baseline)
            value=row['active_cell_days']; delta=value-median
            results.append({**row,'baseline_median':median,'delta':delta,'baseline_years':len(baseline),
                            'relative_change':delta/median if median>=10 else None,
                            'robust_z':delta/(1.4826*mad) if mad>0 else None,
                            'percentile':sum(x<=value for x in baseline)/len(baseline),
                            'model_status':row.get('model_status','unavailable'),'comparability':'unverified_archive_completeness'})
    return {'items':results,'status':'descriptive_only' if results else 'insufficient_history','view':view,
            'reason':'At least five other completed years for the same calendar month, satellite and processing mode are required.',
            'limitations':['Raw mode is within-mission; harmonized mode compares statistical reference-scale estimates.',
                           'Anomaly uncertainty has not been propagated from activity residual bands.',
                           'Archive and observation coverage must be audited before interpretation.', 'Current partial month is excluded.']}

def fill_manifest_zeros(items,filters,first_by_sat=None):
    country=filters.get('country')
    if not country:
        return items
    manifests=[]
    for path in (root()/'manifests').glob(f'country-{country}-*.json'):
        manifests.append(json.loads(path.read_text(encoding='utf-8')))
    if not manifests:return items
    existing={(r['month'],r['satellite'],r['processing_status']) for r in items}
    if first_by_sat is None:
        first_by_sat={}
        for r in items:
            first_by_sat[r['satellite']]=min(first_by_sat.get(r['satellite'],r['month']),r['month'])
    satellite_for={'modis':['T','A'],'viirs-snpp':['N'],'viirs-jpss1':['N20'],'viirs-jpss2':['N21']}
    output=list(items)
    for manifest in manifests:
        for record in manifest['files'].values():
            if record['archive_query_status']!='complete_file' or record['processing_statuses']!=['standard']:
                continue
            sensor='MODIS' if record['sensor']=='modis' else 'VIIRS'
            if filters.get('sensor') and filters['sensor']!=sensor:continue
            if filters.get('processing_status') and filters['processing_status']!='standard':continue
            for month in range(1,13):
                key=f"{record['year']:04d}-{month:02d}"
                beginning=as_utc(key+'-01')
                ending=beginning.replace(year=beginning.year+1,month=1) if month==12 else beginning.replace(month=month+1)
                if filters.get('start') and ending<=as_utc(filters['start']):continue
                if filters.get('end') and beginning>=as_utc(filters['end']):continue
                for satellite in satellite_for[record['sensor']]:
                    identity=(key,satellite,'standard')
                    if identity in existing or satellite not in first_by_sat or key<first_by_sat[satellite]:continue
                    output.append({'month':key,'sensor':sensor,'satellite':satellite,'processing_status':'standard','detection_count':0,'active_cell_days':0,
                                   'coverage_status':'unknown','archive_status':'complete_country_file_no_matching_records','source_manifest':record['batch_id']})
                    existing.add(identity)
    return sorted(output,key=lambda r:(r['month'],r['sensor'],r['satellite'],r['processing_status']))
