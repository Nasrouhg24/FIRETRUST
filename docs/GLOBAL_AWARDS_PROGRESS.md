# Global Awards progress checkpoint (2026-11-14)

> Superseded for science and backend by `SCIENTIFIC_HARDENING_CHECKPOINT.md` (Zambia now complete; selection-bias, transfer and interval analyses added).

## Baseline (start of this pass)
70 backend tests, 2 e2e tests, build passing; Terra→S-NPP only; B1 selected on 2020; test MAE 80.06 (WAPE 55.6%), Uruguay 94.0, band coverage 85.4% (<90% nominal). Nothing committed.

## Most consequential weakness found
The only input sensor was Terra (~10:30 overpass) against S-NPP (~13:30). Raw annual S-NPP/Terra ratios are unstable (Uruguay 4.4–10.2) while S-NPP/Aqua is stable (2.9–3.4): part of the "sensor illusion" is overpass-time/orbit effect, which a Terra-based single ratio cannot absorb.

## Changes
- `pilot.py`/`cli.py`: `run-pilot --modis T|A`; `transfer-eval` command (scores the registered model on unseen countries, never refits).
- `science.py`: `rolling_origin` expanding-window evaluation (fit only on earlier whole years); per-MODIS-satellite model registry (`by_modis_satellite.json`); `predict_reference` loads the matching model, else `unavailable`.
- Frontend: Calendar and Sensor Lab default MODIS input changed Terra→Aqua (one-word state defaults; no styling).
- Data: real NASA country archives added: Greece, Chile 2022–2025 (complete), Zambia 2022–2025 partial (6/8 files; rerun `fetch-country Zambia --start-year 2022 --end-year 2025` to resume).
- Tests: 73 backend (+3), rolling-origin leakage test, registry test, transfer guard.

## Measured comparison (details and caveats in docs/VALIDATION.md)
| | Terra B1 | Aqua B1 |
|---|---:|---:|
| Test MAE / WAPE (PT+UY, 2022–25) | 80.06 / 55.6% | 42.73 / 29.7% |
| Unseen Uruguay MAE | 94.0 | 26.6 |
| Band coverage (nominal 90%) | 85.4% | 92.7% |
| Rolling-origin mean MAE (12 folds) | 80.8 | 55.7 (better in 9/12 folds) |
| Unseen Greece / Chile / Zambia* WAPE | 61.7 / 45.8 / 73.4% | 45.0 / 27.9 / 25.2% |
*Zambia partial (24 months).

## Verification
pytest 73 passed (re-run at end, see below); frontend build and 2 Edge e2e passed after the UI default change (before data expansion; no frontend change since); evidence hashes 78/78; raw-count audits 432/432 for Terra and Aqua pairs.

## Honest limitations
- Aqua-vs-Terra is a post-hoc contrast: the 2020 selection year favours Terra; the Aqua idea came from inspecting ratios that include test years. Rolling origin and three unseen regions support it but reuse the same period (2022–2025 for transfer).
- Cause (overpass time vs orbit drift vs processing) is not isolated. No ground truth, cloud/overpass masks or inter-VIIRS bridge exist. Transfer models under-predict (negative bias) in all new regions. Zambia incomplete. Aqua also drifts after 2022; not modelled.
- No UI redesign or new Sensor Illusion visual was built in this pass; existing detector remains a review heuristic.

## Resume
Pytest: `.\.runtime\python\python.exe -m pytest -q`. Pipeline: `build-warehouse`, `run-pilot --modis A`, `run-pilot --modis T`, `audit-pairs [artifacts/pilot-pairs-A.csv --output ...]`, `transfer-eval --modis A`. Next candidates: finish Zambia; seasonal/biome-stratified ratios; display ratio-stability evidence in the UI.
