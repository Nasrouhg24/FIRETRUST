import { useEffect, useState } from 'react'

// ---------------------------------------------------------------- regions
export type Region = {
  id: string; label: string; short: string
  api: { country?: string; bbox?: string }
  bounds: [number, number, number, number] | null // west, south, east, north; map framing only
  role: 'fitted' | 'transfer' | 'custom'
  record: string
}
export const REGIONS: Region[] = [
  { id: 'portugal_mainland', label: 'Portugal (mainland)', short: 'Portugal', api: { country: 'Portugal', bbox: '-9.6,36.8,-6,42.2' }, bounds: [-9.6, 36.8, -6, 42.2], role: 'fitted', record: 'MODIS 2000–2025 · S-NPP 2012–2025 · model fitted here' },
  { id: 'uruguay', label: 'Uruguay', short: 'Uruguay', api: { country: 'Uruguay', bbox: '-58.5,-35,-53,-30' }, bounds: [-58.5, -35, -53, -30], role: 'transfer', record: '2022–2025 · never used to fit the model' },
  { id: 'greece', label: 'Greece', short: 'Greece', api: { country: 'Greece' }, bounds: [19.3, 34.7, 28.3, 41.8], role: 'transfer', record: '2022–2025 · never used to fit the model' },
  { id: 'chile', label: 'Chile', short: 'Chile', api: { country: 'Chile' }, bounds: [-76, -56, -66, -17], role: 'transfer', record: '2022–2025 · never used to fit the model' },
  { id: 'zambia', label: 'Zambia', short: 'Zambia', api: { country: 'Zambia' }, bounds: [21.9, -18.1, 33.8, -8.2], role: 'transfer', record: '2022–2025 · never used to fit the model' },
]
export function customRegion(bbox: string): Region {
  const parts = bbox.split(',').map(Number)
  const ok = parts.length === 4 && parts.every(Number.isFinite) && parts[0] < parts[2] && parts[1] < parts[3]
  return { id: 'custom', label: 'Custom area', short: 'Custom area', api: { bbox }, bounds: ok ? parts as [number, number, number, number] : null, role: 'custom', record: 'custom coordinates · outside every evaluated region' }
}
export function regionQuery(region: Region, extra: Record<string, string | undefined> = {}) {
  const q = new URLSearchParams()
  if (region.api.country) q.set('country', region.api.country)
  if (region.api.bbox) q.set('bbox', region.api.bbox)
  Object.entries(extra).forEach(([k, v]) => { if (v) q.set(k, v) })
  return q
}

// ---------------------------------------------------------------- types
export type SeriesRow = { month: string; sensor: string; satellite: string; active_cell_days: number; detection_count: number; processing_status: string; coverage_status: string; archive_status?: string }
export type Estimate = { month: string; estimate: number; lower: number | null; upper: number | null; interval_status: string; model_status: string }
export type SeriesResponse = { items: SeriesRow[]; status: string; reason?: string; unit?: string; snapshot_id?: string; harmonized?: { status: string; reason?: string; items: Estimate[]; method?: string; model_id?: string; limitations?: string[]; target?: string } }
export type TestMetrics = { mae: number; wape: number | null; signed_bias: number; empirical_interval_coverage: number; by_region: Record<string, { mae: number; wape: number | null; signed_bias: number }>; band_within_calibration_activity?: { months_with_band: number; months_band_withheld: number } }
export type Model = { model_id: string; reference_satellite: string; modis_satellite: string; selected_model: string; years: Record<string, number[]>; validation: Record<string, { mae: number }>; test: Record<string, TestMetrics>; train_regions: string[]; calibration_modis_range?: [number, number] }
export type Method = { model: Model | null; independent_ground_validation: string; snapshot: { snapshot_id: string; rows: number } | null }
export type TransferRow = { months: number; model_wape: number; model_bias: number; raw_wape: number; model_mae: number; raw_mae: number }
export type BandRow = { months: number; share_withheld: number; coverage_all: number; coverage_when_shown: number | null; coverage_withheld: number | null } | null
export type Validation = {
  status: string; target: string; sources: string[]
  transfer: Record<string, Record<string, TransferRow>>
  bands: Record<string, { nominal: number; folds: number; fitted_region: BandRow; other_regions: BandRow }>
  nested_selection: { n_outer_folds: number; selection_frequency: Record<string, number>; mean_outer_mae_selected: number; mean_outer_mae_fixed: Record<string, number> } | null
  paired_satellite: { n_folds: number; aqua_better_folds: number; median_terra_over_aqua_mae: number | null; caveat: string } | null
  overpass: { scope: { country: string }; daytime_median_local_solar_hour: Record<string, Record<string, number>>; limits: string[] } | null
  first_acquired_after_choice?: { note: string; results: Record<string, { months: number; model_wape: number }> }
}
export type Detection = { id: string; latitude: number; longitude: number; acquired_at: string; sensor: string; satellite: string; confidence_class: string; frp: number | null; batch_id: string }
export type Cell = { date: string; south: number; west: number; count: number; sensors: Record<string, number>; flags: string[]; evidence_ids: string[] }
export type Analytics = { detections: number; sensors: Record<string, number>; confidence: Record<string, number>; flagged_cell_count: number; cell_count: number; first_observation: string | null; last_observation: string | null; cells: Cell[] }
export type Batch = { id: string; source: string; accepted: number; rejected: number; fetched_at: string; raw_path: string }
export type EvidenceRecord = { detection: Record<string, unknown>; batches: Batch[]; interpretation: string }
export type Anomaly = { month: string; sensor: string; satellite: string; active_cell_days: number; baseline_median: number; delta: number; baseline_years: number; robust_z: number | null }
export type AnomalyResponse = { items: Anomaly[]; status: string; reason?: string }

// ---------------------------------------------------------------- fetching (one request per URL; shared across screens)
const cache = new Map<string, Promise<unknown>>()
export async function getJSON<T>(url: string): Promise<T> {
  if (!cache.has(url)) {
    cache.set(url, fetch(url).then(async r => {
      if (!r.ok) { const body = await r.json().catch(() => ({})); throw new Error(typeof body.detail === 'string' ? body.detail : `Request failed (${r.status})`) }
      return r.json()
    }).catch(e => { cache.delete(url); throw e }))
  }
  return cache.get(url) as Promise<T>
}
export function useJSON<T>(url: string | null) {
  const [state, setState] = useState<{ url: string | null; data: T | null; error: string }>({ url: null, data: null, error: '' })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    if (!url) return
    let live = true
    getJSON<T>(url).then(data => { if (live) setState({ url, data, error: '' }) }).catch(e => { if (live) setState({ url, data: null, error: (e as Error).message }) })
    return () => { live = false }
  }, [url, attempt])
  const current = state.url === url
  return { data: current ? state.data : null, error: current ? state.error : '', loading: Boolean(url) && !current, retry: () => setAttempt(a => a + 1) }
}

// ---------------------------------------------------------------- derived series
export const SAT_NAME: Record<string, string> = { T: 'MODIS Terra', A: 'MODIS Aqua', N: 'VIIRS S-NPP' }
export type MonthValue = { value: number; archiveZero: boolean }
export type Series = { months: string[]; observed: Record<string, Map<string, MonthValue>>; estimate: Map<string, Estimate>; status: string; reason?: string }
export function buildSeries(response: SeriesResponse): Series {
  const observed: Record<string, Map<string, MonthValue>> = { T: new Map(), A: new Map(), N: new Map() }
  response.items.forEach(r => { if (observed[r.satellite] && r.processing_status === 'standard') observed[r.satellite].set(r.month, { value: r.active_cell_days, archiveZero: Boolean(r.archive_status) }) })
  const estimate = new Map((response.harmonized?.items ?? []).map(e => [e.month, e]))
  const months = [...new Set([...observed.T.keys(), ...observed.A.keys(), ...observed.N.keys()])].sort()
  return { months, observed, estimate, status: response.harmonized?.status ?? 'unavailable', reason: response.harmonized?.reason }
}
export type AnnualPoint = { year: number; value: number; months: number; flagged?: boolean }
/** Annual totals. Only complete years (12 months supplied by the archive) are returned; partial years are never scaled up. */
export function annual(values: Map<string, { value: number }>, flag?: (month: string) => boolean): AnnualPoint[] {
  const by = new Map<number, AnnualPoint>()
  values.forEach((v, month) => {
    const year = Number(month.slice(0, 4))
    const p = by.get(year) ?? { year, value: 0, months: 0, flagged: false }
    p.value += v.value; p.months += 1; if (flag?.(month)) p.flagged = true
    by.set(year, p)
  })
  return [...by.values()].filter(p => p.months === 12).sort((a, b) => a.year - b.year)
}
export const fmt = (n: number, digits = 0) => n.toLocaleString('en', { maximumFractionDigits: digits, minimumFractionDigits: 0 })
export const pct = (n: number | null | undefined, digits = 0) => n == null ? '—' : `${(n * 100).toFixed(digits)}%`
export const monthLabel = (m: string) => new Date(m + '-01T00:00:00Z').toLocaleDateString('en', { month: 'short', year: 'numeric', timeZone: 'UTC' })
export const COLORS = { modis: '#d95926', snpp: '#3987e5', estimate: '#199e70', terra: '#c98500', ink: '#e9e6df', muted: '#9aa3ad', grid: '#2a2f37', surface: '#15181d' }
