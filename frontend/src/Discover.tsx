import { ArrowRight } from 'lucide-react'
import { IllusionPanel, Loading, Failure, TrustNote, overlapRatio, useMethod, useScience, useValidation } from './shared'
import { SAT_NAME, fmt, pct, type Region } from './api'

export function Discover({ region, modis, go }: { region: Region; modis: string; go: (tab: string) => void }) {
  const { series, error, loading, retry } = useScience(region, modis)
  const aqua = useMethod('A').data?.model, terra = useMethod('T').data?.model
  const method = useMethod(modis).data
  const validation = useValidation().data
  const ratio = series ? overlapRatio(series, modis) : null
  const a = aqua?.test[aqua.selected_model], t = terra?.test[terra.selected_model]
  const transfer = validation?.transfer.A ? Object.values(validation.transfer.A) : []
  return <>
    <section className="hero">
      <p className="eyebrow">MODIS × VIIRS active-fire harmonization</p>
      <h1>Not every change in satellite detections is a change in fire.</h1>
      <p className="lede">Two generations of NASA instruments watch the same fires and report different numbers. FIRETRUST shows the difference, estimates a common scale, and says plainly how far that estimate can be trusted.</p>
    </section>
    <section className="panel feature" aria-labelledby="illusion-title">
      <header className="panel-head"><div><h2 id="illusion-title">The sensor illusion, in {region.short}</h2><p className="sub">Real NASA FIRMS archive records · {region.record}</p></div></header>
      {loading && <Loading what="the satellite record"/>}{error && <Failure message={error} retry={retry}/>}
      {series && <IllusionPanel region={region} modis={modis} series={series} compact/>}
      {series && <TrustNote region={region} modis={modis} validation={validation} method={method} brief/>}
    </section>
    <section className="facts" aria-label="Key findings">
      <article><span className="fact-value">{ratio ? `${fmt(ratio.ratio, 1)}×` : '—'}</span><h3>Same fires, different count</h3><p>{ratio ? <>VIIRS S-NPP recorded {fmt(ratio.ratio, 1)} times the activity {SAT_NAME[modis]} did in {region.short}, {ratio.first}–{ratio.last}.</> : <>No overlapping complete years here.</>}</p></article>
      <article><span className="fact-value">{a && t ? `${fmt(a.mae, 0)} vs ${fmt(t.mae, 0)}` : '—'}</span><h3>The MODIS satellite matters</h3><p>Average monthly error against S-NPP on held-out years: Aqua {a ? fmt(a.mae, 1) : '—'}, Terra {t ? fmt(t.mae, 1) : '—'} active cell-days. Aqua did better in every setting we tested — not a universal rule.</p></article>
      <article><span className="fact-value">{transfer.length ? `${pct(Math.min(...transfer.map(r => r.model_wape)))}–${pct(Math.max(...transfer.map(r => r.model_wape)))}` : '—'}</span><h3>It does not travel well</h3><p>Fitted in Portugal, the model ran low in every other country tested{transfer.length ? `, with errors of ${pct(Math.min(...transfer.map(r => r.model_wape)))}–${pct(Math.max(...transfer.map(r => r.model_wape)))} of the S-NPP total` : ''}. We show that instead of hiding it.</p></article>
    </section>
    <section className="steps" aria-label="Continue">
      {[['Explore', 'See the detections', 'Every point on the map links to its NASA source file.'], ['Compare', 'Open the Sensor Illusion Detector', 'Month by month: recorded MODIS, recorded VIIRS, and the estimate.'], ['Calendar', 'Browse the record', 'Recorded activity, estimates and missing data, kept visibly apart.'], ['Evidence', 'Check our work', 'Validation results, limits and data provenance.']].map(([tab, title, text]) =>
        <button key={tab} type="button" className="step" onClick={() => go(tab)}><span className="step-tag">{tab}</span><strong>{title}</strong><span>{text}</span><ArrowRight size={16} aria-hidden="true"/></button>)}
    </section>
  </>
}
