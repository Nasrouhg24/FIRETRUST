"""Immutable Parquet snapshots and H3 cell-day preaggregates queried with DuckDB."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import h3

from .ingestion import connect, root

RESOLUTION = 7


def processing(version):
    value = version.upper()
    return 'nrt' if 'NRT' in value else 'rt' if 'RT' in value else 'standard' if value and any(c.isdigit() for c in value) else 'unknown'


def build_snapshot():
    with connect() as db:
        batches = [dict(r) for r in db.execute('SELECT * FROM batches ORDER BY id')]
        for country in ('Portugal','Uruguay'):
            db.execute("UPDATE detections SET country=? WHERE country='' AND id IN (SELECT bd.detection_id FROM batch_detections bd JOIN batches b ON b.id=bd.batch_id WHERE b.source LIKE ?)",(country,f'https://firms.modaps.eosdis.nasa.gov/data/country/%_{country}.csv'))
        rows = [dict(r) for r in db.execute('SELECT * FROM detections ORDER BY id')]
    snapshot_id = hashlib.sha256(('h3r7-v3:' + json.dumps([r['id'] for r in batches])).encode()).hexdigest()
    folder = root() / 'warehouse' / snapshot_id
    manifest_path = folder / 'manifest.json'
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding='utf-8'))
    if not rows:
        raise ValueError('no observations available for warehouse snapshot')
    folder.mkdir(parents=True, exist_ok=True)
    for row in rows:
        cell = h3.latlng_to_cell(row['latitude'], row['longitude'], RESOLUTION)
        row.update(grid_id=cell, cell_area_km2=h3.cell_area(cell, unit='km^2'),
                   utc_day=row['acquired_at'][:10], month=row['acquired_at'][:7], year=int(row['acquired_at'][:4]),
                   processing_status=processing(row['version']), coverage_status='unknown')
    normalized = folder / 'normalized.jsonl'
    with normalized.open('w', encoding='utf-8') as stream:
        for row in rows:
            stream.write(json.dumps(row) + '\n')
    with duckdb.connect() as db:
        numeric={'latitude','longitude','frp','scan','track','cell_area_km2'}
        schema={k:('DOUBLE' if k in numeric else 'BIGINT' if k=='year' else 'VARCHAR') for k in rows[0]}
        schema_sql='{'+','.join(f"'{k}':'{v}'" for k,v in schema.items())+'}'
        db.execute(f'CREATE TABLE observations AS SELECT * FROM read_json(?, columns={schema_sql})', [str(normalized)])
        observation_path = str(folder / 'observations').replace("'", "''")
        db.execute(f"COPY observations TO '{observation_path}' (FORMAT PARQUET, PARTITION_BY (sensor,year), COMPRESSION ZSTD, OVERWRITE_OR_IGNORE)")
        daily_path = str(folder / 'cell_day_sensor.parquet').replace("'", "''")
        db.execute(f"""COPY (SELECT grid_id, cell_area_km2, utc_day, month, satellite, sensor, daynight,
            processing_status, count(*) detection_count, sum(frp) frp_sum_raw, 1 active_flag,
            'unknown' coverage_status FROM observations GROUP BY ALL) TO '{daily_path}' (FORMAT PARQUET, COMPRESSION ZSTD)""")
        monthly_path = str(folder / 'monthly.parquet').replace("'", "''")
        db.execute(f"""COPY (SELECT month,sensor,satellite,daynight,processing_status,
            count(*) detection_count,count(DISTINCT (grid_id,utc_day)) active_cell_days,
            'unknown' coverage_status FROM observations GROUP BY ALL) TO '{monthly_path}' (FORMAT PARQUET, COMPRESSION ZSTD)""")
    normalized.unlink()
    files = {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.rglob('*.parquet'))}
    manifest = {'snapshot_id': snapshot_id, 'created_at': datetime.now(timezone.utc).isoformat(),
                'rows': len(rows), 'h3_resolution': RESOLUTION, 'calendar': 'UTC', 'batches': batches, 'files': files,
                'units': 'active_cell_days: unique H3 cell / UTC date pairs; not fire counts or burned area'}
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    pointer = root() / 'warehouse' / 'latest.json'
    temporary = pointer.with_suffix('.tmp')
    temporary.write_text(json.dumps({'snapshot_id': snapshot_id}), encoding='utf-8')
    temporary.replace(pointer)
    return manifest


def snapshot_manifest():
    pointer = root() / 'warehouse' / 'latest.json'
    if not pointer.exists():
        return None
    identity = json.loads(pointer.read_text(encoding='utf-8'))['snapshot_id']
    return json.loads((pointer.parent / identity / 'manifest.json').read_text(encoding='utf-8'))


def preaggregates():
    manifest = snapshot_manifest()
    if not manifest:
        raise ValueError('build a warehouse snapshot first: python -m firetrust.cli build-warehouse')
    path = root() / 'warehouse' / manifest['snapshot_id'] / 'monthly.parquet'
    with duckdb.connect() as db:
        cursor = db.execute('SELECT * FROM read_parquet(?) ORDER BY month,sensor,satellite,daynight', [str(path)])
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
