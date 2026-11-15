import { useEffect, useMemo, useState } from 'react'
import { ArrowDownToLine } from 'lucide-react'
import { bandText } from './charts'
import { Failure, Loading, Segmented, TrustNote, Unit, useMethod, useScience, useValidation } from './shared'
import { SAT_NAME, fmt, monthLabel, regionQuery, useJSON, type AnomalyResponse, type Region } from './api'

type View = 'observed' | 'estimate' | 'anomaly' | 'availability'
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const BLUE = ['#12305a', '#184f95', '#256abf', '#3987e5', '#6da7ec', '#9ec5f4', '#cde2fb']
const GREEN = ['#0c3a2c', '#11573f', '#167a57', '#199e70', '#4cc096', '#86d9b8', '#c2efdd']
const NEG = ['#86b6ef', '#3987e5', '#184f95'], POS = ['#8f2f2f', '#d44f4f', '#f0a3a3'], MID = '#383835'
const step = (ramp: string[], t: number) => { const i = Math.min(ramp.length - 1, Math.floor(Math.sqrt(Math.max(0, Math.min(1, t))) * ramp.length)); return { bg: ramp[i], dark: i >= 4 } }

export function BurningCalendar({ region, modis, setModis }: { region: Region; modis: string; setModis: (m: string) => void }) {
  const [satellite, setSatellite] = useState(modis)
  const [view, setView] = useState<View>('observed')
  const [selected, setSelected] = useState<string | null>(null)
  const input = satellite === 'N' ? modis : satellite
  useEffect(() => { if (satellite !== 'N' && satellite !== modis) setModis(satellite) }, [satellite, modis, setModis])
  const { series, error, loading, retry } = useScience(region, input)
  const method = useMethod(input).data, validation = useValidation().data
  const anomalyUrl = view === 'anomaly' || selected ? `/api/v1/anomalies?${regionQuery(region, { view: 'raw', processing: 'standard', region_id: region.id })}` : null
  const anomalies = useJSON<AnomalyResponse>(anomalyUrl)
  const anomalyBy = useMemo(() => new Map((anomalies.data?.items ?? []).filter(r => r.satellite === satellite).map(r => [r.month, r])), [anomalies.data, satellite])
  const observed = series?.observed[satellite] ?? new Map()
  const estimates = satellite === 'N' ? new Map() : series?.estimate ?? new Map()
  const years = useMemo(() => { const ys = [...observed.keys()].map(m => Number(m.slice(0, 4))); if (!ys.length) return []; const lo = Math.min(...ys), hi = Math.max(...ys); return Array.from({ length: hi - lo + 1 }, (_, i) => lo + i) }, [observed])
  const maxObserved = Math.max(1, ...[...observed.values()].map(v => v.value))
  const maxEstimate = Math.max(1, ...[...estimates.values()].map(v => v.estimate))
  const maxDelta = Math.max(1, ...[...anomalyBy.values()].map(v => Math.abs(v.delta)))
  const estimateOk = satellite !== 'N' && series?.status === 'available'

  const cell = (key: string) => {
    const o = observed.get(key), e = estimates.get(key), a = anomalyBy.get(key)
    if (view === 'observed') {
      if (!o) return { text: '', label: 'no matching records', cls: 'none' }
      if (o.archiveZero) return { text: '0', label: '0 active cell days recorded, complete archive file, coverage unknown', cls: 'zero' }
      return { text: fmt(o.value), label: `${o.value} active cell days`, cls: 'value', ...step(BLUE, o.value / maxObserved) }
    }
    if (view === 'estimate') {
      if (!estimateOk || !e) return { text: '', label: 'no estimate', cls: 'none' }
      const extra = e.model_status === 'extrapolated'
      return { text: fmt(e.estimate) + (extra ? '*' : ''), label: `estimate ${fmt(e.estimate, 1)}; ${bandText(e)}; ${extra ? 'extrapolated' : 'within fitted range'}`, cls: 'value' + (extra ? ' extrapolated' : e.lower === null ? ' noband' : ''), ...step(GREEN, e.estimate / maxEstimate) }
    }
    if (view === 'anomaly') {
      if (!a) return { text: '', label: o ? 'no baseline: fewer than five other years' : 'no matching records', cls: 'none' }
      const t = Math.abs(a.delta) / maxDelta, i = Math.min(2, Math.floor(Math.sqrt(t) * 3))
      return { text: (a.delta > 0 ? '+' : '') + fmt(a.delta), label: `delta ${fmt(a.delta, 1)} from the median of ${a.baseline_years} other years (${fmt(a.baseline_median, 1)})`, cls: 'value', bg: Math.abs(a.delta) < 1 ? MID : a.delta > 0 ? POS[i] : NEG[2 - i], dark: a.delta > 0 ? i === 2 : i === 0 && Math.abs(a.delta) >= 1 }
    }
    if (!o) return { text: '', label: 'no matching records: not in the archive we hold', cls: 'none' }
    return o.archiveZero ? { text: '0', label: 'complete archive file with zero detections; cloud and overpass coverage unknown', cls: 'zero' } : { text: '●', label: 'detections recorded; cloud and overpass coverage unknown', cls: 'value avail' }
  }
  const downloadPNG = () => {
    const canvas = document.createElement('canvas'); canvas.width = 1280; canvas.height = 150 + years.length * 31
    const ctx = canvas.getContext('2d'); if (!ctx) return
    ctx.fillStyle = '#101317'; ctx.fillRect(0, 0, canvas.width, canvas.height); ctx.fillStyle = '#e9e6df'; ctx.font = '22px Georgia, serif'
    ctx.fillText(`FIRETRUST · ${region.label} · ${SAT_NAME[satellite]} · ${view}`, 30, 40)
    ctx.font = '12px sans-serif'; ctx.fillStyle = '#9aa3ad'; ctx.fillText('NASA FIRMS · active cell-days per UTC month (H3 r7) · blank = not in archive · coverage unknown · * extrapolated estimate · estimates are not observed fires', 30, 64)
    MONTHS.forEach((m, i) => ctx.fillText(m, 98 + i * 96, 92))
    years.forEach((year, r) => { ctx.fillStyle = '#c9c6bf'; ctx.fillText(String(year), 30, 122 + r * 31); MONTHS.forEach((_, m) => {
      const c = cell(`${year}-${String(m + 1).padStart(2, '0')}`) as { text: string; bg?: string; dark?: boolean; cls: string }
      ctx.fillStyle = c.bg ?? (c.cls === 'none' ? '#181c22' : '#232830'); ctx.fillRect(90 + m * 96, 102 + r * 31, 88, 25)
      ctx.fillStyle = c.dark ? '#101317' : '#e9e6df'; ctx.fillText(c.text, 98 + m * 96, 119 + r * 31) }) })
    const a = document.createElement('a'); a.download = 'firetrust-calendar.png'; a.href = canvas.toDataURL('image/png'); a.click()
  }
  const csv = regionQuery(region, { mode: view === 'estimate' ? 'harmonized' : 'aggregate', region_id: region.id, reference: 'N', modis: input, processing: 'standard' })
  const sel = selected ? { o: series?.observed, e: satellite === 'N' ? undefined : series?.estimate.get(selected), a: anomalyBy.get(selected) } : null
  return <>
    <section className="page-head"><p className="eyebrow">Fire activity calendar</p><h1>Every month on record, with the gaps left in.</h1><p className="lede">{region.short}: one satellite at a time, in <Unit/>. Recorded values, model estimates and missing data are drawn differently so they are never confused.</p></section>
    <div className="controls">
      <label className="field">Satellite<Segmented value={satellite} onChange={v => { setSatellite(v); if (v === 'N' && view === 'estimate') setView('observed') }} label="Calendar satellite" options={[{ value: 'A', label: 'MODIS Aqua' }, { value: 'T', label: 'MODIS Terra' }, { value: 'N', label: 'VIIRS S-NPP' }]}/></label>
      <label className="field">View<select aria-label="Calendar view" value={view} onChange={ev => setView(ev.target.value as View)}><option value="observed">Recorded activity</option><option value="estimate" disabled={satellite === 'N'}>Estimate on the S-NPP scale</option><option value="anomaly">Difference from a typical year</option><option value="availability">Data availability</option></select></label>
      <button type="button" className="ghost" onClick={downloadPNG} disabled={!series}><ArrowDownToLine size={14} aria-hidden="true"/> Export PNG</button>
    </div>
    {loading && <Loading what="the monthly record"/>}{error && <Failure message={error} retry={retry}/>}
    {series && <section className="panel calendar"><div className="calendar-grid">
      <div className="heat-wrap"><div className="heatmap" role="grid" aria-label={`${SAT_NAME[satellite]} monthly calendar, ${view}`}>
        <div className="heat-row heat-head" role="row"><span role="columnheader">UTC</span>{MONTHS.map(m => <span key={m} role="columnheader">{m}</span>)}</div>
        {years.map(year => <div className="heat-row" role="row" key={year}><span role="rowheader">{year}</span>{MONTHS.map((_, m) => {
          const key = `${year}-${String(m + 1).padStart(2, '0')}`; const c = cell(key) as { text: string; label: string; cls: string; bg?: string; dark?: boolean }
          return <button key={key} type="button" role="gridcell" className={`heat-cell ${c.cls} ${c.dark ? 'dark-ink' : ''}`} aria-pressed={selected === key} style={c.bg ? { background: c.bg } : undefined} title={`${monthLabel(key)} · ${SAT_NAME[satellite]} · ${c.label}`} aria-label={`${key}: ${c.label}`} onClick={() => setSelected(selected === key ? null : key)}>{c.text}</button>
        })}</div>)}
        {!years.length && <p className="chart-empty">No {SAT_NAME[satellite]} records in the archive for {region.short}.</p>}
      </div></div>
      <aside className="month-detail" aria-live="polite">{selected && sel ? <>
        <h3>{monthLabel(selected)}</h3>
        <dl>{(['A', 'T', 'N'] as const).map(s => { const v = sel.o?.[s].get(selected); return <div key={s}><dt>{SAT_NAME[s]} recorded</dt><dd>{v ? v.archiveZero ? '0 (complete archive file)' : fmt(v.value) : 'not in archive'}</dd></div> })}
          {satellite !== 'N' && <div><dt>Estimate on the S-NPP scale from {SAT_NAME[input]}</dt><dd>{sel.e ? fmt(sel.e.estimate, 1) : 'unavailable'}</dd></div>}
          {sel.e && <div><dt>Uncertainty</dt><dd>{bandText(sel.e)}</dd></div>}
          <div><dt>Versus a typical {MONTHS[Number(selected.slice(5)) - 1]}</dt><dd>{sel.a ? `${sel.a.delta > 0 ? '+' : ''}${fmt(sel.a.delta, 1)} (median of ${sel.a.baseline_years} other years: ${fmt(sel.a.baseline_median, 1)})` : anomalies.loading ? 'loading…' : 'needs five other years'}</dd></div></dl>
        <p className="fine">Cloud cover and overpass coverage for this month are unknown.</p></> : <><h3>Select a month</h3><p className="fine">Click or focus any cell to compare all three satellites for that month.</p></>}
        <div className="cal-legend"><h4>How to read it</h4>
          {view === 'observed' && <><div className="ramp">{BLUE.map(c => <i key={c} style={{ background: c }}/>)}</div><div className="ramp-labels"><span>fewer</span><span>more active cell-days (max {fmt(maxObserved)})</span></div></>}
          {view === 'estimate' && <><div className="ramp">{GREEN.map(c => <i key={c} style={{ background: c }}/>)}</div><div className="ramp-labels"><span>lower</span><span>higher estimate (max {fmt(maxEstimate)})</span></div><p className="legend-line"><span className="swatch extrapolated">12*</span> extrapolated: outside what the model was fitted on, no band</p><p className="legend-line"><span className="swatch noband">12</span> estimate with band withheld</p></>}
          {view === 'anomaly' && <><div className="ramp">{[...NEG, MID, ...POS].map(c => <i key={c} style={{ background: c }}/>)}</div><div className="ramp-labels"><span>below typical</span><span>above typical</span></div></>}
          {view === 'availability' && <p className="legend-line"><span className="swatch avail">●</span> detections recorded</p>}
          <p className="legend-line"><span className="swatch zero">0</span> zero detections in a complete archive file — not proof of no fire</p>
          <p className="legend-line"><span className="swatch none"/> not in the archive we hold — unknown, never zero</p>
        </div>
      </aside></div>
      {view === 'estimate' && !estimateOk && <p className="caption">No estimate for this selection: {series.reason ?? 'choose a MODIS satellite.'}</p>}
      {view === 'anomaly' && anomalies.data && !anomalyBy.size && <p className="caption">{anomalies.data.reason ?? 'At least five other complete years of the same month are needed.'}</p>}
      {view === 'estimate' && <TrustNote region={region} modis={input} validation={validation} method={method}/>}
      {(view !== 'estimate' || estimateOk) && <a className="ghost" href={`/api/v1/exports/csv?${csv}`}><ArrowDownToLine size={14} aria-hidden="true"/> Download {view === 'estimate' ? 'estimates' : 'monthly series'} with provenance</a>}
    </section>}
  </>
}
