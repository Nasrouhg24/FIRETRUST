# Limits and remaining scientific work

- There is no ground-truth, incident-record or independent burned-area accuracy validation. Uruguay provides independent geographical evaluation against a fixed satellite reference, not truth about real fires.
- FIRMS detections include thermal anomalies from vegetation, agriculture, volcanoes and fixed sources. Active-cell days are not ignition counts, fire perimeters or burned hectares.
- No swath fire masks, cloud denominators or overpass quality products have been acquired. Coverage stays unknown, including archive-backed zero recorded counts.
- Standard and NRT products are not pooled for model calibration. Current live feeds are snapshots, not complete global history. Portugal and Uruguay cannot represent every biome.
- H3 r7 is fixed rather than optimized. Results depend on spatial support, boundary assignment and temporal aggregation. Large or different custom areas are outside calibrated regional support.
- B1's test WAPE is substantial and its residual band's measured coverage falls below the nominal calibration target. Four test-year blocks and one calibration year provide limited uncertainty evidence.
- No inter-VIIRS continuity model has been validated. Selecting NOAA-20/21 with an S-NPP model yields an unavailable conversion, rather than silently reusing its calibration.
- Counterfactual pre-reference/unseen-region estimates are extrapolations with unavailable calibrated intervals. They are not reconstructed observations.
- The detector has review heuristics, not verified classifications of sensor illusions. Anomalies are either within-mission raw comparisons or descriptive model-estimate comparisons; uncertainty in anomaly deltas has not been propagated. Incomplete-month adjustments beyond excluding the current month are not implemented.
- The map displays up to 5,000 recent matching points; summaries use the full selection. Cell evidence is sampled to 1,000 cells; exports state this. Raw CSV export is limited to 250,000 rows per request; tiles to 1,000 points. The source ledger displays the latest 100 batches.
- Polygon filtering supports one closed, non-self-intersecting ring, no holes, no antimeridian crossing, and at most 500 vertices. Approximate spherical area validates request size; point inclusion follows straight longitude/latitude segments.
- Performance measurements are sequential local ASGI tests, not internet latency or concurrent production load. The first uncached calendar request exceeds the blueprint's 500 ms target on the measured run; warm p95 is reported separately.
- Historical sources can change upstream. Retained raw hashes and the release source ledger define this experiment. New download revisions require a new benchmark.
- The frontend is a local application. There is no public hosting, recorded submission video or NASA submission. The supplied submission text and demo storyboard are preparation materials.

Further work should prioritize coverage products, more independently held-out ecological regions, external incident/burned-area triangulation, multiple calibration years, and a separately validated S-NPP-to-NOAA continuity bridge.
