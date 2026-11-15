"""Independent product triangulation; burned area is never a perfect hotspot label."""
import csv
import hashlib
import json
from datetime import datetime, timezone

import numpy as np
from scipy.stats import spearmanr

from .series import monthly_series


def triangulate(reference,output):
    raw=reference.read_bytes()
    rows=list(csv.DictReader(raw.decode('utf-8-sig').splitlines()))
    required={'month','sensor','satellite','processing_status','burned_area_km2','source_uri','bbox'}
    if not rows or not required.issubset(rows[0]):
        raise ValueError('Independent reference CSV requires '+','.join(sorted(required)))
    matched=[];seen=set()
    for row in rows:
        datetime.strptime(row['month'],'%Y-%m')
        key=(row['month'],row['sensor'],row['satellite'],row['processing_status'],row['bbox'])
        if key in seen:
            raise ValueError('duplicate monthly reference')
        seen.add(key)
        area=float(row['burned_area_km2'])
        if not np.isfinite(area) or area<0 or not row['source_uri'].startswith('https://'):
            raise ValueError('finite nonnegative burned area and independent HTTPS source URI required')
        series=monthly_series(bbox=row['bbox'],sensor=row['sensor'],processing_status=row['processing_status'])
        item=next((x for x in series['items'] if x['month']==row['month'] and x['satellite']==row['satellite']),None)
        if item:
            matched.append({'month':row['month'],'active_cell_days':item['active_cell_days'],'burned_area_km2':area,'source_uri':row['source_uri']})
    if len(matched)<12:
        raise ValueError('At least twelve matched independent monthly observations are required')
    a,b=[m['active_cell_days'] for m in matched],[m['burned_area_km2'] for m in matched]
    rho=float(spearmanr(a,b).statistic) if len(set(a))>1 and len(set(b))>1 else None
    result={'reference_sha256':hashlib.sha256(raw).hexdigest(),'created_at':datetime.now(timezone.utc).isoformat(),
            'matched_months':len(matched),'spearman_rho':rho,'matches':matched,'status':'triangulation_only',
            'limitations':['Burned area and active-cell-day counts measure different quantities.', 'MODIS-derived burned area may share instrument errors; independent product is not necessarily independent sensor.', 'Correlation does not establish accuracy, causation or missed-fire rates.', 'Temporal dependence and seasonal confounding prevent interpreting an unadjusted p-value.']}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result

def audit_reference_pairs(pairs,output):
    """Independent implementation audit; same-source recomputation is not ground truth."""
    from collections import defaultdict
    from pathlib import Path
    import h3
    from .ingestion import connect
    from .warehouse import processing
    targets=list(csv.DictReader(pairs.read_text(encoding='utf-8-sig').splitlines()))
    scopes={r['region']:{'country':r['country'],'bbox':list(map(float,r['bbox'].split(',')))} for r in targets}
    with connect() as db:
        batches=[dict(r) for r in db.execute("SELECT * FROM batches WHERE source LIKE 'https://firms.modaps.eosdis.nasa.gov/data/country/%'")]
    sets=defaultdict(set);sources=[]
    for batch in batches:
        raw=Path(batch['raw_path']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=batch['id']:
            raise ValueError('raw evidence hash mismatch')
        country=batch['source'].rsplit('/',1)[-1].split('_',2)[-1].removesuffix('.csv')
        relevant=[(region,scope) for region,scope in scopes.items() if scope['country']==country]
        if not relevant:continue
        sources.append(batch['id'])
        for row in csv.DictReader(raw.decode('utf-8-sig').splitlines()):
            if processing(row['version'])!='standard':continue
            satellite={'Terra':'T','Aqua':'A','Suomi-NPP':'N'}.get(row['satellite'],row['satellite'])
            lat,lon=float(row['latitude']),float(row['longitude'])
            for region,scope in relevant:
                w,s,e,n=scope['bbox']
                if w<=lon<=e and s<=lat<=n:
                    sets[(region,row['acq_date'][:7],satellite)].add((h3.latlng_to_cell(lat,lon,7),row['acq_date']))
    discrepancies=[]
    for row in targets:
        for field,satellite in [('modis',row['modis_satellite']),('viirs',row['reference_satellite'])]:
            independently_counted=len(sets[(row['region'],row['month'],satellite)])
            if independently_counted!=float(row[field]):
                discrepancies.append({'region':row['region'],'month':row['month'],'field':field,'stored':float(row[field]),'recomputed':independently_counted})
    result={'status':'passed' if not discrepancies else 'failed','checked_monthly_pairs':len(targets),'checked_counts':2*len(targets),
            'raw_source_hashes':sorted(sources),'pair_dataset_sha256':hashlib.sha256(pairs.read_bytes()).hexdigest(),
            'created_at':datetime.now(timezone.utc).isoformat(),'discrepancies':discrepancies,
            'limitations':['Independent code path recomputes the same NASA observations; this is a pipeline audit, not independent ground evidence.', 'H3 library is shared between both implementations.']}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    if discrepancies:raise ValueError('independent raw-file count audit failed; see report')
    return result
