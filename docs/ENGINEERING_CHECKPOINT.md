# Engineering checkpoint — audit, repair and verification (2026-11-14)

State recovered: Git repository with **no commits**; all work untracked. Source of truth: `docs/PROGRESS.md`, `docs/submission/CHECKLIST.md`, `docs/METHOD.md`, `docs/LIMITATIONS.md`, `FIRETRUST_Blueprint_2026.md`. Nothing was committed, pushed or deleted. No UI styling changed; no frontend source changed.

## Defects fixed (7)

| # | Subsystem | Defect (#1, #2, #5 reproduced by probe before fixing; #3, #4, #6, #7 found by code inspection) | Fix | Regression test |
|---|---|---|---|---|
| 1 | Ingestion | A CSV row with fewer fields than the header raised uncaught `AttributeError` (None `.strip()`), aborting the whole batch before any evidence was recorded. | `normalize` rejects rows whose field count differs from the header (short rows, and surplus fields that `DictReader` stores under key `None`); `AttributeError` also quarantined. | `test_short_and_surplus_rows_are_quarantined_not_fatal` |
| 2 | Ingestion | Rows with surplus fields were silently accepted. | Same check as #1. | same |
| 3 | Ingestion | `acq_time` used `str.isdigit()`, which accepts non-ASCII digits. | Require ASCII digits. | `test_non_ascii_digit_time_rejected` |
| 4 | Ingestion | `fetch_area` error text was mojibake and said "1–10 days" while the code enforces 1–5. | Message corrected to "1-5 days". | `test_area_request_day_limit_message` |
| 5 | Science/API | `anomalies(view='raw')` ignored `processing`: `processing=nrt` returned the standard-processing anomalies (verified on real Portugal data: 752 standard rows returned for `nrt`). | Raw rows filtered by the requested processing status. | `test_anomalies_honor_processing_status` |
| 6 | Science/data | Archive zero-filling used the first record month *within the requested date window*, so the same month could be zero in one query and unknown in another. | First recorded month per satellite is computed without the date window (`series._monthly` → `fill_manifest_zeros(first_by_sat=…)`). No differing result was observed on the real data before the fix (window test of Uruguay 2023 matched); the fix removes the logical dependence. Real-data counts unchanged (pilot reproduces exactly). | `test_zero_fill_does_not_depend_on_requested_window` |
| 7 | API | `/api/v1/exports/csv?mode=aggregate` ignored the `processing` parameter the UI sends; bbox of wrong arity gave "not enough values to unpack"; `/api/v1/areas/validate` allowed unbounded SQLite growth. | Aggregate export filtered by `processing`; clear bbox error; stored areas capped at 10,000 (HTTP 507, replay of a stored area still succeeds). | `test_aggregate_export_honors_processing_filter`, `test_bbox_wrong_arity_has_clear_error`, `test_stored_area_limit` |

Also: `pyproject.toml` now declares `joblib` and `scipy`, which the code imports directly (previously transitive via scikit-learn; both already pinned in `requirements.lock.txt`).

Files changed: `backend/firetrust/{ingestion,series,api}.py`, `pyproject.toml`, `tests/{test_ingestion,test_warehouse,test_api,test_science}.py`, `docs/VALIDATION.md` (test count), this file.

## Tests executed (actual results)

- `python -m pytest -q`: **70 passed, 0 failed** (51 pre-existing + 19 added). One third-party Starlette/httpx deprecation warning.
- Added coverage: malformed/short/surplus rows, window-independent zero-fill, processing-status filtering, aggregate-export filter, area cap, frontend/backend field contract, benchmark determinism for a fixed seed, invalid/negative/non-finite/non-integer counts, duplicate months, mixed processing, nonnegative predictions, extrapolation flags (unseen region, out-of-support input), registered-scope mismatch → unavailable, split leakage ordering.
- `npm run build` (`tsc -b && vite build`): passed.
- `npm run test:e2e` (Playwright, Microsoft Edge, real local API and real archive data): **2 passed, 0 failed**.
- `python -m compileall` over backend, scripts, tests: passed. No Python linter/type checker (ruff/mypy/pyflakes) is installed in `.runtime`; none was run.
- `firetrust verify-evidence`: 56 batches, 0 hash failures.
- `firetrust build-warehouse`: snapshot `29bb16c7…` reused (368,490 rows, deterministic).
- `firetrust run-pilot` after the fixes: benchmark JSON (excluding `created_at`) and `pilot-pairs.csv` are **identical** to `docs/evidence/` — every reported metric reproduces.
- `firetrust audit-pairs`: passed, 216 pairs / 432 counts, 0 discrepancies.
- `scripts/benchmark_api.py` and `scripts/package_submission.py` ran successfully (outputs in `artifacts/`, git-ignored). Secret scan of the source tree: none found.

## Verified behavior / verification boundary

- Counts are active-cell-days (distinct H3 r7 cell × UTC date), unioned not summed across satellites/day-night; mixed-instrument FRP sums are `null`.
- Absent months stay `unknown`; zero is only emitted from complete archive country files, after a satellite's first recorded month, and now independently of the query window.
- Models: whole-year chronological splits enforced, Uruguay unseen in fit/selection/calibration; selection uses 2020 MAE only; estimates nonnegative; extrapolated/unseen-region outputs carry no calibrated interval; scope/satellite/processing mismatch yields `unavailable`.
- **Not verified and not claimed:** ground-truth/burned-area accuracy, cloud/overpass coverage, inter-VIIRS continuity, interval coverage guarantees (B1 empirical test coverage 85.42% vs 90% nominal), live NASA download (no network call or MAP_KEY used in this run), public hosting/submission. The 4-block bootstrap MAE interval has limited precision (already stated in `docs/METHOD.md`).

## Checklist (`docs/submission/CHECKLIST.md`)

The 8 checked items remain supported by the evidence above (app starts and serves; hashes verified; benchmark reproduces; ground-truth absence stated; docs/evidence present; e2e passes; ZIP script runs). The 4 unchecked items are owner/external actions and remain unchecked. No item was added, removed or weakened.

## Unresolved blockers

- None blocking code. Items in `docs/LIMITATIONS.md` need scientific evidence not present in the repository (ground validation, coverage products, continuity bridge) and were left guarded/labelled rather than invented.

## Reproduce

```powershell
.\.runtime\python\python.exe -m pytest -q
npm.cmd run build --prefix frontend
npm.cmd run test:e2e --prefix frontend
$env:PYTHONPATH="$PWD\backend"
.\.runtime\python\python.exe -m firetrust.cli verify-evidence
.\.runtime\python\python.exe -m firetrust.cli build-warehouse
.\.runtime\python\python.exe -m firetrust.cli run-pilot      # compare artifacts/pilot-benchmark.json with docs/evidence/ (ignore created_at)
.\.runtime\python\python.exe -m firetrust.cli audit-pairs
```
