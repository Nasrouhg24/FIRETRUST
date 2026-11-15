"""Shared bounded filters and transparent, descriptive detection analytics."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import datetime

from .ingestion import connect

LIMITS = ["Detections are not burned area or unique fires.", "No cloud or overpass coverage denominator is available.", "Sensor confidence classes are not calibrated probabilities.", "FRP sums from different instruments are not harmonized and must not be compared directly.", "Cross-sensor differences are review flags, not proven false positives."]


def query(start=None, end=None, sensor=None, bbox=None, limit=5000, offset=0,country=None,area_id=None):
    from .series import predicate
    clause, values = predicate(start=start,end=end,sensor=sensor,bbox=bbox,country=country,area_id=area_id)
    with connect() as db:
        total = db.execute('SELECT count(*) FROM detections' + clause, values).fetchone()[0]
        rows = db.execute('SELECT * FROM detections' + clause + ' ORDER BY acquired_at DESC,id LIMIT ? OFFSET ?', [*values, limit, offset]).fetchall()
    return {'total': total, 'items': [dict(r) for r in rows], 'limit': limit, 'offset': offset, 'truncated': total > offset + len(rows)}


def summarize(rows):
    daily = Counter(r['acquired_at'][:10] for r in rows)
    monthly = Counter(r['acquired_at'][:7] for r in rows)
    frp = [r['frp'] for r in rows if r['frp'] is not None]
    return {'detections': len(rows), 'sensors': dict(Counter(r['sensor'] for r in rows)),
            'confidence': dict(Counter(r['confidence_class'] for r in rows)),
            'frp_mw_sum': sum(frp) if len({r['sensor'] for r in rows})<=1 else None, 'frp_observed': len(frp),
            'calendar': [{'date': k, 'count': v} for k, v in sorted(daily.items())],
            'monthly': [{'month': k, 'count': v} for k, v in sorted(monthly.items())],
            'first_observation': min((r['acquired_at'] for r in rows), default=None),
            'last_observation': max((r['acquired_at'] for r in rows), default=None), 'limitations': LIMITS}


def harmonize(rows, cell_degrees=None):
    import h3
    cells = defaultdict(list)
    for row in rows:
        key=(row['acquired_at'][:10],h3.latlng_to_cell(row['latitude'],row['longitude'],7))
        cells[key].append(row)
    result=[]
    for (day,grid),members in sorted(cells.items()):
        sensors=Counter(r['sensor'] for r in members)
        flags=[]
        if len(sensors)==1: flags.append('single_sensor_observation')
        if any(r['confidence_class']=='low' for r in members): flags.append('low_confidence_present')
        footprints=[r['scan']*r['track'] for r in members if r['scan'] and r['track']]
        if footprints and max(footprints)/min(footprints)>4: flags.append('footprint_heterogeneity')
        lat,lon=h3.cell_to_latlng(grid)
        result.append({'date':day,'grid_id':grid,'south':lat,'west':lon,'cell_area_km2':h3.cell_area(grid,unit='km^2'),
                       'count':len(members),'sensors':dict(sensors),'flags':flags,
                       'evidence_ids':[r['id'] for r in members]})
    return result


def analytics(**filters):
    from .series import summary
    return summary(**filters)
