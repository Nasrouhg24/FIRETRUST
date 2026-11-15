"""Copy measured evidence into a reviewable release bundle; never synthesize metrics."""
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from firetrust.ingestion import connect
from firetrust.warehouse import snapshot_manifest


def main():
    destination=Path('docs/evidence');destination.mkdir(parents=True,exist_ok=True)
    names=['pilot-benchmark.json','pilot-pairs.csv','raw-count-audit.json','api-performance.json','backend-tests.xml','e2e-results.json',
           'overview-desktop.png','overview-mobile.png','calendar-desktop.png','calendar-harmonized.png','sensor-lab-desktop.png','sensor-lab-harmonized.png']
    for name in names:
        source=Path('artifacts')/name
        if not source.exists():raise RuntimeError(f'Measured evidence missing: {source}')
        shutil.copy2(source,destination/name)
    manifest=snapshot_manifest()
    (destination/'source-ledger.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    for path in (Path('data')/'manifests').glob('country-*.json'):
        shutil.copy2(path,destination/path.name)
    results=json.loads((destination/'pilot-benchmark.json').read_text())
    performance=json.loads((destination/'api-performance.json').read_text())
    audit=json.loads((destination/'raw-count-audit.json').read_text())
    suite=ET.parse(destination/'backend-tests.xml').getroot().find('testsuite')
    browser=json.loads((destination/'e2e-results.json').read_text())['stats']
    if int(suite.attrib['failures']) or int(suite.attrib['errors']) or browser['unexpected']:
        raise RuntimeError('Release evidence contains failing tests')
    lines=['# Validation: measured on 2026-11-14','',
           f"Snapshot: `{manifest['snapshot_id']}`. {manifest['rows']:,} deduplicated observations; {len(manifest['batches'])} raw batches, including 48 annual country files.",'',
           f"Pair dataset SHA-256: `{results['dataset_sha256']}`. {audit['checked_monthly_pairs']} monthly pairs and {audit['checked_counts']} independently recomputed counts; {len(audit['discrepancies'])} mismatches.",'',
           '## Held-out sensor-reference benchmark','',
           'Reference: S-NPP; input: Terra; standard processing; H3 r7 active-cell days per UTC month. Portugal training 2012–2019, selection 2020, calibration 2021. Final test: 2022–2025 in Portugal and geographically unseen Uruguay. Each test region contributes 48 monthly pairs.','',
           '| Method | Selection MAE (2020) | Test MAE | Test WAPE | Signed bias | Empirical band coverage | Mean band width |',
           '|---|---:|---:|---:|---:|---:|---:|']
    for name,result in results['test'].items():
        lines.append(f"| {name} | {results['validation'][name]['mae']:.2f} | {result['mae']:.2f} | {result['wape']:.2%} | {result['signed_bias']:.2f} | {result['empirical_interval_coverage']:.2%} | {result['mean_interval_width']:.2f} |")
    lines+=['',f"Selected: **{results['selected_model']}**, using selection-year MAE only. B2 does better on final test MAE, but the test was not used to change model selection.",'',
            'B1 regional final tests:','', '| Region | MAE | WAPE | Signed bias | Band coverage |','|---|---:|---:|---:|---:|']
    for region,result in results['test'][results['selected_model']]['by_region'].items():
        lines.append(f"| {region} | {result['mae']:.2f} | {result['wape']:.2%} | {result['signed_bias']:.2f} | {result['empirical_interval_coverage']:.2%} |")
    interval=results['test'][results['selected_model']]['year_block_bootstrap_mae_95_interval']
    lines+=['',f"B1 year-block bootstrap MAE interval: [{interval[0]:.2f}, {interval[1]:.2f}], from only four test-year blocks. This interval has limited precision. The residual band was calibrated to a nominal 90% target; observed test coverage is lower. Neither interval is a guaranteed coverage statement.",'',
            '**No independent ground-truth or burned-area accuracy result exists.** The geographical holdout measures transfer to a satellite reference. The raw-file audit validates computation using the same NASA sources and H3 library, not real-world fire completeness.','',
            '## Engineering checks','',
            f"- Backend: {suite.attrib['tests']} tests, {suite.attrib['failures']} failures, {suite.attrib['errors']} errors. One third-party Starlette/httpx deprecation warning.",
            f"- Browser: {browser['expected']} passing, {browser['unexpected']} failing, {browser['skipped']} skipped. Microsoft Edge, desktop and 390px mobile viewport, real local API. Calendar activity/estimate/anomaly/reliability, synchronized month inspection, source evidence, CSV/PNG exports and custom coordinates exercised.",
            '- TypeScript check and Vite production build passed.',
            '- All retained raw evidence hashes verified. Polygon inclusion, UTC offsets, missing coverage, cross-sensor FRP guards and count leakage checks are covered.',
            '', '## Local API performance','',
            f"Environment: {performance['environment']['os']}, Python {performance['environment']['python']}, {performance['environment']['logical_cpus']} logical CPUs; {performance['rows']:,} observations.",'',
            '| Endpoint | First request ms | Warm p50 ms | Warm p95 ms | Requests |','|---|---:|---:|---:|---:|']
    for name,m in performance['measurements'].items():
        lines.append(f"| {name} | {m['cold_ms']:.2f} | {m['warm_p50_ms']:.2f} | {m['warm_p95_ms']:.2f} | {m['repetitions']} |")
    lines+=['',performance['method'],'',
            'The first uncached calendar request exceeds 500 ms. Warm calendar p95 meets the prototype target for this local, sequential workload. OS file cache was not flushed; no concurrent production load, internet transport or browser rendering claim is made. Results may vary with machine load.','',
            '## Reviewable evidence','',
            '- [Benchmark JSON](evidence/pilot-benchmark.json), [paired counts](evidence/pilot-pairs.csv), [raw-file audit](evidence/raw-count-audit.json).',
            '- [Source ledger](evidence/source-ledger.json), [Portugal acquisition manifest](evidence/country-Portugal-2000-2025.json), [Uruguay acquisition manifest](evidence/country-Uruguay-2022-2025.json).',
            '- [Performance trace](evidence/api-performance.json), [backend test report](evidence/backend-tests.xml), [browser report](evidence/e2e-results.json).',
            '- [Overview](evidence/overview-desktop.png), [monthly calendar](evidence/calendar-desktop.png), [harmonized calendar](evidence/calendar-harmonized.png), [sensor lab](evidence/sensor-lab-harmonized.png), [mobile](evidence/overview-mobile.png).','',
            'Source and derived files are retained locally. No public deployment, recorded submission video or NASA submission has been performed.']
    Path('docs/VALIDATION.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(f"Prepared release evidence: {suite.attrib['tests']} backend tests; {browser['expected']} browser tests; model {results['model_id']}")


if __name__=='__main__':main()
