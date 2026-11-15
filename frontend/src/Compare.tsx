import { useEffect, useMemo, useState } from 'react'
import { Check, X } from 'lucide-react'
import { Legend, LineChart, MonthlyChart, bandText } from './charts'
import { Failure, IllusionPanel, Loading, Segmented, TrustNote, Unit, useMethod, useScience, useValidation } from './shared'
import { COLORS, SAT_NAME, annual, fmt, monthLabel, pct, type Region } from './api'

export function Compare({ region, modis, setModis }: { region: Region; modis: string; setModis: (m: string) => void }) {
  const { series, error, loading, retry } = useScience(region, modis)
  const method = useMethod(modis).data
  const aqua = useMethod('A').data?.model, terra = useMethod('T').data?.model
  const validation = useValidation().data
  const years = useMemo(() => series ? [...new Set(series.months.map(m => Number(m.slice(0, 4))))].sort((a, b) => a - b) : [], [series])
  const [from, setFrom] = useState(0), [to, setTo] = useState(0)
  useEffect(() => { if (years.length) { setTo(years[years.length - 1]); setFrom(Math.max(years[0], years[years.length - 1] - 5)) } }, [years])
  const months = useMemo(() => series ? series.months.filter(m => { const y = Number(m.slice(0, 4)); return y >= from && y <= to }) : [], [series, from, to])
  const [show, setShow] = useState({ modis: true, snpp: true, estimate: true })
  const [cursor, setCursor] = useState<number | null>(null)
  const [pinned, setPinned] = useState(0)
  useEffect(() => { setPinned(Math.max(0, months.length - 1)); setCursor(null) }, [months.length])
  const active = cursor ?? Math.min(pinned, Math.max(0, months.length - 1))
  const month = months[active]
  const ratios = useMemo(() => {
    if (!series) return []
    const n = new Map(annual(series.observed.N).map(p => [p.year, p.value]))
    return (['A', 'T'] as const).map(s => ({ name: `S-NPP ÷ ${SAT_NAME[s]}`, color: s === 'A' ? COLORS.modis : COLORS.terra, points: annual(series.observed[s]).filter(p => n.has(p.year) && p.value > 0).map(p => ({ x: p.year, y: n.get(p.year)! / p.value })) })).filter(s => s.points.length)
  }, [series])
  const model = method?.model, tested = model?.test[model.selected_model]
  const a = aqua?.test[aqua.selected_model], t = terra?.test[terra.selected_model]
  const e = month && series ? series.estimate.get(month) : undefined
  return <>
    <section className="page-head"><p className="eyebrow">Sensor Illusion Detector</p><h1>Did the fire change, or did the instrument?</h1><p className="lede">Compare what MODIS recorded, what VIIRS S-NPP recorded, and a model estimate that puts MODIS on the S-NPP scale — for {region.short}.</p></section>
    <div className="controls"><label className="field">MODIS satellite<Segmented value={modis} onChange={setModis} label="MODIS satellite" options={[{ value: 'A', label: 'Aqua' }, { value: 'T', label: 'Terra' }]}/></label></div>
    {loading && <Loading what="the satellite record"/>}{error && <Failure message={error} retry={retry}/>}
    {series && <>
      <section className="panel" aria-labelledby="c1"><header className="panel-head"><div><h2 id="c1">1 · The illusion, year by year</h2><p className="sub">Yearly totals in <Unit/> · {region.record}</p></div></header><IllusionPanel region={region} modis={modis} series={series}/></section>

      <section className="panel" aria-labelledby="c2"><header className="panel-head"><div><h2 id="c2">2 · Month by month</h2><p className="sub">Recorded values and the model estimate on one scale</p></div>
        <div className="range"><label>From<select aria-label="First year" value={from} onChange={ev => setFrom(Math.min(Number(ev.target.value), to))}>{years.map(y => <option key={y}>{y}</option>)}</select></label><label>To<select aria-label="Last year" value={to} onChange={ev => setTo(Math.max(Number(ev.target.value), from))}>{years.map(y => <option key={y}>{y}</option>)}</select></label></div></header>
        <div className="toggles" role="group" aria-label="Series shown">{([['modis', `${SAT_NAME[modis]} · recorded`, COLORS.modis], ['snpp', 'VIIRS S-NPP · recorded', COLORS.snpp], ['estimate', 'Estimate on the S-NPP scale', COLORS.estimate]] as const).map(([k, label, color]) => <button key={k} type="button" aria-pressed={show[k]} onClick={() => setShow({ ...show, [k]: !show[k] })}><span className="key key-line" style={{ ['--c' as string]: color }}/>{label}</button>)}</div>
        <MonthlyChart series={series} modis={modis} months={months} show={show} cursor={cursor} pinned={months.length ? Math.min(pinned, months.length - 1) : null} onCursor={i => { setCursor(i); if (i !== null) setPinned(i) }}/>
        {show.estimate && <Legend items={[{ color: COLORS.estimate, label: 'Residual band (shown only where supported)', shape: 'band' }]}/>}
        {series.status !== 'available' && <p className="caption">No estimate for this selection: {series.reason}</p>}
        {month && <div className="readout"><label>Month<input type="range" min={0} max={months.length - 1} value={active} aria-label="Comparison month" onChange={ev => { setCursor(null); setPinned(Number(ev.target.value)) }}/></label>
          <dl aria-live="polite"><div><dt>{monthLabel(month)}</dt><dd>UTC month</dd></div>
            <div><dt>{series.observed[modis].has(month) ? fmt(series.observed[modis].get(month)!.value) : '—'}</dt><dd><span className="key key-line" style={{ ['--c' as string]: COLORS.modis }}/>{SAT_NAME[modis]} recorded</dd></div>
            <div><dt>{series.observed.N.has(month) ? fmt(series.observed.N.get(month)!.value) : '—'}</dt><dd><span className="key key-line" style={{ ['--c' as string]: COLORS.snpp }}/>S-NPP recorded</dd></div>
            <div><dt>{e ? fmt(e.estimate, 1) : '—'}</dt><dd><span className="key key-line" style={{ ['--c' as string]: COLORS.estimate }}/>Estimate · {bandText(e)}</dd></div></dl></div>}
        <TrustNote region={region} modis={modis} validation={validation} method={method}/>
      </section>

      <section className="panel" aria-labelledby="c3"><header className="panel-head"><div><h2 id="c3">3 · Which MODIS satellite?</h2><p className="sub">How many times more S-NPP recorded than each MODIS satellite, per year</p></div></header>
        <div className="split"><div>{ratios.length ? <><Legend items={ratios.map(r => ({ color: r.color, label: r.name }))}/><LineChart series={ratios} unit="S-NPP ÷ MODIS (yearly totals)" yMin={0} valueDigits={2} label="Ratio of yearly S-NPP to MODIS active cell-days for Aqua and Terra"/></> : <div className="chart-empty">No overlapping complete years.</div>}
          <p className="caption">A steady ratio is easy to convert; a wandering one is not. Harmonization can only correct the part of the gap that stays consistent.</p></div>
          <div className="evidence-card"><h3>Held-out test against S-NPP</h3><table className="mini"><thead><tr><th/><th>Aqua</th><th>Terra</th></tr></thead><tbody>
            <tr><th>Average monthly error</th><td>{a ? fmt(a.mae, 1) : '—'}</td><td>{t ? fmt(t.mae, 1) : '—'}</td></tr>
            <tr><th>Error as share of total</th><td>{pct(a?.wape, 1)}</td><td>{pct(t?.wape, 1)}</td></tr></tbody></table>
            <p className="fine">Portugal and Uruguay, 2022–2025; years never used to fit the model. {validation?.paired_satellite && <>Aqua had the lower error in {validation.paired_satellite.aqua_better_folds} of {validation.paired_satellite.n_folds} region-years. </>}Aqua did better in every setting tested, but the comparison re-uses data we had already seen, and <strong>why</strong> Aqua does better is not established.</p></div></div>
      </section>

      <section className="panel conclude" aria-labelledby="c4"><h2 id="c4">What this lets you conclude</h2><div className="split">
        <ul className="yes"><li><Check size={16} aria-hidden="true"/>MODIS and VIIRS counts are not interchangeable; the gap is large and measurable.</li><li><Check size={16} aria-hidden="true"/>Within Portugal, a simple model brings MODIS much closer to what S-NPP records.</li><li><Check size={16} aria-hidden="true"/>A trend that crosses a sensor change needs this check before it is believed.</li></ul>
        <ul className="no"><li><X size={16} aria-hidden="true"/>Estimates are not the true number of fires, nor burned area.</li><li><X size={16} aria-hidden="true"/>The Portugal model is not reliable elsewhere; it ran low in every other country tested.</li><li><X size={16} aria-hidden="true"/>A month with no detections is not proof of no fire: cloud and overpass coverage are unknown.</li></ul></div>
        <details className="method-details"><summary>How it was computed</summary>
          <p>Detections are grouped into hexagonal cells (H3 resolution 7) and UTC days; each satellite is counted separately and never summed with another. Months missing from the archive stay missing.</p>
          {model && tested ? <><p>Registered model {model.model_id} ({model.selected_model}) for {SAT_NAME[model.modis_satellite]} → S-NPP. Fitted on {model.years.train[0]}–{model.years.train[model.years.train.length - 1]}, method chosen on {model.years.validation.join(', ')}, band calibrated on {model.years.calibration.join(', ')}, tested on {model.years.test[0]}–{model.years.test[model.years.test.length - 1]}.</p>
            <dl className="metrics"><div><dt>{fmt(tested.mae, 2)}</dt><dd>Test error (MAE), active cell-days per month</dd></div><div><dt>{pct(tested.wape, 1)}</dt><dd>Error as share of S-NPP total (WAPE)</dd></div><div><dt>{tested.band_within_calibration_activity ? `${tested.band_within_calibration_activity.months_with_band} / ${tested.band_within_calibration_activity.months_with_band + tested.band_within_calibration_activity.months_band_withheld}` : '—'}</dt><dd>Test months where a residual band is shown</dd></div></dl>
            <p className="fine">Benchmark figures describe the benchmark regions, not necessarily this selection. Independent ground validation: {method?.independent_ground_validation.replaceAll('_', ' ')}.</p></> : <p>No registered benchmark for this satellite.</p>}
        </details>
      </section>
    </>}
  </>
}
