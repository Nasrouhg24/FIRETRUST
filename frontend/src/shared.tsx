import { useMemo, useState, type ReactNode } from 'react'
import { ShieldCheck } from 'lucide-react'
import { AnnualChart, Legend, type IllusionMode } from './charts'
import { COLORS, SAT_NAME, annual, buildSeries, fmt, pct, regionQuery, useJSON, type Method, type Region, type Series, type SeriesResponse, type Validation } from './api'

export const UNIT_HELP = 'One active cell-day = one hexagonal grid cell (about 5 km²) with at least one satellite detection on one UTC day. It counts where and when a satellite saw heat — not fires, and not burned area.'
export const Unit = ({ children = 'active cell-days' }: { children?: ReactNode }) => <abbr title={UNIT_HELP} tabIndex={0}>{children}</abbr>

export function useScience(region: Region, modis: string) {
  const url = `/api/v1/sensor-comparison?${regionQuery(region, { processing: 'standard', modis, reference: 'N', region_id: region.id })}`
  const { data, error, loading, retry } = useJSON<SeriesResponse>(url)
  const series = useMemo(() => data ? buildSeries(data) : null, [data])
  return { series, raw: data, error, loading, retry }
}
export const useMethod = (modis: string) => useJSON<Method>(`/api/v1/method?modis=${modis}`)
export const useValidation = () => useJSON<Validation>('/api/v1/validation')

export function Segmented<T extends string>({ value, onChange, options, label }: { value: T; onChange: (v: T) => void; options: { value: T; label: string }[]; label: string }) {
  return <div className="segmented" role="group" aria-label={label}>{options.map(o => <button key={o.value} type="button" aria-pressed={value === o.value} onClick={() => onChange(o.value)}>{o.label}</button>)}</div>
}

export function Loading({ what }: { what: string }) { return <div className="loading" role="status"><span className="spinner" aria-hidden="true"/>Loading {what}…</div> }
export function Failure({ message, retry }: { message: string; retry?: () => void }) { return <div className="error" role="alert">{message} {retry && <button type="button" onClick={retry}>Retry</button>}</div> }

/** Overlap ratio: S-NPP total ÷ MODIS total over the complete calendar years both recorded. */
export function overlapRatio(series: Series, modis: string) {
  const m = new Map(annual(series.observed[modis]).map(p => [p.year, p.value])); const n = annual(series.observed.N).filter(p => m.has(p.year))
  const mTotal = n.reduce((s, p) => s + m.get(p.year)!, 0), nTotal = n.reduce((s, p) => s + p.value, 0)
  return n.length && mTotal > 0 ? { ratio: nTotal / mTotal, first: n[0].year, last: n[n.length - 1].year, years: n.length } : null
}

export function TrustNote({ region, modis, validation, method, brief = false }: { region: Region; modis: string; validation: Validation | null; method: Method | null; brief?: boolean }) {
  let body: ReactNode
  if (region.role === 'fitted' && brief) {
    body = <>The model was fitted here, so from {region.short}'s first S-NPP year on, its estimates can be checked against what S-NPP recorded. Earlier years cannot be checked.</>
  } else if (region.role === 'fitted') {
    const b = validation?.bands[modis]?.fitted_region
    body = <>The shaded <strong>residual band</strong> appears only where the evidence supports it{b?.coverage_when_shown != null && <> — in out-of-sample checks it contained the S-NPP value in {pct(b.coverage_when_shown)} of the months where it was shown</>}. It is hidden when activity exceeds the calibrated range and before the S-NPP record begins.</>
  } else if (region.role === 'transfer') {
    const t = validation?.transfer[modis]?.[region.id]
    const u = !t && method?.model ? method.model.test[method.model.selected_model]?.by_region[region.id] : null
    const bias = t?.model_bias ?? u?.signed_bias, wape = t?.model_wape ?? u?.wape
    const other = validation?.bands[modis]?.other_regions
    body = <><strong>No uncertainty band in {region.short}.</strong> The model was fitted in Portugal{bias != null && wape != null && <>; tested here in 2022–2025 it ran {bias < 0 ? 'low' : 'high'} by {fmt(Math.abs(bias), Math.abs(bias) < 100 ? 1 : 0)} active cell-days a month on average (error {pct(wape)} of the S-NPP total)</>}.{other && <> Outside Portugal a band would have contained S-NPP in only {pct(other.coverage_all)} of months, so none is drawn.</>}</>
  } else {
    body = <><strong>No uncertainty band.</strong> This area lies outside every region the model was evaluated in, so its estimates are extrapolations that no test supports.</>
  }
  return <aside className="trust" aria-label="How far to trust these estimates"><ShieldCheck size={16} aria-hidden="true"/><p>{body} Estimates describe agreement with the S-NPP satellite, <strong>not the true amount of fire</strong>.</p></aside>
}

export function IllusionPanel({ region, modis, series, compact = false }: { region: Region; modis: string; series: Series; compact?: boolean }) {
  const data = useMemo(() => {
    const m = annual(series.observed[modis]), n = annual(series.observed.N)
    return { m, n, hasPre: Boolean(n.length && m.some(p => p.year < n[0].year)), ratio: overlapRatio(series, modis) }
  }, [series, modis])
  const [mode, setMode] = useState<IllusionMode>('raw')
  const active = mode === 'splice' && !data.hasPre ? 'raw' : mode
  const options: { value: IllusionMode; label: string }[] = [{ value: 'raw', label: 'What each satellite recorded' }, ...(data.hasPre ? [{ value: 'splice' as const, label: 'Switch sensors mid-record' }] : []), { value: 'common', label: 'Estimated common scale' }]
  const estimateAvailable = series.status === 'available'
  const r = data.ratio
  return <div className="illusion">
    <div className="illusion-head"><Segmented value={active} onChange={setMode} options={options} label="Illusion view"/></div>
    <Legend items={active === 'raw' ? [{ color: COLORS.modis, label: `${SAT_NAME[modis]} · recorded`, shape: 'bar' }, { color: COLORS.snpp, label: 'VIIRS S-NPP · recorded', shape: 'bar' }]
      : active === 'splice' ? [{ color: COLORS.modis, label: `${SAT_NAME[modis]} · recorded`, shape: 'bar' }, { color: COLORS.snpp, label: 'VIIRS S-NPP · recorded', shape: 'bar' }]
      : [{ color: COLORS.estimate, label: 'Model estimate on the S-NPP scale', shape: 'bar' }, { color: COLORS.estimate, label: 'Estimate · extrapolated', shape: 'hatch' }, { color: COLORS.snpp, label: 'VIIRS S-NPP · recorded', shape: 'dot' }]}/>
    {active === 'common' && !estimateAvailable ? <div className="chart-empty">No estimate available: {series.reason ?? 'no compatible model is registered.'}</div> : <AnnualChart series={series} modis={modis} mode={active} height={compact ? 260 : 320}/>}
    <p className="caption" aria-live="polite">
      {active === 'raw' && (r ? <>Same place, same years, same fires. VIIRS S-NPP recorded <strong>{fmt(r.ratio, 1)}× as many</strong> <Unit/> as {SAT_NAME[modis]} in {region.short} ({r.first}–{r.last}). Much of that gap is the instrument: VIIRS has finer pixels and picks up smaller, cooler fires than MODIS can.</> : <>The archive has no complete year in which both satellites recorded {region.short}.</>)}
      {active === 'splice' && r && <>A record that switches from MODIS to VIIRS when S-NPP begins inherits a step of about <strong>{fmt(r.ratio, 1)}×</strong> — the gap measured while both flew ({r.first}–{r.last}). Read naively, that step looks like fire activity rising.</>}
      {active === 'common' && estimateAvailable && <>Bars: what the model estimates S-NPP <em>would have</em> recorded, computed from {SAT_NAME[modis]}. Dots: what S-NPP actually recorded. Hatched bars are extrapolations{region.role === 'fitted' ? ' (before S-NPP flew), which no observation can check' : ' — this region was never used to fit the model'}.</>}
    </p>
    <details className="table-view"><summary>View these numbers as a table</summary><div className="table-scroll"><table><thead><tr><th>Year</th><th>{SAT_NAME[modis]} recorded</th><th>VIIRS S-NPP recorded</th><th>Estimate (S-NPP scale)</th></tr></thead><tbody>{[...new Set([...data.m, ...data.n].map(p => p.year))].sort().map(y => { const e = annual(new Map([...series.estimate].filter(([k]) => k.startsWith(String(y))).map(([k, v]) => [k, { value: v.estimate }])))[0]; return <tr key={y}><td>{y}</td><td>{data.m.find(p => p.year === y) ? fmt(data.m.find(p => p.year === y)!.value) : '—'}</td><td>{data.n.find(p => p.year === y) ? fmt(data.n.find(p => p.year === y)!.value) : '—'}</td><td>{e ? fmt(e.value) : '—'}</td></tr> })}</tbody></table></div><p className="fine">Active cell-days per complete calendar year. Partial years are omitted, never scaled up.</p></details>
  </div>
}
