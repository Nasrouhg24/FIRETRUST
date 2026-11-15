import csv
import io

import pytest


@pytest.fixture(autouse=True)
def isolated_data(tmp_path,monkeypatch):
    monkeypatch.setenv('FIRETRUST_DATA_DIR',str(tmp_path/'data'))
    monkeypatch.delenv('FIRMS_MAP_KEY',raising=False)
    monkeypatch.delenv('FIRETRUST_WRITE_TOKEN',raising=False)
    from firetrust.series import _summary,_monthly
    _summary.cache_clear();_monthly.cache_clear()
    yield
    _summary.cache_clear();_monthly.cache_clear()


@pytest.fixture
def payload():
    def create(overrides=None,rows=None):
        base=dict(latitude='39.5',longitude='-8.1',acq_date='2024-01-03',acq_time='0100',satellite='N20',instrument='VIIRS',confidence='n',frp='5',scan='.4',track='.5',daynight='N',version='2',type='0')
        if overrides:base.update(overrides)
        entries=rows if rows is not None else [base]
        output=io.StringIO();writer=csv.DictWriter(output,fieldnames=list(base));writer.writeheader();writer.writerows(entries)
        return output.getvalue().encode()
    return create
