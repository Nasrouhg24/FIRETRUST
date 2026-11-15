import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import { LocateFixed, SlidersHorizontal } from 'lucide-react'
import { Failure, Loading } from './shared'
import { REGIONS, customRegion, fmt, regionQuery, useJSON, type Analytics, type Detection, type Region } from './api'

const dateLabel = (s: string | null) => s ? new Date(s).toLocaleDateString('en', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' }) : '—'

const WORLD: [number, number, number, number] = [-100, -45, 60, 60]

function ObservationMap({ rows, bounds, overview, selectedId, onSelect, onPickRegion, onOverview }: { rows: Detection[]; bounds: Region['bounds']; overview: boolean; selectedId: string; onSelect: (id: string) => void; onPickRegion: (id: string) => void; onOverview: () => void }) {
  const element = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const layer = useRef<L.LayerGroup | null>(null)
  const [basemapFailed, setBasemapFailed] = useState(false)
  const outlines = useRef<L.LayerGroup | null>(null)
  const fit = () => {
    const m = map.current; if (!m) return
    m.stop()
    const b = overview ? WORLD : bounds
    if (b) m.fitBounds([[b[1], b[0]], [b[3], b[2]]], { padding: [24, 24], maxZoom: 8, animate: false })
    else m.setView([23, 5], 2, { animate: false })
  }
  useEffect(() => {
    if (!element.current) return
    const m = L.map(element.current, { zoomControl: false, preferCanvas: true, minZoom: 2 }).setView([23, 5], 2)
    L.control.zoom({ position: 'bottomright' }).addTo(m)
    m.createPane('countries').style.zIndex = '250'
    const controller = new AbortController()
    fetch('/world.geojson', { signal: controller.signal }).then(r => r.json()).then(geo => {
      if (controller.signal.aborted) return
      L.geoJSON(geo, { pane: 'countries', style: { renderer: L.svg({ pane: 'countries' }), color: '#4a525d', weight: .6, fillColor: '#20252c', fillOpacity: 1 }, interactive: false }).addTo(m)
      m.attributionControl.addAttribution('<a href="https://www.naturalearthdata.com/">Natural Earth</a>')
    }).catch(() => { if (!controller.signal.aborted) setBasemapFailed(true) })
    map.current = m; outlines.current = L.layerGroup().addTo(m); layer.current = L.layerGroup().addTo(m)
    return () => { controller.abort(); m.stop(); m.remove(); map.current = null }
  }, [])
  useEffect(() => {
    const l = layer.current; if (!l) return
    l.clearLayers()
    rows.forEach(r => L.circleMarker([r.latitude, r.longitude], { radius: 3, weight: 0, fillColor: r.sensor === 'VIIRS' ? '#3987e5' : '#d95926', fillOpacity: .75 }).on('click', () => onSelect(r.id)).addTo(l))
  }, [rows, onSelect])
  useEffect(() => {
    const g = outlines.current; if (!g) return
    g.clearLayers()
    REGIONS.forEach(r => {
      if (!r.bounds) return
      const active = r.id === selectedId
      L.rectangle([[r.bounds[1], r.bounds[0]], [r.bounds[3], r.bounds[2]]], { color: active ? '#e8b46a' : '#8d959e', weight: active ? 2 : 1, dashArray: active ? undefined : '4 4', fillOpacity: 0, interactive: true, bubblingMouseEvents: false })
        .bindTooltip(`${r.short}${r.role === 'fitted' ? ' · model fitted here' : ''}`, { sticky: true, direction: 'top' })
        .on('click', () => onPickRegion(r.id)).addTo(g)
    })
  }, [selectedId, onPickRegion])
  useEffect(fit, [bounds?.join(','), overview])
  return <div className="map-wrap"><div className="map" ref={element} aria-label="Map of satellite fire detections"/>
    <div className="map-actions"><button type="button" className="map-reset" onClick={onOverview} aria-pressed={overview}>All regions</button><button type="button" className="map-reset" title="Re-centre on the selected region" aria-label="Re-centre map" onClick={fit}><LocateFixed size={16}/></button></div>
    <ul className="legend map-legend"><li><span className="key key-dot" style={{ ['--c' as string]: '#d95926' }}/>MODIS detection</li><li><span className="key key-dot" style={{ ['--c' as string]: '#3987e5' }}/>VIIRS detection</li></ul>
    {basemapFailed && <div className="map-warning">Basemap unavailable. Detection points remain visible.</div>}</div>
}

export function Explore({ region, setRegion, onSelect }: { region: Region; setRegion: (r: Region) => void; onSelect: (id: string) => void }) {
  const [sensor, setSensor] = useState('')
  const [start, setStart] = useState(''), [end, setEnd] = useState('')
  const [open, setOpen] = useState(false)
  const [bbox, setBbox] = useState('')
  const [overview, setOverview] = useState(true)
  const lastRegion = useRef(region.id)
  useEffect(() => { if (lastRegion.current !== region.id) { lastRegion.current = region.id; setOverview(false) } }, [region.id])
  const pick = (id: string) => { const r = REGIONS.find(x => x.id === id); if (r) { setRegion(r); setOverview(false) } }
  const q = regionQuery(region, { sensor, start, end }).toString()
  const summary = useJSON<Analytics>(`/api/analytics?${q}`)
  const points = useJSON<{ items: Detection[]; total: number }>(`/api/detections?${q}&limit=5000`)
  const rows = points.data?.items ?? []
  const error = summary.error || points.error
  return <>
    <section className="page-head"><p className="eyebrow">Explore</p><h1>What the satellites recorded.</h1><p className="lede">Each dot is one detection by one instrument on one pass over {region.short}. Dashed outlines mark the other regions in the archive — click one to switch. Select a dot to trace it to its NASA source file.</p></section>
    <div className="controls">
      <label className="field">Instrument<select aria-label="Sensor" value={sensor} onChange={e => setSensor(e.target.value)}><option value="">MODIS and VIIRS</option><option value="MODIS">MODIS only</option><option value="VIIRS">VIIRS only</option></select></label>
      <button type="button" className="ghost" aria-expanded={open} onClick={() => setOpen(!open)}><SlidersHorizontal size={14} aria-hidden="true"/> Dates and custom area</button>
    </div>
    {open && <div className="controls advanced">
      <label className="field">From (UTC, inclusive)<input type="date" value={start} onChange={e => setStart(e.target.value)}/></label>
      <label className="field">Until (UTC, exclusive)<input type="date" value={end} onChange={e => setEnd(e.target.value)}/></label>
      <button type="button" className="ghost" onClick={() => { setStart(''); setEnd('') }}>Clear dates</button>
      <label className="field">Custom area (west,south,east,north)<input aria-label="Custom bounding box" placeholder="-9.6,36.8,-6,42.2" value={bbox} onChange={e => setBbox(e.target.value)}/></label>
      <button type="button" className="ghost" onClick={() => setRegion(customRegion(bbox.trim()))} disabled={!bbox.trim()}>Apply area</button>
    </div>}
    {error && <Failure message={error} retry={() => { summary.retry(); points.retry() }}/>}
    <section className="panel map-panel">
      <ObservationMap rows={rows} bounds={region.bounds} overview={overview} selectedId={region.id} onSelect={onSelect} onPickRegion={pick} onOverview={() => setOverview(true)}/>
      {(summary.loading || points.loading) && <Loading what="NASA detections"/>}
      {summary.data && <dl className="statline">
        <div><dt>{fmt(summary.data.detections)}</dt><dd>detections in this selection</dd></div>
        <div><dt>{fmt(summary.data.sensors.MODIS ?? 0)}</dt><dd>by MODIS</dd></div>
        <div><dt>{fmt(summary.data.sensors.VIIRS ?? 0)}</dt><dd>by VIIRS</dd></div>
        <div><dt className="small">{dateLabel(summary.data.first_observation)} – {dateLabel(summary.data.last_observation)}</dt><dd>first and latest record held</dd></div>
      </dl>}
      {summary.data && summary.data.detections === 0 && <div className="empty"><h3>No observations in this selection.</h3><p>Nothing in the archive we hold matches these filters. That is not evidence that nothing burned.</p></div>}
      {points.data && <p className="fine">Map shows the {fmt(rows.length)} most recent of {fmt(points.data.total)} detections; totals use the full selection. A detection is one satellite pixel flagged as hot — several can belong to one fire, and VIIRS pixels are about seven times smaller than MODIS pixels.</p>}
    </section>
  </>
}
