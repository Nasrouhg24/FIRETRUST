# Final UI checkpoint (2026-11-15)

Nothing committed, pushed, deployed or submitted. No scientific model, split, calibration or benchmark result was changed. Science baseline: `FINAL_SCIENTIFIC_REVIEW.md`.

## Original baseline (screenshots in `docs/evidence/ui-baseline/`)
- Admin-dashboard shell: sidebar, breadcrumb, avatar, and four metric cards (one permanently "Pending") repeated on every tab.
- The opening screen was a dot map; the project's message was never stated.
- The signature chart overplotted 25 years of three monthly series with no hover readout, above a 100-row table of flagged cells.
- Only Portugal and Uruguay were selectable, although Greece, Chile and Zambia are in the archive.
- Caveats lived in amber notice boxes, not next to the numbers. Google Fonts were loaded over the network.
- A latent bug from an earlier fix: `fitBounds` ran even for an invalid custom bounding box.

## Design decisions
- **Journey as navigation:** Discover → Explore → Compare → Calendar → Evidence in a top bar, with one global region selector (five archived regions plus custom area).
- **One message first:** "Not every change in satellite detections is a change in fire." The first screen proves it with live archive data.
- **Entity colours, validated:** orange = MODIS input, blue = S-NPP recorded, aqua = model estimate, yellow = second MODIS satellite. All four pass the dataviz validator on the dark surface (lightness band, chroma, colour-blind separation, contrast). Text never wears series colour.
- **Typography:** system serif for display, system sans for text, monospace for figures. No remote fonts, so the app is fully offline.
- **Trust beside the result:** a region-aware note sits under every estimate, with numbers served from the reviewed evidence files.
- **Progressive disclosure:** plain-language captions first; tables, method and validation behind "View as table", "How it was computed" and the Evidence screen.

## Screens and components
| File | Content |
|---|---|
| `frontend/src/api.ts` | Regions, types, one-request-per-URL cache, series derivation, complete-year annual totals (partial years never scaled) |
| `frontend/src/charts.tsx` | `AnnualChart` (three illusion modes), `MonthlyChart` (crosshair tooltip, residual band, pinned month), `LineChart`, legends |
| `frontend/src/shared.tsx` | `IllusionPanel`, `TrustNote`, unit explainer, loading and error states |
| `Discover.tsx` | Headline, live illusion chart, three findings computed from the API, journey links |
| `Explore.tsx` | Map (MODIS and VIIRS coloured separately), instrument/date/custom-area filters, totals line, empty state |
| `Compare.tsx` | Sensor Illusion Detector: yearly illusion, monthly comparison with series toggles and keyboard month slider, S-NPP÷MODIS ratio chart for Aqua and Terra, held-out results, "can / cannot conclude", method details |
| `CalendarView.tsx` | Year × month grid; views: recorded, estimate, difference from typical, data availability; month detail panel; legend; PNG and CSV export |
| `Evidence.tsx` | What an estimate is; benchmark tables for both satellites; transfer and band-coverage tables; overpass-time chart; unusual months; review flags; source ledger; exports |
| `App.tsx`, `styles.css` | Shell, evidence drawer with focus trap, visual system |
| Removed | `ScienceViews.tsx` (replaced) |

Backend, additive only: `GET /api/v1/validation` serves a read-only summary of `docs/evidence/*.json` (nothing is computed); `GET /api/v1/method?modis=T|A` returns either registered model. Two tests added.

## Scientific trust in the UI
- **Portugal:** the residual band is drawn only where the API supplies one. The note states its out-of-sample coverage where shown (Aqua 94%, Terra 97%) and that it is not an interval for true fire.
- **Other regions:** no band. The note states the measured bias and error share for that region and satellite (for example Greece, Aqua: low by 63.8 active cell-days a month, 45% of the S-NPP total), and that a band would have covered S-NPP in only 61% of months outside Portugal.
- **Custom areas:** stated as unsupported extrapolation.
- **Everywhere:** "agreement with the S-NPP satellite, not the true amount of fire". Estimates are always labelled as estimates; extrapolated ones are hatched (chart) or dashed with an asterisk (calendar).
- **Missing versus zero:** hatched cell = not in the archive; outlined "0" = zero detections in a complete archive file, "not proof of no fire".
- **Aqua:** described as better "in every setting we tested, not a universal rule", with the cause "not established".
- Footer: independent prototype, not affiliated with or endorsed by NASA.

## Browser verification (Microsoft Edge via Playwright, real backend and archive)
- Every screen inspected by screenshot at 1360, 820 and 390 px wide; final captures in `docs/evidence/ui-final/`.
- Issues found by inspection and fixed: permanent tooltip covering chart peaks; rounded axis ticks (1.3k for 1,250); trust note mentioning a band on a chart without one; misaligned export button; date overflow in the totals line; annotation colliding with the unit label on mobile; missing favicon (404).
- `e2e/app.spec.ts` (3 tests): full journey with all three illusion modes, calendar states (recorded / archive zero / missing / estimate / extrapolated / difference / availability), PNG and two CSV downloads, series toggles, Terra switch, keyboard month slider, evidence dialog with SHA-256 and Escape, zero page errors; region-dependent trust notes (Portugal versus Greece); map, custom area, empty selection, and no horizontal overflow on every screen at 390 px.
- `e2e/audit.spec.ts` (1 test): no control without an accessible name, exactly one `h1` per screen, no overflow at 820 px, skip link first in tab order, visible focus outline, keyboard navigation, loading state on the largest region.

## Accessibility and responsiveness
Skip link; `aria-current` navigation; `aria-pressed` toggles; charts carry `role="img"` descriptions plus a table view or readout, so no value is hover-only; calendar cells are labelled buttons; `aria-live` readouts; focus trap and Escape in the drawer; `prefers-reduced-motion` honoured. Not done: screen-reader testing with a real assistive technology, and automated contrast checks (axe could not be installed; PyPI and new npm packages were not used).

## Performance (measured)
| Request (cold server) | Time |
|---|---:|
| Portugal series (Compare/Calendar/Discover) | about 1.0 s first, 15 ms repeat |
| Portugal summary / map points | 0.5–0.65 s / 0.2 s |
| Zambia (3.9 M detections): Explore first load | 2.4–2.9 s on a warm disk; 14 s once on a cold disk |
| Zambia: Compare first load | 2.9–3.4 s |
| Any screen revisited (client cache) | 22–27 ms |

The client now issues one request per URL and shares it across screens; the old UI refetched on every tab change. Production bundle: 449 kB JS (137 kB gzip), 34 kB CSS. No backend optimisation was attempted.

## Tests
- Backend: `pytest -q -W error::RuntimeWarning` 91 passed (89 before; 2 added for the new endpoints).
- Frontend: `npm run build` (type-check and bundle) passed.
- Browser: 4 of 4 passed, twice in a row.

## Post-release fixes (2026-11-15)
- **Deployed Zambia/global summary returned HTTP 500** (`/api/analytics?country=Zambia`, and with no region). Cause (likely, not confirmed on the host): the summary copied every column of the selection (about 4 M rows including 64-character ids) into a temp table, which a memory-limited serverless function cannot hold. Fix: aggregates now stream from the Parquet view and only a narrow cell-day table is built; evidence ids are looked up for the at-most-1,000 returned cells. Output is identical; locally Zambia 2.6 s → 1.2 s unlimited and 7.1 s → 3.2 s under a 300 MB DuckDB memory cap. The monthly series got the same treatment. The fix has **not** been deployed or tested on the host.
- **Explore appeared to show only Europe:** it opened framed on Portugal with the other regions hidden in a dropdown. It now opens on a world view with every archived region outlined (click to switch), an "All regions" button, and the selected region highlighted.
- Tests: backend 92 passed; browser 5 passed.

## Unresolved limitations
- First load for the largest region is slow (seconds); a loading state is shown.
- Near-real-time processing can no longer be selected in the Calendar or Compare screens (it has no history and no model); the API still supports it.
- The map shows the 5,000 most recent detections only.
- The calendar's "difference from typical" view now uses within-satellite recorded values only.
- Screenshots listed in older documents (`VALIDATION.md` evidence links to `overview-desktop.png`, `sensor-lab-harmonized.png`) show the previous interface; current captures are in `docs/evidence/ui-final/`.
- Node is not on the default PATH in this environment; use the fnm install (`%APPDATA%\fnm\node-versions\v26.13.1\installation`) or a normal Node setup.
- No user testing was done; comprehension claims are design intent, not measured outcomes.

## Reproduce
```powershell
.\.runtime\python\python.exe -m pytest -q -W error::RuntimeWarning
npm.cmd run build --prefix frontend
npm.cmd run test:e2e --prefix frontend
.\scripts\start.ps1    # then open http://127.0.0.1:8000
```
