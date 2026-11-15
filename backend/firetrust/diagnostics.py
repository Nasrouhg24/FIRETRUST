"""Observing-system diagnostics from detection metadata (associations, not causal attribution)."""
import json
from pathlib import Path

import duckdb
import numpy as np

from .ingestion import root
from .warehouse import snapshot_manifest


def _observations():
    manifest = snapshot_manifest()
    if not manifest:
        raise ValueError('build a warehouse snapshot first')
    path = str(root() / 'warehouse' / manifest['snapshot_id'] / 'observations' / '**' / '*.parquet').replace("'", "''")
    db = duckdb.connect()
    db.execute(f"CREATE VIEW o AS SELECT * FROM read_parquet('{path}', hive_partitioning=true) WHERE processing_status='standard'")
    return db, manifest['snapshot_id']


def overpass_and_daynight(country='Portugal', bbox=(-9.6, 36.8, -6.0, 42.2), first_year=2012, last_year=2025):
    """Per satellite/year/day-night: median local solar time of detections (UTC + longitude/15 h) and H3 r7
    active-cell days; annual S-NPP/MODIS ratios by pass type. Local solar time of *detections* reflects overpass
    timing and swath geometry together; it is not an orbital ephemeris."""
    db, snapshot = _observations()
    w, s, e, n = bbox
    rows = db.execute('''SELECT satellite, year, daynight, count(*) detections,
        count(DISTINCT (grid_id, utc_day)) active_cell_days,
        median(((CAST(substr(acquired_at,12,2) AS DOUBLE)+CAST(substr(acquired_at,15,2) AS DOUBLE)/60+longitude/15)+48)%24) median_local_solar_hour
        FROM o WHERE country=? AND longitude BETWEEN ? AND ? AND latitude BETWEEN ? AND ? AND year BETWEEN ? AND ?
        GROUP BY ALL ORDER BY satellite, daynight, year''', [country, w, e, s, n, first_year, last_year]).fetchall()
    table = {}
    for sat, year, dn, det, acd, lst in rows:
        table.setdefault(sat, {}).setdefault(dn, {})[int(year)] = {'detections': det, 'active_cell_days': acd, 'median_local_solar_hour': round(float(lst), 3)}
    ratios = {}
    for sat in ('T', 'A'):
        for dn in ('D', 'N'):
            series = {y: table['N'][dn][y]['active_cell_days'] / v['active_cell_days']
                      for y, v in table.get(sat, {}).get(dn, {}).items() if y in table.get('N', {}).get(dn, {}) and v['active_cell_days']}
            def cv(years):
                values = [series[y] for y in years if y in series]
                return float(np.std(values, ddof=1) / np.mean(values)) if len(values) > 2 else None
            ratios[f'{sat}-{dn}'] = {'annual_snpp_over_modis': {y: round(r, 3) for y, r in sorted(series.items())},
                                     'cv_2012_2021': cv(range(2012, 2022)), 'cv_2022_2025': cv(range(2022, 2026))}
    return {'snapshot_id': snapshot, 'scope': {'country': country, 'bbox': list(bbox)}, 'by_satellite': table,
            'ratio_stability': ratios,
            'interpretation_limits': ['Associations only: overpass drift, sensor ageing, fire-regime change and processing cannot be separated with these data.',
                                      'Ratios use annual active-cell days; low-count night passes are noisy.']}


def run(output=Path('artifacts/observing-system-diagnostics.json')):
    result = overpass_and_daynight()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result
