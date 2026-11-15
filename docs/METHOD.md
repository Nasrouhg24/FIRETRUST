# Scientific method, version 0.1

## Observation processing

FIRMS CSVs retain their original bytes and SHA-256 hash. Parsing checks finite WGS84 coordinates, UTC date/time, instrument, satellite, confidence scheme, nonnegative optional FRP/footprint values and day/night flag. Invalid rows are counted with line-number diagnostics. Valid observations have deterministic IDs; overlapping files retain batch-to-observation links without multiplying observations. Missing optional FRP is null, not zero. `type` remains available as `type_raw`; the pilot does not exclude industrial, volcanic or agricultural detections.

Satellite aliases are normalized to T, A, N, N20 and N21. Numeric MODIS confidence is classified low below 30, nominal below 80, and high otherwise. VIIRS l/n/h and low/nominal/high spellings map to its own classes. These are quality tiers, not cross-sensor probabilities. Processing versions containing NRT or RT remain distinct from standard archive versions. FRP is retained in MW; a combined multi-instrument FRP total is not supplied as a harmonized measurement.

## Spatial and temporal unit

H3 resolution 7 indexes detections, retaining each cell's actual area in km². For any one mission and UTC month:

`active_cell_days = count(distinct (H3 cell, UTC date))`.

Union across satellites and day/night categories is computed from cell-day pairs rather than by adding mission subtotals. The harmonization benchmark itself fixes Terra as input and S-NPP as reference. A higher active-cell-day count is not evidence of more independent fires.

Annual country files restrict data to the source country. The Portugal pilot additionally clips to west/south/east/north `-9.6,36.8,-6,42.2`; Uruguay uses `-58.5,-35,-53,-30`. The country restriction and rectangle both apply. The pilot excludes Portugal's offshore islands. These are different spatial supports from an arbitrary rectangle containing other countries.

Absent monthly rows remain unknown. A downloaded complete annual country file with no rejected rows can establish **zero recorded matching hotspots**, with `coverage_status=unknown`; it cannot establish a fire-free or cloud-free month. The earliest mission month with records is treated conservatively when filling archive-backed zero records. Empty or unsupported observation-coverage products are never invented.

## Count harmonization

- **B0:** raw Terra active-cell days, labeled unharmonized.
- **B1:** regional/calendar-month ratio, shrunk toward the global training ratio. With training counts M and V and global ratio R, each regional/month ratio is `(sum(V) + 24 R) / (sum(M) + 24)`. The pseudocount 24 is a fixed engineering choice, not a test-tuned optimum. A zero MODIS input predicts zero under this baseline.
- **B2:** Tweedie regression, power 1.5, log link, alpha 1.0. Features are standardized log(1+MODIS count), sine/cosine of calendar month and region encoding. Predictions are nonnegative. Biome, cloud and orbital covariates are not supplied.

Portugal training: 2012–2019 (96 monthly pairs). Model selection: 2020 (12). Interval calibration: 2021 (12). Final test: 2022–2025, Portugal and unseen Uruguay (96). Whole-year separation is checked; duplicate months, negative/nonfinite/noninteger counts, mixed processing/reference missions and incomplete region-years are rejected. Final test data never selects the model.

B1 is selected because its 2020 MAE is smaller. B2's better subsequent test MAE is reported rather than used to retrospectively change selection. These observations do not establish that B1 will generalize best elsewhere.

## Error and uncertainty

Reports include MAE, WAPE, signed bias, peak-month concordance, annual total bias, and regional diagnostics. WAPE is null for a zero target denominator. Error intervals resample whole test years, retaining both regions within each sampled year; four blocks provide limited precision.

Absolute residuals on 2021 define a finite-sample-corrected nominal 90% calibration quantile, with a nonnegative lower endpoint. These are **empirical residual bands**, not guaranteed probability intervals: adjacent months are dependent and a geographically shifted test violates exchangeability. Their actual test coverage and widths are reported. Counterfactual predictions outside training count support, before the reference period or in an unseen region are marked extrapolated and receive **no calibrated interval**. Other predictions remain `low_support`, not automatically `validated`.

## Review flags and anomalies

The detector flags a cell/day when one instrument is recorded, any low-confidence observation is present, or the ratio of largest to smallest available scan×track footprint exceeds four. This threshold is a review heuristic with no validated false-fire interpretation. The response and interface distinguish a bounded cell sample from full-selection counts.

Descriptive anomalies compare the same satellite, processing mode and calendar month to at least five other completed years. The target year is excluded. The baseline is the median; robust z uses 1.4826×MAD when MAD is positive; relative change is supplied only when the baseline is at least ten active-cell days. The current partial month is excluded. Date filters restrict complete target months, not the historical baseline, and honor the exclusive end boundary. Raw mode compares within-mission counts; harmonized mode compares reference-scale model estimates and excludes extrapolated inputs. Activity-band uncertainty is not propagated into anomaly deltas. Neither mode establishes causal changes or forecasts. Archive and cloud/overpass comparability remain unverified.

## Independent checks

Uruguay is geographically held out of fitting, selection and interval calibration. A separate implementation reads raw NASA country CSVs, recomputes the benchmark's H3 sets directly and compares every stored monthly count. That audit checks computation using the **same** underlying observations. An optional independent-product triangulation command accepts documented burned-area references, reports rank association and explicitly avoids interpreting burned area as a perfect hotspot label. No such external product results have been supplied or claimed.

## Input-satellite choice and rolling-origin evaluation

Benchmarks are run separately for Terra (`run-pilot --modis T`) and Aqua (`--modis A`); the registry keeps one model per MODIS input satellite and `predict_reference` loads the model matching the requested satellite (otherwise `unavailable`). `rolling_origin` evaluates B0/B1 with an expanding window: each fold fits on whole earlier years of the same region (at least three) and forecasts one later year; it is reported beside, never instead of, the fixed split. Results and caveats are in VALIDATION.md. The web application now defaults to Aqua because it has the lower held-out error in these two regions, not because Aqua is established as universally better.

## Scientific hardening protocols (v0.2)

- **Selection status.** All Terra/Aqua comparisons re-use data inspected when Aqua was first considered. They are reported as exploratory/post-selection evidence. Only Zambia S-NPP 2023–2024, acquired afterwards, had not been inspected; it is one region.
- **Pre-specified registry rule (unchanged).** Fixed split train ≤2019, selection 2020, calibration 2021, test 2022–2025. Candidates B1, B2 and B3 (log-linear `log1p(V)=a+b·log1p(M)` with Duan smearing); the smallest 2020 MAE wins. B3 was added after the nested analysis and was not selected.
- **Nested temporal evaluation** (`experiments.nested_temporal`). Outer year Y; the satellite × candidate is chosen by one-year-ahead rolling-origin MAE on years < Y (≥3 training years). Band radii are calibrated on those inner residuals only. Y is never used for selection or calibration.
- **Leave-one-region-out** (`experiments.leave_one_region_out`). Fit on the other regions' 2022–2025 months; band radius from an inner leave-one-region-out among the training regions. Calendar years are shared, so this measures geographic transfer only.
- **Band applicability.** A residual band is shown only when the model is not extrapolating and the MODIS input does not exceed the calibration year's maximum input (one-sided: absolute errors grow with activity); otherwise `interval_status=unavailable_outside_calibration_activity`. Bands are empirical residual bands for the S-NPP-reference count, not confidence intervals for true fire activity.
- **Baselines** (`experiments.CANDIDATES`): raw MODIS, global ratio, seasonal ratio (B1), linear, log-linear, and S-NPP same-month climatology (ignores MODIS).
- **Months used.** Only months for which the archive supplies both satellites (recorded or archive-backed zero) are used. Failed or missing archive files never produce zeros (test `test_failed_archive_file_never_zero_filled`). Archive-backed zero still means zero recorded detections with unknown observation coverage. No cloud or overpass-opportunity masks are used. VIIRS continuity (S-NPP → NOAA-20/21) is not modelled.
- **Diagnostics** (`diagnostics.overpass_and_daynight`): median local solar time of detections (UTC + longitude/15) and day/night ratio stability per satellite-year. These are associations, not orbital ephemerides.
- **Seeds and units.** Benchmark seed 42; paired bootstrap seed 42 (5,000 draws); block sensitivity seed 42 (2,000 draws). Unit: H3 r7 active-cell days per UTC month.
