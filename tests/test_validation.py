import csv

import pytest

from firetrust.ingestion import ingest_bytes
from firetrust.validation import audit_reference_pairs


def test_independent_audit_detects_wrong_count(payload,tmp_path):
    for sensor,sat,confidence in [('MODIS','Terra','80'),('VIIRS','N','n')]:
        kind='modis' if sensor=='MODIS' else 'viirs-snpp'
        ingest_bytes(payload({'instrument':sensor,'satellite':sat,'confidence':confidence}),f'https://firms.modaps.eosdis.nasa.gov/data/country/{kind}/2024/{kind}_2024_Portugal.csv')
    row=dict(region='pilot',country='Portugal',bbox='-9,39,-7,40',month='2024-01',modis='1',viirs='2',modis_satellite='T',reference_satellite='N')
    pairs=tmp_path/'pairs.csv'
    with pairs.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(row));writer.writeheader();writer.writerow(row)
    with pytest.raises(ValueError,match='count audit failed'):
        audit_reference_pairs(pairs,tmp_path/'audit.json')
