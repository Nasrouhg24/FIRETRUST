# Final independent scientific review (2026-11-14)

Scope: verify that FIRETRUST's conclusions follow from its evidence, and fix substantiated scientific defects. No UI design changes. Nothing committed or published.

## 1. Independent recomputation
A separate script (plain `csv` and arithmetic, no `firetrust` imports) recomputed the fixed-split B1 benchmark from `evidence/pilot-pairs*.csv`. It covered the training ratios with pseudocount 24, the finite-sample 90% calibration quantile, test MAE, WAPE, bias and band coverage. Terra: MAE 80.06, WAPE 0.5557, bias -15.18, coverage 0.8542. Aqua: 42.73, 0.2966, +6.98, 0.9271. These are **identical** to the stored evidence. Raw-count audits: 432/432 for each satellite. Evidence hashes: 80/80. The pair files are byte-identical after re-running the pipeline.

## 2. Defects found and fixed
| # | Defect | Fix | Verification |
|---|---|---|---|
| 1 | The band-withholding rule (previous pass) also withheld bands for months **below** the calibration range (16 Aqua test months), where the constant band was not failing. Its headline "100% coverage on 70 kept months" was measured on the same test set that motivated the rule. | Rule made one-sided (withhold only when input > calibration-year maximum), justified because absolute errors grow with activity. Evaluated **out-of-sample** with a new rolling protocol (`experiments.rolling_band_evaluation`). | Tests `test_band_withheld_outside_calibration_activity` (below-range keeps band), `test_rolling_band_evaluation_is_out_of_fold` |
| 2 | Unseen-region API estimates carried no statement of the measured transfer bias. | `predict_reference` adds a limitation for regions outside training: negative bias in every evaluated transfer region, and no band. Each response states its target is S-NPP-reference counts, "not true fire activity". | `test_unseen_region_limitation_states_measured_bias` |
| 3 | VALIDATION.md implied that overpass time explains Aqua's advantage, but the project's own diagnostics contradict that. | Reworded as motivation only. | — |
| 4 | "Diagnosed cause of transfer bias" overstated the evidence: at equal activity (MODIS 10–100) the S-NPP/Aqua ratio still differs by region (Uruguay 3.2, Portugal 3.7, Greece 4.9, Chile 5.2, Zambia 10.8). | Retitled "measured contributors, not a resolved cause"; between-region effect stated. | — |
| 5 | Submission text described a Portugal-only, Terra-only system. Its AI-use disclosure named an "OpenAI coding agent", although the recent iterations were done by Claude (Anthropic) via Claude Code. | PROJECT.md and README corrected. Aqua claim stated with region-by-region numbers and caveats ("roughly halves" removed: Greece WAPE only falls 61.7% → 45.0%). Disclosure corrected; the team must confirm tools used in earlier iterations. | — |

## 3. Uncertainty: out-of-sample evidence (`evidence/science-eval.json`, `rolling_band_*`)
Protocol: fit on Portugal years < Y−1, calibrate on Y−1 (12 months), score Y; 10 folds (2016–2025). Exploratory, because the data had been inspected before. Months within a fold are dependent.

| | Aqua | Terra |
|---|---:|---:|
| Portugal coverage, all months | 90.8% | 93.3% |
| Portugal: months with band shown (rule) | 92.5% | 94.2% |
| Portugal coverage where shown | 93.7% | 97.3% |
| Portugal coverage on withheld months | 56% | 29% |
| Other regions, coverage all / where shown | 61% / 80% | 54% / 71% |
| By region (Aqua, all months) | Chile 56%, Greece 65%, Uruguay 98%, Zambia 25% | — |

The fixed test is optimistic because it motivated the rule: Aqua shown 86/96 months, 98.8%; Terra 91/96, 89.0%. Alternatives did not beat the constant band in-region. A sqrt-normalized band gave 89% in Portugal; multiplicative bands gave 69% at MODIS <10 and were extremely wide at high activity. **Conclusion:** residual bands are reasonable only for the fitted region (Portugal) within its observed activity range. They are invalid for geographic transfer, which is why unseen regions get none. They describe S-NPP-reference counts, not true fire activity. No method change was justified beyond the one-sided rule.

## 4. Geographic transfer
- **Under-prediction persists:** all 6 region × satellite transfers have negative bias.
- **Leave-one-region-out alternatives:** the global ratio and log-linear models do not remove the bias. The log-linear model transfers worst.
- **Contributors:** the activity-dependent ratio and between-region differences at equal activity both contribute. Neither can be separated from fire regime, land cover or viewing geometry with the available data.
- **Domain rule:** the existing rule is retained, since evidence supports nothing stronger. Unseen region or input outside training support → `extrapolated`, no band, plus the measured-bias limitation.
- **No geographic correction:** none was introduced, because any correction learned from a region would make that region no longer unseen.

## 5. Aqua-versus-Terra claims as now stated
Supported:
- Aqua input had lower error against S-NPP than Terra in every evaluated setting (fixed split, rolling origin, nested selection, transfer).
- Nested selection from earlier years only chooses Aqua in 10/10 Portugal folds.
- Paired median Terra/Aqua MAE ratio: 1.37 (12/15 dependent folds).

Qualified:
- All of this re-uses inspected data except 24 Zambia months (Aqua WAPE 27.8% vs Terra 72.8%; one region).
- Fold-level bootstrap and sign test overstate precision.
- The mechanism is unattributed: Aqua's advantage predates the 2022+ orbit drift, and pre-2022 ratio stability and rank agreement are equal.

Not claimed: true fire counts, ground-truth accuracy, causal attribution, or calibrated intervals for real fire activity.

## 6. Verification
- **Backend:** `pytest -q -W error::RuntimeWarning` 89 passed.
- **Frontend:** build passed; `npm run test:e2e` 2/2 passed.
- **Data integrity:** `verify-evidence` 80/80; Terra and Aqua raw-count audits passed.
- **Reproducibility:** fixed-split metrics are unchanged versus the previous evidence, and the pairs hash (`7fe6aad5…`) is stable across runs.
- **Reproduce:** commands are in `SCIENTIFIC_HARDENING_CHECKPOINT.md`. Running `science-eval` now includes `rolling_band_aqua` and `rolling_band_terra`.

## 7. Readiness assessment
**No critical scientific blocker remains for final UI integration.** The API contract is unchanged, apart from an additive `target` field and limitation strings. `interval_status` can now be `unavailable_outside_calibration_activity`, and the existing UI already renders a null band as "unavailable".

Evidence limitations, not defects:
- **Independent confirmation:** no untouched holdout for the Aqua choice beyond 24 months.
- **Mechanism:** the cause of Aqua's advantage is unattributed.
- **Transfer:** persistent under-prediction with no valid band.
- **Uncertainty:** in-region-only uncertainty, based on 12-month calibration years.
- **Missing data:** no ground truth, cloud or overpass-opportunity data, land cover, or VIIRS continuity bridge.

The UI should keep presenting estimates as S-NPP-reference agreement with these limits visible.
