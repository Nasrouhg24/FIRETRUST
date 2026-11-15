# FIRETRUST progress

## 2026-11-14 - delivered local implementation

Verified read/write access at C:\Users\nasre\FIRETRUST. The workspace initially contained only .git. After the owner supplied its path, copied FIRETRUST_Blueprint_2026.md from the OneDrive desktop directory into the project and implemented its count-harmonization design.

### Completed and measured

- [x] Project structure, Python package, React/TypeScript frontend, native PowerShell setup/start/reproduction scripts.
- [x] Real NASA MODIS, NOAA-20/21 public ingestion, area API, resumable historical requests and indexed annual country acquisition.
- [x] Portugal: 26 MODIS annual files (2000-2025) and 14 S-NPP files (2012-2025). Uruguay: eight annual files (2022-2025). No rejected rows in these 48 archive files.
- [x] Raw SHA-256 evidence, manifests, deterministic IDs, deduplication and row diagnostics. All 56 retained batch hashes verified.
- [x] 368,490 deduplicated observations; H3 r7, actual cell areas, DuckDB transforms, partitioned Parquet and unique cell/day unions.
- [x] B0 raw, B1 seasonal ratio, B2 nonnegative Tweedie benchmark; fixed Terra input/S-NPP reference; standard/NRT separation.
- [x] Whole-year train/selection/calibration/test splits, unseen Uruguay test, measured MAE/WAPE/bias/peak/annual diagnostics, residual-band coverage and year-block bootstrap intervals.
- [x] B1 selected on 2020 MAE. B2's subsequent test improvement is reported without changing selection. B1 combined test MAE 80.06 versus B0 100.83 active-cell days/month; empirical band coverage 85.42%, not a guarantee.
- [x] Separate raw-file implementation recomputed all 432 benchmark counts with zero mismatches. This is a pipeline audit, not ground truth.
- [x] FastAPI observations, calendar, series, comparison, anomalies, evidence, method, bounded GeoJSON tiles, streamed raw/aggregate/harmonized CSV; refresh disabled unless authenticated.
- [x] UI coordinate/region/date selection; exact, validated single-ring GeoJSON filtering in the API.
- [x] Calendar activity, harmonized estimate, anomaly and reliability views; PNG/CSV exports. Extrapolation flags and unavailable calibrated intervals stay visible.
- [x] Sensor Illusion Lab with raw/reference/estimated series, residual bands, synchronized month inspection and model diagnostics; separate review-only heuristic detector.
- [x] Evidence ledger/drawer, descriptive decision brief, full-selection totals and explicitly bounded map/cell samples.
- [x] Bundled Natural Earth basemap, responsive layouts, keyboard controls and evidence dialog focus handling.
- [x] 51 backend tests, two desktop/mobile browser tests, TypeScript check and production build passed. Native start script served health and the application with HTTP 200.
- [x] Query indexes, bounded requests, snapshot/filter caches, gzip and streaming. Cold and warm measurements recorded separately in VALIDATION.md.
- [x] README, scientific method, validation, limitations, NASA attribution, AI-use disclosure draft, two-minute demo storyboard, screenshots, measured evidence and ZIP packaging script.

### Engineering decisions and corrections

- Installed workspace-local Python 3.13.9 because the launcher had no interpreter; used npm.cmd for PowerShell execution policy compatibility.
- Windows application control blocked PyArrow's dataset extension. Replaced it with direct DuckDB Parquet writes and removed PyArrow from project dependencies.
- SQLite serves ingestion/point lookups; DuckDB/Parquet serves scientific aggregates. Leaflet with bundled geography replaces the suggested MapLibre stack.
- Supported NASA long-form VIIRS confidence and public CSVs without an explicit instrument column, using brightness schema to identify the instrument.
- Fixed cross-thread CSV-stream cleanup found by browser testing, and optimized measured queries with indexes and snapshot caches.
- Fixed anomaly filtering: target dates no longer remove historical baseline years.
- NASA accepted the owner-supplied mock MAP_KEY in small checks. It was not saved in source/release evidence. Public country archives then supplied the historical pilot without a key.

### Remaining scientific/external work - not claimed complete

- [ ] Ground incident/burned-area validation. A triangulation runner exists, but independent product results have not been supplied or invented.
- [ ] Cloud/overpass masks and verified observation coverage. Current coverage status remains unknown.
- [ ] More ecological/geographic validation, stronger uncertainty calibration and a validated inter-VIIRS continuity bridge.
- [ ] Public hosting/repository, final video, team details and actual NASA submission. Preparation materials are ready; no external publication or submission was performed.

The first uncached calendar request exceeds 500 ms in the measured run. Warm p95 meets the target for this local sequential workload, with no production-load claim. Exact measurements, hashes and evidence links are in VALIDATION.md.
