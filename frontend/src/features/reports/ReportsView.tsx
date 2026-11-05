import { useEffect, useMemo, useState } from 'react'
import { usePolling } from '../../hooks/usePolling'
import { apiGet } from '../../services/api'
import { fmtDateTime, fmtPct, fmtSeconds } from '../../services/format'
import type { Report, SiteInfo } from '../../types/api'

type Range = { start: string; end: string }

const PRESETS = [
  { label: 'Últimas 24 h', hours: 24 },
  { label: 'Últimos 7 días', hours: 168 },
  { label: 'Últimos 30 días', hours: 720 },
]

const presetRange = (hours: number): Range => {
  const end = new Date()
  return { start: new Date(end.getTime() - hours * 3600000).toISOString(), end: end.toISOString() }
}

const availClass = (v: number | null) => (v == null ? 'UNKNOWN' : v >= 99.9 ? 'UP' : v >= 99 ? 'warning' : 'DOWN')
const errMsg = (e: unknown) => (e instanceof Error ? e.message : String(e))

export default function ReportsView() {
  const [range, setRange] = useState<Range>(() => presetRange(168))
  const [presetLabel, setPresetLabel] = useState('Últimos 7 días')
  const [siteId, setSiteId] = useState('')
  const [csvStyle, setCsvStyle] = useState('es')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [report, setReport] = useState<Report | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const sites = usePolling(() => apiGet<SiteInfo[]>('/sites'), 600000)

  const qs = useMemo(() => {
    const p = new URLSearchParams({ start: range.start, end: range.end })
    if (siteId) p.set('site_id', siteId)
    return p.toString()
  }, [range, siteId])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    apiGet<Report>(`/reports/availability?${qs}`)
      .then(r => { if (!cancelled) { setReport(r); setError(null) } })
      .catch(e => { if (!cancelled) setError(errMsg(e)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [qs])

  const applyCustom = () => {
    if (!from || !to) return
    setRange({ start: new Date(`${from}T00:00:00`).toISOString(), end: new Date(`${to}T23:59:59`).toISOString() })
    setPresetLabel('Personalizado')
  }

  const devices = [...(report?.devices ?? [])].sort(
    (a, b) => (a.availability_pct ?? 101) - (b.availability_pct ?? 101))
  const services = [...(report?.services ?? [])].sort(
    (a, b) => (a.availability_pct ?? 101) - (b.availability_pct ?? 101))

  return (
    <main>
      <section className="panel">
        <h3 style={{ marginTop: 0 }}>Reporte de disponibilidad</h3>
        <div className="map-toolbar">
          {PRESETS.map(p => (
            <button key={p.label} className={presetLabel === p.label ? 'active' : ''}
              onClick={() => { setRange(presetRange(p.hours)); setPresetLabel(p.label) }}>
              {p.label}
            </button>
          ))}
          <input type="date" value={from} onChange={e => setFrom(e.target.value)} />
          <input type="date" value={to} onChange={e => setTo(e.target.value)} />
          <button disabled={!from || !to} onClick={applyCustom}>Aplicar fechas</button>
          <select value={siteId} onChange={e => setSiteId(e.target.value)}>
            <option value="">Todas las sedes</option>
            {(sites.data ?? []).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <button onClick={() => setRange(r => ({ ...r }))}>Actualizar</button>
        </div>
        <div className="map-toolbar">
          <a className="btn" href={`/api/v1/reports/availability.pdf?${qs}`}>Descargar PDF</a>
          <a className="btn" href={`/api/v1/reports/availability.csv?kind=devices&style=${csvStyle}&${qs}`}>CSV dispositivos</a>
          <a className="btn" href={`/api/v1/reports/availability.csv?kind=services&style=${csvStyle}&${qs}`}>CSV servicios</a>
          <a className="btn" href={`/api/v1/reports/availability.csv?kind=alerts&style=${csvStyle}&${qs}`}>CSV alertas</a>
          <select value={csvStyle} onChange={e => setCsvStyle(e.target.value)}>
            <option value="es">CSV para Excel en español (; y coma decimal)</option>
            <option value="en">CSV estándar (, y punto decimal)</option>
          </select>
        </div>
        {error && <p className="error">{error}</p>}
        {loading && <p className="muted">Generando reporte…</p>}
        {report && (
          <>
            <p className="muted">
              Del {fmtDateTime(report.period.start)} al {fmtDateTime(report.period.end)} ({report.period.hours.toFixed(0)} h)
              · {report.period.site ?? 'todas las sedes'}
            </p>
            <div className="kpis">
              <div className="kpi"><span className="muted">Disponibilidad media</span><strong>{fmtPct(report.avg_availability_pct)}</strong></div>
              <div className="kpi"><span className="muted">Caídas</span><strong>{report.total_outages}</strong></div>
              <div className="kpi"><span className="muted">Alertas</span><strong>{report.alerts.total}</strong>
                <span className="muted">{report.alerts.critical} críticas · {report.alerts.warning} avisos</span></div>
              <div className="kpi"><span className="muted">MTTR</span><strong>{fmtSeconds(report.alerts.mttr_s)}</strong></div>
            </div>
          </>
        )}
      </section>

      {report && (
        <>
          <section className="panel">
            <h3 style={{ marginTop: 0 }}>Dispositivos (ICMP) <span className="muted">— ordenados de peor a mejor</span></h3>
            {devices.length === 0 ? <p className="muted">Sin datos en el periodo.</p> : (
              <table className="grid">
                <thead><tr><th>Dispositivo</th><th>Sede</th><th>Disponibilidad</th><th>Cobertura</th><th>Caídas</th><th>Downtime est.</th><th>RTT medio</th><th>Pérdida</th></tr></thead>
                <tbody>
                  {devices.map(d => (
                    <tr key={d.device_id}>
                      <td>{d.name}<br /><span className="muted">{d.ip}</span></td>
                      <td>{d.site}</td>
                      <td><span className={`badge ${availClass(d.availability_pct)}`}>{fmtPct(d.availability_pct)}</span></td>
                      <td>{d.coverage_pct.toFixed(0)} %</td>
                      <td>{d.outages}</td>
                      <td>{fmtSeconds(d.est_downtime_s)}</td>
                      <td>{d.avg_rtt_ms != null ? `${d.avg_rtt_ms.toFixed(1)} ms` : '—'}</td>
                      <td>{d.avg_loss_pct != null ? `${d.avg_loss_pct.toFixed(2)} %` : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <p className="muted">La cobertura compara las muestras reales con las esperadas: un valor bajo significa que el monitoreo estuvo apagado o el equipo se agregó durante el periodo.</p>
          </section>

          <section className="panel">
            <h3 style={{ marginTop: 0 }}>Servicios</h3>
            {services.length === 0 ? <p className="muted">Sin comprobaciones de servicios en el periodo.</p> : (
              <table className="grid">
                <thead><tr><th>Dispositivo</th><th>Servicio</th><th>Disponibilidad</th><th>Muestras</th><th>Fallidas</th><th>Latencia media</th><th>p95</th></tr></thead>
                <tbody>
                  {services.map(s => (
                    <tr key={s.check_id}>
                      <td>{s.device}</td>
                      <td>{s.name} <span className="muted">({s.kind.toUpperCase()})</span></td>
                      <td><span className={`badge ${availClass(s.availability_pct)}`}>{fmtPct(s.availability_pct)}</span></td>
                      <td>{s.samples}</td>
                      <td>{s.failed}</td>
                      <td>{s.avg_latency_ms != null ? `${s.avg_latency_ms.toFixed(0)} ms` : '—'}</td>
                      <td>{s.p95_latency_ms != null ? `${s.p95_latency_ms.toFixed(0)} ms` : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          {report.alerts.top_devices.length > 0 && (
            <section className="panel">
              <h3 style={{ marginTop: 0 }}>Dispositivos con más alertas</h3>
              <table className="grid">
                <thead><tr><th>Dispositivo</th><th>Alertas</th></tr></thead>
                <tbody>
                  {report.alerts.top_devices.map(t => <tr key={t.device}><td>{t.device}</td><td>{t.alerts}</td></tr>)}
                </tbody>
              </table>
            </section>
          )}
        </>
      )}
    </main>
  )
}
