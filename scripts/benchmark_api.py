"""Measure actual local ASGI latency, with clearly separated cold and cached calls."""
import json
import os
import platform
import statistics
import time
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from firetrust.api import app
from firetrust.series import _summary,_monthly
from firetrust.warehouse import snapshot_manifest


def main():
    client=TestClient(app)
    endpoints={
        'calendar':'/api/v1/calendar?bbox=-9.6,36.8,-6,42.2&country=Portugal',
        'analytics':'/api/analytics?bbox=-9.6,36.8,-6,42.2&country=Portugal',
        'timeseries':'/api/v1/timeseries?bbox=-9.6,36.8,-6,42.2&country=Portugal&processing=standard',
        'points_5000':'/api/detections?bbox=-9.6,36.8,-6,42.2&country=Portugal&limit=5000'}
    measurements={}
    for name,url in endpoints.items():
        _summary.cache_clear();_monthly.cache_clear();t=time.perf_counter();first=client.get(url);cold=(time.perf_counter()-t)*1000
        if first.status_code!=200:raise RuntimeError(f'{name} failed with {first.status_code}')
        values=[]
        for _ in range(30):
            t=time.perf_counter();response=client.get(url);values.append((time.perf_counter()-t)*1000)
            if response.status_code!=200:raise RuntimeError(f'{name} request failed')
        measurements[name]={'cold_ms':cold,'warm_p50_ms':float(np.quantile(values,.5)),'warm_p95_ms':float(np.quantile(values,.95)),
                            'repetitions':30,'response_bytes':len(first.content),'analytics_cache':str(_summary.cache_info()),'series_cache':str(_monthly.cache_info())}
    manifest=snapshot_manifest()
    report={'environment':{'os':platform.platform(),'python':platform.python_version(),'logical_cpus':os.cpu_count(),'processor':platform.processor()},
            'rows':manifest['rows'],'snapshot_id':manifest['snapshot_id'],'measurements':measurements,
            'method':'Sequential FastAPI TestClient ASGI requests; includes serialization, excludes TCP/TLS and browser rendering. Warm analytics cache enabled; monthly series and analytics caches enabled after the first call.',
            'cache_info':str(_summary.cache_info()),'limits':['Single-user local measurements; not a production load test.','Cold OS file cache was not flushed.']}
    output=Path('artifacts/api-performance.json');output.parent.mkdir(exist_ok=True);output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
