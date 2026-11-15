import { ArrowDownToLine, ArrowUpRight } from 'lucide-react'
import { Legend, LineChart } from './charts'
import { Failure, Loading, useMethod, useValidation } from './shared'
import { COLORS, REGIONS, SAT_NAME, fmt, pct, regionQuery, useJSON, type Analytics, type AnomalyResponse, type Batch, type Detection, type Model, type Region } from './api'

const METHOD_NAME: Record<string, string> = { B0_raw_modis: 'Raw MODIS, unchanged', B1_shrunk_ratio: 'Seasonal ratio', B2_tweedie: 'Tweedie regression', B3_loglinear: 'Log-linear' }
const regionName = (id: string) => REGIONS.find(r => r.id === id)?.short ?? id

function Benchmark({ model }: { model: Model }) {
  return <div className="table-scroll"><table><caption>{SAT_NAME[model.modis_satellite]} → S-NPP · fitted {model.years.train[0]}–{model.years.train[model.years.train.length - 1]} in {model.train_regions.map(regionName).join(', ')} · tested {model.years.test[0]}–{model.years.test[model.years.test.length - 1]}</caption>
    <thead><tr><th>Method</th><th>Selection-year error</th><th>Test error (MAE)</th><th>Share of total (WAPE)</th><th>Average bias</th></tr></thead>
    <tbody>{Object.entries(model.test).map(([name, m]) => <tr key={name} className={name === model.selected_model ? 'chosen' : ''}><th>{METHOD_NAME[name] ?? name}{name === model.selected_model && <span className="tag">in use</span>}</th><td>{fmt(model.validation[name].mae, 1)}</td><td>{fmt(m.mae, 1)}</td><td>{pct(m.wape, 1)}</td><td>{m.signed_bias > 0 ? '+' : ''}{fmt(m.signed_bias, 1)}</td></tr>)}</tbody></table></div>
}

export function Evidence({ region, onSelect }: { region: Region; onSelect: (id: string) => void }) {
  const aqua = useMethod('A'), terra = useMethod('T'), validation = useValidation()
  const q = regionQuery(region).toString()
  const summary = useJSON<Analytics>(`/api/analytics?${q}`)
  const points = useJSON<{ items: Detection[]; total: number }>(`/api/detections?${q}&limit=5000`)
  const batches = useJSON<{ items: Batch[] }>('/api/batches')
  const anomalies = useJSON<AnomalyResponse>(`/api/v1/anomalies?${regionQuery(region, { view: 'raw', processing: 'standard', region_id: region.id })}`)
  const v = validation.data
  const flagged = summary.data?.cells.filter(c => c.flags.length > 0) ?? []
  const overpass = v?.overpass ? (['T', 'A', 'N'] as const).map(s => ({ name: SAT_NAME[s], color: s === 'T' ? COLORS.terra : s === 'A' ? COLORS.modis : COLORS.snpp, points: Object.entries(v.overpass!.daytime_median_local_solar_hour[s] ?? {}).map(([y, h]) => ({ x: Number(y), y: h })) })) : []
  const exportJSON = () => {
    const payload = JSON.stringify({ exported_at: new Date().toISOString(), region: region.api, summary: summary.data, map_sample: points.data?.items, total_matching: points.data?.total, sample_limit: 5000, cell_sample_limit: 1000, batches: batches.data?.items }, null, 2)
    const url = URL.createObjectURL(new Blob([payload], { type: 'application/json' })); const a = document.createElement('a'); a.href = url; a.download = 'firetrust-evidence.json'; a.click(); URL.revokeObjectURL(url)
  }
  return <>
    <section className="page-head"><p className="eyebrow">Evidence</p><h1>Check our work.</h1><p className="lede">What was tested, what held up, what did not, and where every number comes from. Open only what you need.</p></section>
    {validation.error && <Failure message={validation.error} retry={validation.retry}/>}

    <details className="panel fold" open><summary><h2>What an estimate is — and is not</h2></summary>
      <p>An estimate answers one question: <em>given what MODIS recorded this month, what would VIIRS S-NPP probably have recorded?</em> It is checked against S-NPP, another satellite — not against fires on the ground. No ground-truth, burned-area, cloud-cover or overpass-coverage data were available, so nothing here measures the true amount of fire.</p>
      <p className="fine">Unit: active cell-days — unique pairs of a hexagonal cell (H3 resolution 7, about 5 km²) and a UTC day with at least one detection, per satellite, per month.</p></details>

    <details className="panel fold" open><summary><h2>How well it works where it was fitted</h2></summary>
      {(aqua.loading || terra.loading) && <Loading what="benchmark results"/>}
      {aqua.data?.model && <Benchmark model={aqua.data.model}/>}{terra.data?.model && <Benchmark model={terra.data.model}/>}
      <p className="fine">Errors are in active cell-days per month against S-NPP, on Portugal and Uruguay. The method in use was chosen on the selection year only; others are shown even where they scored better on the test. {v?.nested_selection && <>Re-choosing satellite and method each year from earlier years only picked Aqua in {Object.entries(v.nested_selection.selection_frequency).filter(([k]) => k.startsWith('A:')).reduce((s, [, n]) => s + n, 0)} of {v.nested_selection.n_outer_folds} years. </>}These comparisons re-use data inspected during development{v?.first_acquired_after_choice && <>, except {v.first_acquired_after_choice.results.A?.months} Zambia months acquired after Aqua was chosen (error share: Aqua {pct(v.first_acquired_after_choice.results.A?.model_wape, 1)}, Terra {pct(v.first_acquired_after_choice.results.T?.model_wape, 1)})</>}.</p></details>

    <details className="panel fold" open><summary><h2>Where it does not work</h2></summary>
      {v && <><div className="table-scroll"><table><caption>The Portugal-fitted model applied elsewhere, 2022–2025, without refitting</caption><thead><tr><th>Region</th><th>Months</th><th>Aqua: error share</th><th>Aqua: average bias</th><th>Terra: error share</th><th>Terra: average bias</th></tr></thead>
        <tbody>{Object.keys(v.transfer.A ?? {}).map(r => <tr key={r}><th>{regionName(r)}</th><td>{v.transfer.A[r].months}</td><td>{pct(v.transfer.A[r].model_wape, 1)}</td><td>{fmt(v.transfer.A[r].model_bias, 0)}</td><td>{pct(v.transfer.T?.[r]?.model_wape, 1)}</td><td>{v.transfer.T?.[r] ? fmt(v.transfer.T[r].model_bias, 0) : '—'}</td></tr>)}</tbody></table></div>
        <p>Every bias is negative: the model ran low in each country. The S-NPP-to-MODIS ratio differs between regions and falls as activity rises, and the data cannot separate the reasons, so no geographic correction is applied.</p>
        <div className="table-scroll"><table><caption>Residual band: share of months in which it contained the S-NPP value (target {pct(v.bands.A?.nominal)}; {v.bands.A?.folds} rolling yearly tests)</caption><thead><tr><th/><th>Aqua</th><th>Terra</th></tr></thead>
          <tbody><tr><th>Portugal, all months</th><td>{pct(v.bands.A?.fitted_region?.coverage_all, 1)}</td><td>{pct(v.bands.T?.fitted_region?.coverage_all, 1)}</td></tr>
            <tr><th>Portugal, months where the band is shown</th><td>{pct(v.bands.A?.fitted_region?.coverage_when_shown, 1)}</td><td>{pct(v.bands.T?.fitted_region?.coverage_when_shown, 1)}</td></tr>
            <tr><th>Portugal, months where it is withheld</th><td>{pct(v.bands.A?.fitted_region?.coverage_withheld, 0)}</td><td>{pct(v.bands.T?.fitted_region?.coverage_withheld, 0)}</td></tr>
            <tr><th>Other regions, all months</th><td>{pct(v.bands.A?.other_regions?.coverage_all, 0)}</td><td>{pct(v.bands.T?.other_regions?.coverage_all, 0)}</td></tr></tbody></table></div>
        <p className="fine">This is why the band is drawn only in Portugal and only within its calibrated activity range. It describes agreement with S-NPP, not a confidence interval for true fire activity. Source files: {v.sources.join(', ')}.</p></>}</details>

    <details className="panel fold"><summary><h2>Why Terra and Aqua differ — what is known</h2></summary>
      {overpass.length > 0 && <><Legend items={overpass.map(o => ({ color: o.color, label: o.name }))}/><LineChart series={overpass} unit="median local solar time of daytime detections (hours)" valueDigits={2} label="Median local solar time of daytime detections per year for Terra, Aqua and S-NPP over Portugal"/></>}
      <p>Over {v?.overpass?.scope.country ?? 'Portugal'}, Aqua passes at nearly the same time of day as S-NPP while Terra passes about two hours earlier, and both MODIS satellites drift after 2021. That is consistent with Aqua matching S-NPP better — but Aqua was already ahead before the drift, so timing alone does not explain it. The cause is not established.</p></details>

    <details className="panel fold"><summary><h2>Unusual months in {region.short}</h2></summary>
      {anomalies.loading && <Loading what="monthly comparisons"/>}
      {anomalies.data && (anomalies.data.items.length ? <div className="table-scroll"><table><caption>Largest differences from the median of the same month in at least five other years, per satellite</caption><thead><tr><th>Month</th><th>Satellite</th><th>Active cell-days</th><th>Typical</th><th>Difference</th><th>Years compared</th></tr></thead><tbody>{[...anomalies.data.items].sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta)).slice(0, 20).map(r => <tr key={`${r.month}-${r.satellite}`}><td>{r.month}</td><td>{SAT_NAME[r.satellite] ?? r.satellite}</td><td>{fmt(r.active_cell_days)}</td><td>{fmt(r.baseline_median, 1)}</td><td>{r.delta > 0 ? '+' : ''}{fmt(r.delta, 1)}</td><td>{r.baseline_years}</td></tr>)}</tbody></table></div> : <p>{anomalies.data.reason}</p>)}
      <p className="fine">Descriptive only, within one satellite at a time. Not a forecast, and not adjusted for cloud or coverage.</p></details>

    <details className="panel fold"><summary><h2>Cells flagged for a closer look</h2></summary>
      <p>A cell-day is flagged when only one instrument recorded it, a low-confidence detection is present, or pixel footprints differ strongly. These are prompts for review — <strong>not</strong> classifications of false fires. {summary.data && <>{fmt(summary.data.flagged_cell_count)} of {fmt(summary.data.cell_count)} cell-days in {region.short} carry a flag.</>}</p>
      {summary.loading && <Loading what="review flags"/>}
      {flagged.length > 0 && <div className="table-scroll"><table><thead><tr><th>UTC date</th><th>Cell centre</th><th>Detections</th><th>Instruments</th><th>Flags</th><th>Source</th></tr></thead><tbody>{flagged.slice(0, 25).map(c => <tr key={`${c.date}-${c.south}-${c.west}`}><td>{c.date}</td><td>{c.south.toFixed(2)}, {c.west.toFixed(2)}</td><td>{c.count}</td><td>{Object.keys(c.sensors).join(' + ')}</td><td>{c.flags.map(f => <span className="tag" key={f}>{f.replaceAll('_', ' ')}</span>)}</td><td><button type="button" className="link" onClick={() => onSelect(c.evidence_ids[0])}>Trace <ArrowUpRight size={12} aria-hidden="true"/></button></td></tr>)}</tbody></table></div>}</details>

    <details className="panel fold" open><summary><h2>Source ledger</h2></summary>
      <p className="fine">Every NASA file is stored byte-for-byte under its SHA-256 hash. Latest 100 files.</p>
      {batches.data && <div className="table-scroll tall"><table><thead><tr><th>Source</th><th>Fetched (UTC)</th><th>Rows accepted</th><th>Rejected</th><th>SHA-256</th></tr></thead><tbody>{batches.data.items.map(b => <tr key={b.id}><td>{b.source.replace('https://firms.modaps.eosdis.nasa.gov/data/country/', 'FIRMS country archive · ')}</td><td>{new Date(b.fetched_at).toISOString().replace('T', ' ').slice(0, 16)}</td><td>{fmt(b.accepted)}</td><td>{b.rejected}</td><td><code title={b.id}>{b.id.slice(0, 12)}…</code></td></tr>)}</tbody></table></div>}
      <h3>Latest detections in {region.short}</h3>
      {points.loading && <Loading what="detections"/>}
      {points.data && <div className="table-scroll tall"><table><thead><tr><th>Acquired (UTC)</th><th>Location</th><th>Instrument</th><th>Confidence class</th><th>FRP (MW)</th><th>Source</th></tr></thead><tbody>{points.data.items.slice(0, 50).map(r => <tr key={r.id}><td>{r.acquired_at.slice(0, 16).replace('T', ' ')}</td><td>{r.latitude.toFixed(3)}, {r.longitude.toFixed(3)}</td><td>{r.sensor} / {r.satellite}</td><td>{r.confidence_class}</td><td>{r.frp ?? 'missing'}</td><td><button type="button" className="link" onClick={() => onSelect(r.id)}>Inspect <ArrowUpRight size={12} aria-hidden="true"/></button></td></tr>)}</tbody></table></div>}
      <div className="actions"><a className="ghost" href={`/api/v1/exports/csv?${q}&mode=raw`}><ArrowDownToLine size={14} aria-hidden="true"/> Export filtered detections as CSV</a><button type="button" className="ghost" onClick={exportJSON} disabled={!summary.data}><ArrowDownToLine size={14} aria-hidden="true"/> Export evidence as JSON</button><a className="ghost" href="/docs" target="_blank" rel="noreferrer">API reference <ArrowUpRight size={12} aria-hidden="true"/></a></div></details>
  </>
}
