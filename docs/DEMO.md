# Two-minute demo storyboard

Preparation: run `scripts/start.ps1`, open http://127.0.0.1:8000, keep Portugal selected, and check `/api/health`. Use the pinned historical archive rather than refreshing NRT midway. Screenshots and measured evidence live under `docs/evidence` and `artifacts`.

| Time | Action | Accurate narration |
|---|---|---|
| 0:00–0:20 | Open Discover (Portugal). Read the headline; hover the yearly chart | "Not every change in satellite detections is a change in fire. In the years both flew, S-NPP recorded about 2.8 times what MODIS Aqua did over Portugal. Same fires, different instrument." |
| 0:20–0:40 | Click "Switch sensors mid-record", then "Estimated common scale" | "A record that switches instruments inherits that step. The model estimates what S-NPP would have recorded from MODIS. Hatched years are extrapolations nobody can check." |
| 0:40–1:05 | Open Compare. Hover the monthly chart; switch Aqua to Terra | "Month by month: recorded MODIS, recorded VIIRS, and the estimate with its residual band. Aqua had lower error than Terra in everything we tested; we do not know why, and we do not claim it is universal." |
| 1:05–1:25 | Change Region to Greece | "Outside Portugal the band disappears, and the page says why: the Portugal-fitted model ran low here. We show the bias instead of hiding it." |
| 1:25–1:40 | Open Calendar; click a month; switch View to Data availability | "Recorded months, zeros from complete archive files, and months we simply do not hold are drawn differently. Missing is never zero." |
| 1:40–2:00 | Open Evidence; expand "Where it does not work"; Inspect a detection | "Every number traces to NASA source bytes and a SHA-256 hash. Estimates measure agreement with another satellite, not the true amount of fire." |

Keep claims consistent with `VALIDATION.md`; never describe WAPE as classification accuracy. Do not say a flagged point is a false fire. No live operational decision or automatic emergency alert should be demonstrated.

Assets prepared: overview, calendar, sensor lab and mobile screenshots; machine-readable benchmark, raw-count audit, test outputs and performance trace. The browser tests create fresh screenshots and exercise the real local backend. A video has not been recorded and no submission has been sent.
