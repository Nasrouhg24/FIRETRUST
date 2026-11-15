import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { COLORS, SAT_NAME, annual, fmt, monthLabel, type Estimate, type Series } from './api'

export function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(0)
  useEffect(() => {
    if (!ref.current) return
    const observer = new ResizeObserver(entries => setWidth(Math.round(entries[0].contentRect.width)))
    observer.observe(ref.current)
    return () => observer.disconnect()
  }, [])
  return [ref, width] as const
}

function niceMax(v: number) {
  if (v <= 0) return 1
  const p = 10 ** Math.floor(Math.log10(v))
  const m = v / p
  return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10) * p
}
const ticks = (max: number) => [0, .25, .5, .75, 1].map(t => t * max)
const compact = (n: number) => n >= 1000 ? `${parseFloat((n / 1000).toFixed(2))}k` : fmt(n, n % 1 ? (n < 10 ? 2 : 1) : 0)

export function bandText(e: Estimate | undefined) {
  if (!e) return 'no estimate'
  if (e.lower !== null && e.upper !== null) return `residual band ${fmt(e.lower)}–${fmt(e.upper)}`
  if (e.interval_status === 'unavailable_outside_calibration_activity') return 'no band: activity above the calibrated range'
  return 'no band: outside what the model was fitted on'
}

export function Legend({ items }: { items: { color: string; label: string; shape?: 'line' | 'bar' | 'dot' | 'band' | 'hatch' }[] }) {
  return <ul className="legend">{items.map(i => <li key={i.label}><span className={`key key-${i.shape ?? 'line'}`} style={{ ['--c' as string]: i.color }}/>{i.label}</li>)}</ul>
}

function Tooltip({ x, width, children }: { x: number; width: number; children: ReactNode }) {
  const left = x > width / 2
  return <div className="tip" role="presentation" style={left ? { right: width - x + 12 } : { left: x + 12 }}>{children}</div>
}
const TipRow = ({ color, label, value, note }: { color?: string; label: string; value: string; note?: string }) =>
  <div className="tip-row">{color && <span className="tip-key" style={{ background: color }}/>}<span className="tip-label">{label}</span><strong>{value}</strong>{note && <em>{note}</em>}</div>

// ---------------------------------------------------------------- annual illusion chart
export type IllusionMode = 'raw' | 'splice' | 'common'
export function AnnualChart({ series, modis, mode, height = 300 }: { series: Series; modis: string; mode: IllusionMode; height?: number }) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)
  const data = useMemo(() => {
    const m = annual(series.observed[modis]); const n = annual(series.observed.N)
    const e = annual(new Map([...series.estimate].map(([k, v]) => [k, { value: v.estimate }])), month => series.estimate.get(month)?.model_status === 'extrapolated')
    const years = [...new Set([...m, ...n].map(p => p.year))].sort((a, b) => a - b)
    return { m: new Map(m.map(p => [p.year, p])), n: new Map(n.map(p => [p.year, p])), e: new Map(e.map(p => [p.year, p])), years, firstN: n[0]?.year }
  }, [series, modis])
  const { years } = data
  const pad = { l: 46, r: 12, t: 16, b: 30 }
  const w = Math.max(width, 280), plotW = w - pad.l - pad.r, plotH = height - pad.t - pad.b
  const values = years.flatMap(y => mode === 'raw' ? [data.m.get(y)?.value ?? 0, data.n.get(y)?.value ?? 0] : mode === 'splice' ? [(data.firstN && y >= data.firstN ? data.n.get(y)?.value : data.m.get(y)?.value) ?? 0] : [data.e.get(y)?.value ?? 0, data.n.get(y)?.value ?? 0])
  const max = niceMax(Math.max(1, ...values))
  const band = plotW / Math.max(1, years.length)
  const y = (v: number) => pad.t + plotH - v / max * plotH
  const bar = (x: number, bw: number, v: number, fill: string, key: string) => <path key={key} d={`M${x},${y(0)} V${y(v) + Math.min(3, (y(0) - y(v)) / 2)} q0,-3 3,-3 H${x + bw - 3} q3,0 3,3 V${y(0)} Z`} fill={fill}/>
  const labelEvery = Math.ceil(years.length / Math.max(1, Math.floor(plotW / 44)))
  const hoverYear = hover === null ? null : years[hover]
  if (!years.length) return <div ref={ref} className="chart-empty">No complete calendar years in the archive for this selection.</div>
  return <div ref={ref} className="chart" style={{ height }} onPointerLeave={() => setHover(null)}
    onPointerMove={ev => { const box = ev.currentTarget.getBoundingClientRect(); const i = Math.floor((ev.clientX - box.left - pad.l) / band); setHover(i >= 0 && i < years.length ? i : null) }}>
    <svg width={w} height={height} role="img" aria-label={`Annual active cell-days by satellite, ${years[0]} to ${years[years.length - 1]}. ${mode === 'splice' ? 'MODIS until S-NPP begins, then S-NPP.' : mode === 'common' ? 'Model estimates on the S-NPP scale with observed S-NPP.' : 'MODIS and S-NPP as recorded.'}`}>
      <defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="6" height="6" fill={COLORS.estimate} opacity=".28"/><line x1="0" y1="0" x2="0" y2="6" stroke={COLORS.estimate} strokeWidth="2.4"/></pattern></defs>
      {ticks(max).map(t => <g key={t}><line x1={pad.l} x2={w - pad.r} y1={y(t)} y2={y(t)} stroke={COLORS.grid} strokeWidth="1"/><text x={pad.l - 8} y={y(t) + 4} textAnchor="end" className="axis">{compact(t)}</text></g>)}
      {hover !== null && <rect x={pad.l + hover * band} y={pad.t} width={band} height={plotH} fill="#fff" opacity=".045"/>}
      {years.map((yr, i) => {
        const x0 = pad.l + i * band, inner = Math.max(4, band - Math.max(4, band * .22)), off = (band - inner) / 2
        if (mode === 'raw') { const bw = (inner - 2) / 2; return <g key={yr}>{data.m.has(yr) && bar(x0 + off, bw, data.m.get(yr)!.value, COLORS.modis, 'm')}{data.n.has(yr) && bar(x0 + off + bw + 2, bw, data.n.get(yr)!.value, COLORS.snpp, 'n')}</g> }
        if (mode === 'splice') { const useN = Boolean(data.firstN && yr >= data.firstN); const p = useN ? data.n.get(yr) : data.m.get(yr); return <g key={yr}>{p && bar(x0 + off, inner, p.value, useN ? COLORS.snpp : COLORS.modis, 's')}</g> }
        const e = data.e.get(yr), n = data.n.get(yr)
        return <g key={yr}>{e && bar(x0 + off, inner, e.value, e.flagged ? 'url(#hatch)' : COLORS.estimate, 'e')}{n && <circle cx={x0 + band / 2} cy={y(n.value)} r={Math.min(5, Math.max(3.5, band / 5))} fill={COLORS.snpp} stroke={COLORS.surface} strokeWidth="2"/>}</g>
      })}
      {mode !== 'common' && data.firstN && years[0] < data.firstN && (() => { const x = pad.l + years.indexOf(data.firstN) * band; return <g><line x1={x} x2={x} y1={pad.t - 4} y2={y(0)} stroke={COLORS.muted} strokeDasharray="3 4"/><text x={x + 6} y={pad.t + 22} className="axis annotation">S-NPP begins {data.firstN}</text></g> })()}
      {years.map((yr, i) => i % labelEvery === 0 && <text key={yr} x={pad.l + i * band + band / 2} y={height - 10} textAnchor="middle" className="axis">{yr}</text>)}
      <text x={pad.l} y={10} className="axis unit">active cell-days per year</text>
    </svg>
    {hoverYear !== null && <Tooltip x={pad.l + (hover! + .5) * band} width={w}>
      <div className="tip-title">{hoverYear}</div>
      <TipRow color={COLORS.modis} label={SAT_NAME[modis]} value={data.m.has(hoverYear) ? fmt(data.m.get(hoverYear)!.value) : 'no complete year'}/>
      <TipRow color={COLORS.snpp} label="VIIRS S-NPP" value={data.n.has(hoverYear) ? fmt(data.n.get(hoverYear)!.value) : 'not recorded'}/>
      {mode === 'common' && <TipRow color={COLORS.estimate} label="Estimate (S-NPP scale)" value={data.e.has(hoverYear) ? fmt(data.e.get(hoverYear)!.value) : 'unavailable'} note={data.e.get(hoverYear)?.flagged ? 'extrapolated' : undefined}/>}
    </Tooltip>}
  </div>
}

// ---------------------------------------------------------------- monthly comparison chart
export function MonthlyChart({ series, modis, months, show, cursor, pinned, onCursor, height = 320 }: { series: Series; modis: string; months: string[]; show: { modis: boolean; snpp: boolean; estimate: boolean }; cursor: number | null; pinned: number | null; onCursor: (i: number | null) => void; height?: number }) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const pad = { l: 46, r: 14, t: 16, b: 30 }
  const w = Math.max(width, 280), plotW = w - pad.l - pad.r, plotH = height - pad.t - pad.b
  const M = series.observed[modis], N = series.observed.N, E = series.estimate
  const max = niceMax(Math.max(1, ...months.flatMap(m => [show.modis ? M.get(m)?.value ?? 0 : 0, show.snpp ? N.get(m)?.value ?? 0 : 0, show.estimate ? E.get(m)?.upper ?? E.get(m)?.estimate ?? 0 : 0])))
  const x = (i: number) => pad.l + (months.length < 2 ? plotW / 2 : i * plotW / (months.length - 1))
  const y = (v: number) => pad.t + plotH - v / max * plotH
  const line = (get: (m: string) => number | undefined) => months.map((m, i) => { const v = get(m); const prev = i > 0 ? get(months[i - 1]) : undefined; return v === undefined ? '' : `${prev === undefined ? 'M' : 'L'}${x(i).toFixed(1)},${y(v).toFixed(1)}` }).join(' ')
  const bands: string[] = []
  let run: number[] = []
  months.forEach((m, i) => { const e = E.get(m); if (e && e.lower !== null && e.upper !== null) run.push(i); if ((!e || e.lower === null || i === months.length - 1) && run.length) { const top = run.map(j => `${x(j).toFixed(1)},${y(E.get(months[j])!.upper!).toFixed(1)}`); const bottom = run.slice().reverse().map(j => `${x(j).toFixed(1)},${y(E.get(months[j])!.lower!).toFixed(1)}`); bands.push(run.length === 1 ? `M${x(run[0]) - 3},${y(E.get(months[run[0]])!.upper!)} h6 V${y(E.get(months[run[0]])!.lower!)} h-6 Z` : `M${top.join(' L')} L${bottom.join(' L')} Z`); run = [] } })
  const dots = months.length <= 36
  const mark = cursor ?? pinned
  const m = mark === null || mark >= months.length ? null : months[mark]
  const e = m ? E.get(m) : undefined
  if (!months.length) return <div ref={ref} className="chart-empty">No recorded months in this window.</div>
  return <div ref={ref} className="chart" style={{ height }} onPointerLeave={() => onCursor(null)}
    onPointerMove={ev => { const box = ev.currentTarget.getBoundingClientRect(); const i = Math.round((ev.clientX - box.left - pad.l) / (plotW / Math.max(1, months.length - 1))); onCursor(Math.max(0, Math.min(months.length - 1, i))) }}>
    <svg width={w} height={height} role="img" aria-label={`Monthly active cell-days: ${SAT_NAME[modis]} as recorded, VIIRS S-NPP as recorded, and the model estimate on the S-NPP scale, ${monthLabel(months[0])} to ${monthLabel(months[months.length - 1])}`}>
      {ticks(max).map(t => <g key={t}><line x1={pad.l} x2={w - pad.r} y1={y(t)} y2={y(t)} stroke={COLORS.grid}/><text x={pad.l - 8} y={y(t) + 4} textAnchor="end" className="axis">{compact(t)}</text></g>)}
      {months.map((mo, i) => mo.endsWith('-01') && (months.length <= 96 || Number(mo.slice(0, 4)) % 2 === 0) && <text key={mo} x={x(i)} y={height - 10} textAnchor="middle" className="axis">{mo.slice(0, 4)}</text>)}
      {show.estimate && bands.map((d, i) => <path key={i} d={d} fill={COLORS.estimate} opacity=".2"/>)}
      {show.modis && <path d={line(k => M.get(k)?.value)} fill="none" stroke={COLORS.modis} strokeWidth="2" strokeLinejoin="round"/>}
      {show.snpp && <path d={line(k => N.get(k)?.value)} fill="none" stroke={COLORS.snpp} strokeWidth="2" strokeLinejoin="round"/>}
      {show.estimate && <path d={line(k => E.get(k)?.estimate)} fill="none" stroke={COLORS.estimate} strokeWidth="2" strokeLinejoin="round" strokeDasharray="5 3"/>}
      {dots && months.map((mo, i) => <g key={mo}>{show.modis && M.has(mo) && <circle cx={x(i)} cy={y(M.get(mo)!.value)} r="2.5" fill={COLORS.modis}/>}{show.snpp && N.has(mo) && <circle cx={x(i)} cy={y(N.get(mo)!.value)} r="2.5" fill={COLORS.snpp}/>}</g>)}
      {m && mark !== null && <g><line x1={x(mark)} x2={x(mark)} y1={pad.t} y2={pad.t + plotH} stroke={COLORS.muted} strokeWidth="1" strokeDasharray={cursor === null ? '2 3' : undefined}/>
        {show.modis && M.has(m!) && <circle cx={x(mark)} cy={y(M.get(m!)!.value)} r="4.5" fill={COLORS.modis} stroke={COLORS.surface} strokeWidth="2"/>}
        {show.snpp && N.has(m!) && <circle cx={x(mark)} cy={y(N.get(m!)!.value)} r="4.5" fill={COLORS.snpp} stroke={COLORS.surface} strokeWidth="2"/>}
        {show.estimate && e && <circle cx={x(mark)} cy={y(e.estimate)} r="4.5" fill={COLORS.estimate} stroke={COLORS.surface} strokeWidth="2"/>}</g>}
      <text x={pad.l} y={10} className="axis unit">active cell-days per month</text>
    </svg>
    {m && cursor !== null && <Tooltip x={x(cursor)} width={w}>
      <div className="tip-title">{monthLabel(m)}</div>
      <TipRow color={COLORS.modis} label={`${SAT_NAME[modis]} recorded`} value={M.has(m) ? fmt(M.get(m)!.value) : 'no record'}/>
      <TipRow color={COLORS.snpp} label="VIIRS S-NPP recorded" value={N.has(m) ? fmt(N.get(m)!.value) : 'no record'}/>
      <TipRow color={COLORS.estimate} label="Estimate (S-NPP scale)" value={e ? fmt(e.estimate, 1) : 'unavailable'}/>
      {e && <div className="tip-note">{bandText(e)}</div>}
    </Tooltip>}
  </div>
}

// ---------------------------------------------------------------- generic small line chart (one axis)
export type LineSeries = { name: string; color: string; points: { x: number; y: number }[] }
export function LineChart({ series, unit, height = 220, yMin, valueDigits = 2, label }: { series: LineSeries[]; unit: string; height?: number; yMin?: number; valueDigits?: number; label: string }) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)
  const xs = [...new Set(series.flatMap(s => s.points.map(p => p.x)))].sort((a, b) => a - b)
  const ys = series.flatMap(s => s.points.map(p => p.y))
  const pad = { l: 46, r: 14, t: 16, b: 28 }
  const w = Math.max(width, 260), plotW = w - pad.l - pad.r, plotH = height - pad.t - pad.b
  const lo = yMin ?? Math.floor(Math.min(...ys)), hi = yMin === 0 ? niceMax(Math.max(...ys)) : Math.ceil(Math.max(...ys))
  const x = (v: number) => pad.l + (xs.length < 2 ? plotW / 2 : (xs.indexOf(v)) * plotW / (xs.length - 1))
  const y = (v: number) => pad.t + plotH - (v - lo) / Math.max(1e-9, hi - lo) * plotH
  if (!xs.length) return <div ref={ref} className="chart-empty">No data available.</div>
  const every = Math.ceil(xs.length / Math.max(1, Math.floor(plotW / 44)))
  return <div ref={ref} className="chart" style={{ height }} onPointerLeave={() => setHover(null)}
    onPointerMove={ev => { const box = ev.currentTarget.getBoundingClientRect(); const i = Math.round((ev.clientX - box.left - pad.l) / (plotW / Math.max(1, xs.length - 1))); setHover(Math.max(0, Math.min(xs.length - 1, i))) }}>
    <svg width={w} height={height} role="img" aria-label={label}>
      {[0, .25, .5, .75, 1].map(t => { const v = lo + t * (hi - lo); return <g key={t}><line x1={pad.l} x2={w - pad.r} y1={y(v)} y2={y(v)} stroke={COLORS.grid}/><text x={pad.l - 8} y={y(v) + 4} textAnchor="end" className="axis">{fmt(v, (hi - lo) % 4 ? 2 : 0)}</text></g> })}
      {xs.map((v, i) => i % every === 0 && <text key={v} x={x(v)} y={height - 9} textAnchor="middle" className="axis">{v}</text>)}
      {series.map(s => <g key={s.name}><path d={s.points.map((p, i) => `${i ? 'L' : 'M'}${x(p.x).toFixed(1)},${y(p.y).toFixed(1)}`).join(' ')} fill="none" stroke={s.color} strokeWidth="2" strokeLinejoin="round"/>{s.points.map(p => <circle key={p.x} cx={x(p.x)} cy={y(p.y)} r="3" fill={s.color} stroke={COLORS.surface} strokeWidth="1.5"/>)}</g>)}
      {hover !== null && <line x1={x(xs[hover])} x2={x(xs[hover])} y1={pad.t} y2={pad.t + plotH} stroke={COLORS.muted}/>}
      <text x={pad.l} y={10} className="axis unit">{unit}</text>
    </svg>
    {hover !== null && <Tooltip x={x(xs[hover])} width={w}><div className="tip-title">{xs[hover]}</div>{series.map(s => { const p = s.points.find(q => q.x === xs[hover]); return <TipRow key={s.name} color={s.color} label={s.name} value={p ? fmt(p.y, valueDigits) : '—'}/> })}</Tooltip>}
  </div>
}
