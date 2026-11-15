# Scientific hardening checkpoint (2026-11-14)

Nothing committed or pushed (repository still has no commits). UI not redesigned. Prior checkpoints: `ENGINEERING_CHECKPOINT.md`, `GLOBAL_AWARDS_PROGRESS.md`. Full numbers: `VALIDATION.md` § "Scientific hardening"; protocols: `METHOD.md` § "Scientific hardening protocols (v0.2)".

## Verified starting baseline
73 tests passing; 78 batches verified. Terra B1 test MAE 80.06 / Aqua B1 42.73, band coverage 85.4% / 92.7%: reproduced exactly. Transfer WAPE Greece 61.7/45.0, Chile 45.8/27.9: reproduced. Zambia was partial (6/8 files).

## Changes
| Area | Change | Evidence |
|---|---|---|
| Ingestion (defect) | Zambia failures were `sqlite3.OperationalError`: 4 threads writing about 800k-row transactions concurrently. Writes are now serialized in-process with a lock; `executemany` batching; HTTP retry (3 attempts, 5xx/network only); Content-Length truncation check. | Zambia 8/8 files, 0 rejected rows; tests for parallel ingest, truncated-retry and give-up |
| Evidence API (defect) | Missing index on `batch_detections(detection_id)` caused full scans at 4.6M rows; this broke the e2e evidence dialog. | 6,036 → 33 ms and 751 → 5 ms; query-plan test |
| Frontend (functional defect) | Leaflet `_leaflet_pos` race on map teardown or view change during animation: `stop()` added before teardown, programmatic re-fits non-animated. No styling change. | e2e failed in 2 of 4 full runs before, passed 4 of 4 after |
| Science | `experiments.py`: nested temporal selection; paired Terra/Aqua comparison with a scale-free ratio; leave-one-region-out with nested band calibration; 6 baselines including S-NPP climatology; activity-stratified errors; interval strata; bootstrap block sensitivity. CLI `science-eval`. | `evidence/science-eval.json` |
| Science | `diagnostics.py`: overpass local solar time and day/night ratio stability by satellite-year. | `evidence/observing-system-diagnostics.json` |
| Model registry | B3 log-linear candidate under the unchanged 2020 rule (not selected); region-year block bootstrap added alongside the 4-block one. | `evidence/pilot-benchmark*.json` |
| Uncertainty | Band withheld when the input exceeds the calibration-year maximum (made one-sided in the final review). | Superseded figures: see `FINAL_SCIENTIFIC_REVIEW.md` (the earlier "100% on 70 kept months" was in-sample on the test that motivated the rule) |

## Key before → after
- **Zambia:** 24 → 48 months. Aqua transfer WAPE 25.2% (partial) → 26.6% (complete); Terra 73.4% → 73.1%.
- **Aqua selection:** previously post hoc. Now nested selection from earlier years only chooses Aqua + log-linear in 10/10 outer Portugal folds. Paired median Terra/Aqua MAE ratio is 1.37 (B1), with 12/15 dependent folds favouring Aqua. On the Zambia 2023–2024 months first acquired after the choice, Aqua WAPE is 27.8% vs Terra 72.8%. Everything else is re-analysis, not an independent holdout.
- **Uncertainty:** "92.7% coverage" was previously the headline. It is now stratified: 50% for high-activity months and 85% in Portugal, with a band-withholding rule evaluated out-of-sample in `FINAL_SCIENTIFIC_REVIEW.md`. The 4-block bootstrap understated width: Aqua [35.0, 49.1] vs region-year [29.4, 57.2].
- **Transfer bias:** previously unexplained. Partly explained by an activity-dependent S-NPP/MODIS ratio; between-region differences at equal activity remain (see `FINAL_SCIENTIFIC_REVIEW.md`). Measured: ratio (falls roughly 3–8× from low- to high-activity months in every region) combined with Portugal's low ratio. Global-ratio, linear and log-linear alternatives were tested under leave-one-region-out; none removes the bias, and log-linear transfers worst. Registered B1 retained.
- **Terra vs Aqua cause:** previously the overpass-time story was implied. Now drift is measured: Terra daytime detections moved from about 11.0 to 9.85 h, and Aqua's from about 13.15 to 14.4 h. But Aqua's advantage predates the drift, and pre-2022 ratio stability is equal. The cause stays unattributed.

## Tests and builds
- `pytest -q -W error::RuntimeWarning`: 87 passed (73 at start; 14 added).
- `npm run build`: passed. `npm run test:e2e`: 2/2 passed in 4 consecutive runs. `compileall`: passed.
- No linter or type checker: PyPI is unreachable from `.runtime` (pip found no ruff or pyflakes distributions).
- Evidence hashes 80/80. Raw-count audits pass, 432/432 counts for both Terra and Aqua pairs. Fixed-split benchmark numbers are identical to the previous evidence.

## Reproduce
```powershell
$env:PYTHONPATH="$PWD\backend"; $py=".\.runtime\python\python.exe"
& $py -m firetrust.cli fetch-country Zambia --start-year 2022 --end-year 2025   # resumes; skips completed files
& $py -m firetrust.cli verify-evidence
& $py -m firetrust.cli build-warehouse
& $py -m firetrust.cli run-pilot --modis T ; & $py -m firetrust.cli run-pilot --modis A
& $py -m firetrust.cli audit-pairs ; & $py -m firetrust.cli audit-pairs artifacts/pilot-pairs-A.csv --output artifacts/raw-count-audit-A.json
& $py -m firetrust.cli transfer-eval --modis A ; & $py -m firetrust.cli transfer-eval --modis T --output artifacts/transfer-eval-T.json
& $py -m firetrust.cli science-eval
& $py -c "from firetrust.diagnostics import run; run()"
& $py -m pytest -q -W error::RuntimeWarning ; npm.cmd run build --prefix frontend ; npm.cmd run test:e2e --prefix frontend
```
Predictions pick the model by MODIS satellite via `data/models/by_modis_satellite.json`. Snapshot `e332e0eb…`: 4,607,351 observations, 80 batches. Pair datasets: Terra `0ff44b414836ca5c…`, Aqua `2ecb4f4553ee5332…` (these changed from earlier IDs only because the snapshot id in `source_manifest` changed; counts are identical).

## Unresolved evidence limits
- No untouched holdout for the Terra/Aqua choice beyond 24 Zambia months. Confirmation needs a region or period acquired after this checkpoint and scored once.
- Aqua's advantage is not causally attributed. Both MODIS platforms drift after 2021.
- Transfer bias remains: every new region is under-predicted by the Portugal-trained model. The activity-dependent ratio is diagnosed but not corrected in a way that transfers.
- Bands carry no conditional coverage guarantee: 12 calibration months, all low-activity. Withheld months are flagged, not modelled.
- No ground truth, cloud masks, overpass-opportunity denominators or VIIRS continuity bridge. Zero counts remain "zero recorded detections, coverage unknown". Land cover was not available and was not used.
- Cold API requests at 4.6M rows exceed 500 ms (calendar 1,081 ms).
