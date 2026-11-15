import { useCallback, useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { Discover } from './Discover'
import { Explore } from './Explore'
import { Compare } from './Compare'
import { BurningCalendar } from './CalendarView'
import { Evidence } from './Evidence'
import { REGIONS, getJSON, type EvidenceRecord, type Region } from './api'

const TABS = ['Discover', 'Explore', 'Compare', 'Calendar', 'Evidence'] as const
type Tab = typeof TABS[number]

export default function App() {
  const [tab, setTab] = useState<Tab>('Discover')
  const [region, setRegion] = useState<Region>(REGIONS[0])
  const [modis, setModis] = useState('A')
  const [evidence, setEvidence] = useState<EvidenceRecord | null>(null)
  const [evidenceState, setEvidenceState] = useState<'closed' | 'loading' | 'open' | 'error'>('closed')
  const request = useRef(0)
  const go = useCallback((t: string) => { setTab(t as Tab); window.scrollTo({ top: 0 }) }, [])
  const select = useCallback(async (id: string) => {
    const current = ++request.current
    setEvidence(null); setEvidenceState('loading')
    try { const value = await getJSON<EvidenceRecord>(`/api/evidence/${id}`); if (current === request.current) { setEvidence(value); setEvidenceState('open') } }
    catch { if (current === request.current) setEvidenceState('error') }
  }, [])
  const close = useCallback(() => { ++request.current; setEvidence(null); setEvidenceState('closed') }, [])
  const drawerOpen = evidenceState !== 'closed'
  useEffect(() => {
    if (!drawerOpen) return
    const previous = document.activeElement as HTMLElement | null
    const drawer = document.querySelector('.drawer') as HTMLElement | null
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); close() }
      if (e.key === 'Tab' && drawer) {
        const controls = drawer.querySelectorAll<HTMLElement>('button,a[href],input,select,[tabindex="0"]')
        const first = controls[0], last = controls[controls.length - 1]
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus() }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus() }
      }
    }
    drawer?.querySelector<HTMLElement>('button')?.focus()
    document.addEventListener('keydown', handler)
    return () => { document.removeEventListener('keydown', handler); previous?.focus() }
  }, [drawerOpen, close])
  return <div className="app">
    <a className="skip" href="#main">Skip to content</a>
    <header className="masthead">
      <button type="button" className="brand" onClick={() => go('Discover')} aria-label="FIRETRUST home"><span className="brand-mark" aria-hidden="true"><i/><i/></span><span className="brand-name">FIRETRUST</span></button>
      <nav aria-label="Sections">{TABS.map((t, i) => <button key={t} type="button" className="nav-item" aria-current={tab === t ? 'page' : undefined} onClick={() => go(t)}><span className="nav-index">{i + 1}</span>{t}</button>)}</nav>
      <label className="region-pick"><span>Region</span><select aria-label="Region" value={region.id} onChange={e => setRegion(REGIONS.find(r => r.id === e.target.value) ?? region)}>{REGIONS.map(r => <option key={r.id} value={r.id}>{r.label}</option>)}{region.role === 'custom' && <option value="custom">Custom area</option>}</select></label>
    </header>
    <main id="main" tabIndex={-1}>
      {tab === 'Discover' && <Discover region={region} modis={modis} go={go}/>}
      {tab === 'Explore' && <Explore region={region} setRegion={setRegion} onSelect={select}/>}
      {tab === 'Compare' && <Compare region={region} modis={modis} setModis={setModis}/>}
      {tab === 'Calendar' && <BurningCalendar region={region} modis={modis} setModis={setModis}/>}
      {tab === 'Evidence' && <Evidence region={region} onSelect={select}/>}
    </main>
    <footer><p><strong>FIRETRUST</strong> is an independent research prototype built for the NASA Space Apps Challenge. It is not affiliated with or endorsed by NASA and is not an emergency alert service.</p><p>Data: <a href="https://firms.modaps.eosdis.nasa.gov/" target="_blank" rel="noreferrer">NASA FIRMS</a> active-fire archives (MODIS Collection 6.1, VIIRS S-NPP). Basemap: Natural Earth.</p></footer>
    {drawerOpen && <div className="drawer-backdrop" onClick={close}><aside className="drawer" aria-label="Observation evidence" role="dialog" aria-modal="true" onClick={e => e.stopPropagation()}>
      <button type="button" className="close" aria-label="Close evidence" onClick={close}><X size={18}/></button>
      <p className="eyebrow">Trace the observation</p><h2>Evidence record</h2>
      {evidenceState === 'loading' && <p role="status">Loading evidence…</p>}
      {evidenceState === 'error' && <p className="error" role="alert">This record could not be loaded.</p>}
      {evidence && <><p className="fine">{evidence.interpretation}</p>
        <dl className="record">{Object.entries(evidence.detection).map(([k, v]) => <div key={k}><dt>{k.replaceAll('_', ' ')}</dt><dd>{v === null || v === '' ? 'missing' : String(v)}</dd></div>)}</dl>
        <h3>Source files</h3>{evidence.batches.map(b => <div className="source" key={b.id}><strong>{b.source}</strong><span>SHA-256</span><code>{b.id}</code></div>)}</>}
    </aside></div>}
  </div>
}
