# Validation: measured on 2026-11-14

Snapshot: `29bb16c78537e47fb7ed962aa2d8951376eb0743e27780221c906bd9234c7745`. 368,490 deduplicated observations; 56 raw batches, including 48 annual country files.

Pair dataset SHA-256: `acac8b050323fb899ae3b24c60c52d6feb12e5eab00397dbacaeb2fa5d53734c`. 216 monthly pairs and 432 independently recomputed counts; 0 mismatches.

## Held-out sensor-reference benchmark

Reference: S-NPP; input: Terra; standard processing; H3 r7 active-cell days per UTC month. Portugal training 2012–2019, selection 2020, calibration 2021. Final test: 2022–2025 in Portugal and geographically unseen Uruguay. Each test region contributes 48 monthly pairs.

| Method | Selection MAE (2020) | Test MAE | Test WAPE | Signed bias | Empirical band coverage | Mean band width |
|---|---:|---:|---:|---:|---:|---:|
| B0_raw_modis | 80.17 | 100.83 | 69.98% | -100.83 | 89.58% | 265.71 |
| B1_shrunk_ratio | 24.82 | 80.06 | 55.57% | -15.18 | 85.42% | 215.89 |
| B2_tweedie | 47.62 | 69.86 | 48.49% | 16.49 | 84.38% | 230.14 |

Selected: **B1_shrunk_ratio**, using selection-year MAE only. B2 does better on final test MAE, but the test was not used to change model selection.

B1 regional final tests:

| Region | MAE | WAPE | Signed bias | Band coverage |
|---|---:|---:|---:|---:|
| portugal_mainland | 66.11 | 44.17% | 37.04 | 89.58% |
| uruguay | 94.01 | 67.89% | -67.40 | 81.25% |

B1 year-block bootstrap MAE interval: [65.30, 93.96], from only four test-year blocks. This interval has limited precision. The residual band was calibrated to a nominal 90% target; observed test coverage is lower. Neither interval is a guaranteed coverage statement.

**No independent ground-truth or burned-area accuracy result exists.** The geographical holdout measures transfer to a satellite reference. The raw-file audit validates computation using the same NASA sources and H3 library, not real-world fire completeness.

## Engineering checks

- Backend: 70 tests, 0 failures, 0 errors (re-run 2026-11-14 after the engineering audit; see ENGINEERING_CHECKPOINT.md). One third-party Starlette/httpx deprecation warning.
- Browser: 2 passing, 0 failing, 0 skipped. Microsoft Edge, desktop and 390px mobile viewport, real local API. Calendar activity/estimate/anomaly/reliability, synchronized month inspection, source evidence, CSV/PNG exports and custom coordinates exercised.
- TypeScript check and Vite production build passed.
- All retained raw evidence hashes verified. Polygon inclusion, UTC offsets, missing coverage, cross-sensor FRP guards and count leakage checks are covered.

## Local API performance

Environment: Windows-11-10.0.26200-SP0, Python 3.13.9, 24 logical CPUs; 368,490 observations.

| Endpoint | First request ms | Warm p50 ms | Warm p95 ms | Requests |
|---|---:|---:|---:|---:|
| calendar | 676.39 | 11.09 | 14.15 | 30 |
| analytics | 374.22 | 45.61 | 66.66 | 30 |
| timeseries | 369.65 | 15.66 | 16.89 | 30 |
| points_5000 | 273.66 | 296.29 | 426.08 | 30 |

Sequential FastAPI TestClient ASGI requests; includes serialization, excludes TCP/TLS and browser rendering. Warm analytics cache enabled; monthly series and analytics caches enabled after the first call.

The first uncached calendar request exceeds 500 ms. Warm calendar p95 meets the prototype target for this local, sequential workload. OS file cache was not flushed; no concurrent production load, internet transport or browser rendering claim is made. Results may vary with machine load.

## Reviewable evidence

- [Benchmark JSON](evidence/pilot-benchmark.json), [paired counts](evidence/pilot-pairs.csv), [raw-file audit](evidence/raw-count-audit.json).
- [Source ledger](evidence/source-ledger.json), [Portugal acquisition manifest](evidence/country-Portugal-2000-2025.json), [Uruguay acquisition manifest](evidence/country-Uruguay-2022-2025.json).
- [Performance trace](evidence/api-performance.json), [backend test report](evidence/backend-tests.xml), [browser report](evidence/e2e-results.json).
- [Overview](evidence/overview-desktop.png), [monthly calendar](evidence/calendar-desktop.png), [harmonized calendar](evidence/calendar-harmonized.png), [sensor lab](evidence/sensor-lab-harmonized.png), [mobile](evidence/overview-mobile.png).

Source and derived files are retained locally. No public deployment, recorded submission video or NASA submission has been performed.

## Input-satellite comparison: Terra versus Aqua (added in the Global Awards pass)

Same protocol, splits, reference (S-NPP), H3 grid and code; only the MODIS input differs. Aqua's nominal overpass (~13:30) is closer to S-NPP's than Terra's (~10:30); this motivated the comparison but is **not** shown to explain the result (see Observing-system diagnostics below). Files: `evidence/pilot-benchmark.json` (Terra), `evidence/pilot-benchmark-A.json` (Aqua), `evidence/raw-count-audit-A.json`.

| Input | Selected | Selection MAE (2020) | Test MAE | Test WAPE | Bias | Uruguay (unseen) MAE | Band coverage |
|---|---|---:|---:|---:|---:|---:|---:|
| Terra, B1 | B1 | 24.82 | 80.06 | 55.6% | -15.2 | 94.0 | 85.4% |
| Aqua, B1 | B1 | 32.28 | 42.73 | 29.7% | +7.0 | 26.6 | 92.7% |

Rolling-origin check (expanding window, B1/B0 fit only on earlier whole years, 12 region-year folds: Portugal 2015–2025, Uruguay 2025): mean MAE Terra B0 121.1 / B1 80.8; Aqua B0 117.0 / B1 55.7. Aqua B1 beats Terra B1 in 9 of 12 folds. B1 beats raw counts in 12/12 folds with Aqua and 10/12 with Terra.

Raw annual S-NPP/Terra count ratio in Uruguay ranges 4.4–10.2 (2022–2025); S-NPP/Aqua ranges 2.9–3.4. Portugal's S-NPP/Terra ratio ranges 1.95–6.88 over 2012–2025.

**Caveats (do not omit):** (1) The 2020 selection year alone does *not* favour Aqua (B1 MAE 32.3 vs 24.8). (2) The overpass-time rationale was stated from instrument knowledge, but the decision to compare Aqua was prompted by inspecting annual ratios that include test years, so the Terra-vs-Aqua contrast is a post-hoc comparison, partly supported by the rolling-origin folds (which still reuse the same two regions and years). (3) No cause is established; overpass time, orbit drift, sensor degradation and processing differences are not separated. (4) Both sensors are compared with S-NPP, not with ground truth. (5) Two regions only.

## Transfer to additional regions (no refitting)

Greece, Chile and Zambia: whole countries, 2022–2025, standard processing, public NASA archives; Zambia now complete (8/8 files, 0 rejected rows; the earlier 2/8 failures were SQLite write-lock errors, fixed). The Portugal-trained registered model is applied as is (unseen region → global ratio, flagged extrapolated, no band). Files: `evidence/transfer-eval.json` (Aqua), `evidence/transfer-eval-T.json` (Terra).

| Region | Months | Aqua model WAPE / bias | Terra model WAPE / bias |
|---|---:|---:|---:|
| Greece | 48 | 45.0% / -63.8 | 61.7% / -93.2 |
| Chile | 48 | 27.9% / -29.1 | 45.8% / -229.5 |
| Zambia | 48 | 26.6% / -5,543 | 73.1% / -24,715 |

All six region × satellite results under-predict (negative bias); see "Scientific hardening" below for the diagnosis. These regions and years were inspected in the previous pass, so they are **post-selection evidence**, not untouched holdouts. Exception: Zambia S-NPP 2023 and 2024 were first acquired after Aqua was chosen; on those 24 months Aqua WAPE 27.8% vs Terra 72.8% (`evidence/zambia-2023-2024-first-acquired.json`), one region only.

## Scientific hardening (2026-11-14, `firetrust.cli science-eval`, `evidence/science-eval.json`)

All analyses re-use previously inspected observations and are labelled `exploratory_reanalysis_of_previously_inspected_data`. 720 monthly region × satellite pairs, snapshot `e332e0eb…` (4,607,351 observations, 80 batches, all hashes verified).

**Fixed-split benchmark reproduces exactly** after adding data and code: Terra B1 test MAE 80.06, Aqua B1 42.73 (all previously reported B0/B1/B2 numbers unchanged). New candidate B3 (log-linear) was **not** selected by the unchanged 2020 rule (Terra 55.5 vs B1 24.8; Aqua 42.4 vs B1 32.3) and is worse than B1 on Aqua's test (46.6 vs 42.7). Registered models remain B1.

**Nested temporal selection (Portugal, outer years 2016–2025).** For each outer year, satellite × candidate {raw, global ratio, seasonal ratio B1, linear, log-linear, S-NPP climatology} was chosen by rolling-origin MAE on earlier years only. Aqua + log-linear was selected in 10/10 outer folds. Mean outer MAE: selected 42.0; fixed Aqua log-linear 42.0, Aqua linear 48.2, Aqua B1 54.2, Terra log-linear 54.2, Terra B1 77.6, raw 112.2, climatology 154.8. MODIS therefore adds information beyond a S-NPP climatology. The fixed split and the nested protocol disagree on B1 vs log-linear; the difference is not conclusive.

**Paired Aqua-vs-Terra (rolling origin, same months, 15 region-year folds).** Aqua better in 12/15 (B1) and 12/15 (log-linear); median Terra/Aqua MAE ratio 1.37 (bootstrap 1.05–1.64) for B1, 1.31 (1.02–1.58) for log-linear; sign test p = 0.035. Folds are dependent, so these precision figures are optimistic. Mean count differences are dominated by Zambia and are not used. In Portugal the advantage exists before the orbit drift (log-linear 7/7 folds 2015–2021) and is smaller after (2/4 folds 2022–2025).

**Leave-one-region-out (2022–2025, nested band calibration).** Aqua global ratio WAPE: Chile 34%, Greece 43%, Uruguay 26%, Zambia 25%, Portugal 76% (raw counts are better for Portugal). Terra global ratio is worse than raw counts in 4/5 regions because pooled Terra ratios vary 2.3–11.8 by region (Aqua 2.3–4.2). Log-linear transfers worse than the global ratio in every region and fails in Zambia (46% of months outside the training input range).

**Transfer bias: measured contributors, not a resolved cause.** (a) The S-NPP/Aqua ratio falls with activity in every region (Portugal 13.4 for monthly MODIS <10, 3.7 for 10–100, 1.7 for 100–1000; Zambia 10.8 → 7.2 → 3.4), so a single ratio cannot be unbiased across different activity mixes. (b) At *equal* activity the ratio still differs between regions (MODIS 10–100: Uruguay 3.2, Portugal 3.7, Greece 4.9, Chile 5.2, Zambia 10.8), so activity mix alone does not explain the under-prediction. (c) Portugal 2022–2025 has the lowest pooled ratio (2.33). Region-level effects (fire size distribution, land cover, viewing geometry) are not separable with these data; no geographic correction is applied.

**Interval reliability.** Aqua B1's 92.7% aggregate coverage hides 50% coverage for high-activity test months (n=12) and 85% in Portugal. The 2021 calibration year contains only low-activity months, so the band is now withheld when the MODIS input exceeds the calibration year's maximum (`interval_status = unavailable_outside_calibration_activity`; one-sided after the final review, because below-range constant bands were not under-covering). *Fixed test (the same test that motivated the rule, so optimistic):* Aqua band shown for 86/96 months, coverage 98.8%, withheld 10 (would-be 40%); Terra 91/96, 89.0%, withheld 5 (20%). *Out-of-sample rolling evaluation* (`rolling_band_aqua/terra` in `evidence/science-eval.json`; fit < Y-1, calibrate Y-1, score Y, 10 folds 2016–2025): Portugal, Aqua — coverage 90.8% overall, 93.7% where shown (band shown for 92.5% of months), 56% on withheld months; Terra — 93.3% overall, 97.3% where shown (shown for 94.2%), 29% withheld. Other regions (temporal + geographic): Aqua 61% overall, 80% where shown; overall by region Chile 56%, Greece 65%, Uruguay 98%, Zambia 25% — residual bands are **not** valid outside the fitted region, which is why unseen-region estimates receive none. Alternative shapes: a sqrt-normalized band did not improve Portugal coverage (89%) and multiplicative bands under-cover low activity (Portugal MODIS <10: 69%) while becoming extremely wide at high activity; the constant band plus the upper-bound rule is retained. Coverage holds only for the fitted region, the observed activity range and the S-NPP reference; it is not a statement about true fire activity.

**Bootstrap block sensitivity (Aqua B1 MAE 42.7).** Year blocks (4) [35.0, 49.1]; region-year (8) [29.4, 57.2]; region-quarter (32) [28.3, 59.6]; iid months [30.4, 58.7]. The four-block interval is the narrowest and understates uncertainty; benchmark reports now include the region-year interval as well. No resampling unit gives a reliable interval with four test years.

**Observing-system diagnostics (Portugal, `evidence/observing-system-diagnostics.json`).** Median local solar time of daytime detections: S-NPP 12.8–13.2 h throughout; Terra 10.9–11.1 h 2012–2021 then 10.8, 10.6, 10.3, 9.85 h (2022–2025); Aqua 13.1–13.2 h then 13.2, 13.4, 13.5, 14.4 h. Day-only S-NPP/MODIS annual ratio CV 2012–2021: Terra 0.171, Aqua 0.171; 2022–2025: Terra 0.255, Aqua 0.182. Monthly log-count Spearman with S-NPP 2012–2021: Terra 0.934, Aqua 0.941. Interpretation: both MODIS platforms drift after 2021 (consistent with their known end-of-mission orbits) and Terra's ratio destabilises more; but before 2022 the two have equal ratio stability and similar rank agreement, yet Aqua already has lower count-weighted error. **The mechanism of Aqua's advantage is not isolated**; overpass time, drift, swath geometry and fire diurnal cycle remain confounded.

## Engineering checks after hardening

87 backend tests pass (runtime warnings as errors); 2/2 Edge e2e tests pass in 4 consecutive full runs after fixing a Leaflet animation race; frontend build passes. Evidence lookup index: `/api/evidence` 6,036 ms → 33 ms (first) and 751 ms → 5 ms (warm) at 4.6 M observations. API cold/warm (ms, 4.6 M rows): calendar 1,081 / p95 11.5; analytics 563 / 60.9; timeseries 609 / 15.5; points 260 / 271.9. Cold requests exceed the 500 ms prototype target.
