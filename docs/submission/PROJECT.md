# FIRETRUST — Fire, in context

## Project description

FIRETRUST helps an analyst distinguish changing satellite observations from changing fire activity. It joins a historical NASA FIRMS archive, a fixed-reference statistical comparison and an evidence ledger in a local scientific atlas.

Our demonstrator contains Portugal's MODIS records from November 2000 and S-NPP records from 2012–2025, plus 2022–2025 MODIS and S-NPP archives for Uruguay, Greece, Chile and Zambia. It aggregates detections into unique H3 cell/day pairs, preserving satellite, processing version and source hashes. A monthly calendar and Sensor Illusion Lab compare raw observations with a statistical estimate of a fixed VIIRS mission's scale. Missing coverage remains explicitly unknown.

We benchmark raw MODIS, a seasonal ratio and a nonnegative Tweedie model using disjoint years for fitting, selection, interval calibration and final testing. Uruguay is geographically excluded from fitting. The selected ratio model improves combined held-out MAE over raw MODIS. Using Aqua instead of Terra as the MODIS input gave lower held-out error against the S-NPP reference in every evaluated region (fixed-split test MAE 80.1 → 42.7 for Portugal + Uruguay; transfer WAPE from 61.7% → 45.0% in Greece to 73.1% → 26.6% in Zambia); this comparison re-uses data we had already inspected, the reason for the difference is not established, and a model fitted in Portugal under-predicts in every other region. Error and uncertainty limitations remain substantial: residual bands are only reliable within the fitted region and activity range, and estimates measure agreement with another satellite, not the true amount of fire. The interface exposes those limitations rather than calling an anomaly a forecast or a sensor difference a proven false detection.

## Measured evidence

See `../VALIDATION.md` and `../evidence/pilot-benchmark.json` for exact test metrics, regions, years and dataset hash. A separate raw-file computation matched all 432 benchmark counts. Automated backend tests and desktop/mobile browser tests cover ingestion, deduplication, scientific guardrails, filtering, provenance and exports.

## NASA data use

NASA FIRMS annual MODIS and S-NPP country CSVs form the historical pilot. Live MODIS and NOAA-20/21 feeds demonstrate NRT ingestion separately. Original files and processing metadata remain traceable. Data sources and NASA's disclaimer are linked in `../DATA_SOURCES.md`.

## Honest limitations and next steps

This is a research prototype. We have not validated against ground incident records or independent burned-area products, nor measured cloud/overpass coverage. The geographical sample is limited. We do not claim exact numbers of fires, burned area, operational risk prediction or guaranteed interval coverage. Future work will add those independent checks and validate continuity across VIIRS missions.

## Submission preparation status

Source, local demonstration, screenshots, method, validation evidence and a two-minute storyboard are prepared. A public repository URL, public demo URL, team details and recorded video must be supplied by the owner if required by the event. Check the applicable official challenge and local event requirements before submission. No deadline, eligibility determination, endorsement or successful submission is asserted here.

## AI-use disclosure draft

AI coding agents assisted with implementation, documentation and test execution; the most recent iterations used Anthropic's Claude via Claude Code. The team should confirm which tools were used in earlier iterations. Scientific numbers in the evidence bundle were computed from retained NASA data; they are not generated example results. Engineering tests use explicitly synthetic fixtures in isolated temporary directories. Team members should review the implementation and tailor this disclosure to the event's actual requirements.
