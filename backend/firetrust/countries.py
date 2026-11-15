"""Acquire NASA's indexed annual country archives without inventing file availability."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from .ingestion import connect, download, root
from .warehouse import processing

BASE='https://firms.modaps.eosdis.nasa.gov/data/country/'


def fetch_country(country,start_year,end_year,sensors=('modis','viirs-snpp'),workers=4):
    if not country.replace('_','').isalpha() or not 2000<=start_year<=end_year<=datetime.now().year:
        raise ValueError('invalid country or year range')
    if any(s not in {'modis','viirs-snpp','viirs-jpss1','viirs-jpss2'} for s in sensors):
        raise ValueError('unsupported indexed archive source')
    folder=root()/'manifests';folder.mkdir(exist_ok=True)
    with urllib.request.urlopen(BASE+'yearly_summary_files.txt',timeout=60) as response:
        index=response.read()
    digest=hashlib.sha256(index).hexdigest()
    index_path=folder/f'country-index-{digest}.csv'
    if not index_path.exists():index_path.write_bytes(index)
    listing={r['filename']:r for r in csv.DictReader(io.StringIO(index.decode()))}
    manifest_path=folder/f'country-{country}-{start_year}-{end_year}.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {'country':country,'files':{},'index_sha256':digest,'source':BASE,'created_at':datetime.now(timezone.utc).isoformat()}
    requested=[];unavailable=[]
    for sensor in sensors:
        for year in range(start_year,end_year+1):
            name=f'{sensor}_{year}_{country}.csv'
            if name not in listing:
                unavailable.append(name);continue
            if name in manifest['files']:continue
            requested.append((sensor,year,name))
    def acquire(item):
        sensor,year,name=item
        url=f'{BASE}{sensor}/{year}/{name}'
        result=download(url,url)
        with connect() as db:
            versions=[r[0] for r in db.execute('SELECT DISTINCT version FROM detections d JOIN batch_detections b ON b.detection_id=d.id WHERE b.batch_id=?',(result['id'],))]
        return name,{'sensor':sensor,'year':year,'batch_id':result['id'],'source_uri':url,'accepted':result['accepted'],'rejected':result['rejected'],
                     'listed_updated':listing[name]['updated'],'processing_statuses':sorted({processing(v) for v in versions}),
                     'archive_query_status':'complete_file' if result['rejected']==0 else 'rows_rejected','coverage_status':'unknown'}
    failures=[]
    with ThreadPoolExecutor(max_workers=min(4,max(1,workers))) as executor:
        futures={executor.submit(acquire,item):item for item in requested}
        for future in as_completed(futures):
            try:
                name,record=future.result();manifest['files'][name]=record
                temporary=manifest_path.with_suffix('.tmp');temporary.write_text(json.dumps(manifest,indent=2),encoding='utf-8');temporary.replace(manifest_path)
                print(json.dumps({'country':country,'completed':len(manifest['files']),'file':name,'accepted':record['accepted'],'rejected':record['rejected']}),flush=True)
            except Exception as exc:
                failures.append({'file':futures[future][2],'error':type(exc).__name__})
    manifest['unavailable']=unavailable;manifest['failures']=failures
    manifest_path.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    if failures:
        raise RuntimeError(f'{len(failures)} archive downloads failed; rerun to resume from the saved manifest')
    return {'manifest':str(manifest_path),'files':len(manifest['files']),'failures':failures,'unavailable_count':len(unavailable)}
