"""Resumable bounded archive acquisition and explicit monthly-pair preparation."""
from __future__ import annotations

import csv
import hashlib
import json
import os
from datetime import date, timedelta
from pathlib import Path

from .ingestion import fetch_area, root
from .series import monthly_series


def fetch_history(source,bbox,start,end):
    if not os.getenv('FIRMS_MAP_KEY'):
        raise ValueError('Historical NASA API acquisition requires FIRMS_MAP_KEY. Import downloaded official archive CSVs as an alternative.')
    first,last=date.fromisoformat(start),date.fromisoformat(end)
    if first>=last:
        raise ValueError('start must be before exclusive end')
    identity=hashlib.sha256(json.dumps([source,bbox,start,end]).encode()).hexdigest()
    checkpoint=root()/'jobs'/f'{identity}.json'
    checkpoint.parent.mkdir(exist_ok=True)
    state=json.loads(checkpoint.read_text(encoding='utf-8')) if checkpoint.exists() else {'source':source,'bbox':bbox,'start':start,'end':end,'completed':{}}
    day=first
    while day<last:
        days=min(5,(last-day).days)
        key=day.isoformat()
        if key not in state['completed']:
            result=fetch_area(source,bbox,days,key)
            state['completed'][key]={'batch_id':result['id'],'days':days,'accepted':result['accepted'],'rejected':result['rejected']}
            temporary=checkpoint.with_suffix('.tmp')
            temporary.write_text(json.dumps(state,indent=2),encoding='utf-8')
            temporary.replace(checkpoint)
        day+=timedelta(days=days)
    return {'job':identity,'windows':len(state['completed']),'checkpoint':str(checkpoint),'coverage_status':'unknown'}


def prepare_pairs(region,bbox,reference,modis,processing,validation_year,calibration_year,test_year,output):
    if not validation_year<calibration_year<test_year:
        raise ValueError('whole-year boundaries must be validation < calibration < test')
    series=monthly_series(bbox=bbox,processing_status=processing)
    months={}
    for row in series['items']:
        if (row['sensor']=='VIIRS' and row['satellite']==reference) or (row['sensor']=='MODIS' and row['satellite']==modis):
            months.setdefault(row['month'],{})[row['sensor']]=row['active_cell_days']
    today=date.today().strftime('%Y-%m')
    rows=[]
    for month,values in sorted(months.items()):
        if set(values)!={'VIIRS','MODIS'} or month>=today:
            continue
        year=int(month[:4])
        split='train' if year<validation_year else 'validation' if year<calibration_year else 'calibration' if year<test_year else 'test'
        rows.append({'region':region,'month':month,'modis':values['MODIS'],'viirs':values['VIIRS'],'split':split,
                     'reference_satellite':reference,'modis_satellite':modis,'processing_status':processing,'source_manifest':series['snapshot_id']})
    if not rows:
        raise ValueError('No completed monthly pairs available. Acquire overlapping historical archives; current live feeds are insufficient.')
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    return {'output':str(output),'pairs':len(rows),'snapshot_id':series['snapshot_id'],
            'limitations':['Only months with records from both fixed satellites exported.', 'Missing archive months were not assigned zeros.', 'Completeness and spatial-region overlap need external audit.']}
