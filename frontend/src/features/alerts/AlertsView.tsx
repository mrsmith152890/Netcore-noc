import { useState } from 'react'
import { usePolling } from '../../hooks/usePolling'
import { apiGet, apiSend } from '../../services/api'
import { fmtDateTime } from '../../services/format'
import type { AlertOut, DeviceStatus, Silence } from '../../types/api'

const errMsg = (e: unknown) => (e instanceof Error ? e.message : String(e))

export default function AlertsView({ devices }: { devices: DeviceStatus[] }) {
  const [filter, setFilter] = useState<'active' | 'resolved'>('active')
  const [grouped, setGrouped] = useState(true)
  const [tick, setTick] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const alerts = usePolling(() => apiGet<AlertOut[]>(`/alerts?state=${filter}&limit=100`), 5000, [filter, tick])
  const silences = usePolling(() => apiGet<Silence[]>('/alerts/silences'), 10000, [tick])

  async function act(fn: () => Promise<unknown>) {
    try {
      await fn()
      setError(null)
      setTick(t => t + 1)
    } catch (e) {
      setError(errMsg(e))
    }
  }

  const ack = (a: AlertOut) => {
    const note = window.prompt('Nota para el reconocimiento (opcional)')
    if (note === null) return
    void act(() => apiSend('POST', `/alerts/${a.id}/ack`, { note: note.trim() || null }))
  }

  const silence = (a: AlertOut) => {
    const m = window.prompt('¿Cuántos minutos silenciar este dispositivo?', '60')
    const minutes = Number(m)
    if (!m || !Number.isFinite(minutes) || minutes < 1) return
    void act(() =>
      apiSend('POST', '/alerts/silences', {
        device_id: a.device_id,
        minutes: Math.round(minutes),
        reason: `Silenciado desde la interfaz (${a.rule_name})`,
      }),
    )
  }

  const deviceName = (id: number | null) => devices.find(d => d.device_id === id)?.name ?? `#${id}`
  const list = alerts.data ?? []
  const groups = new Map<string, AlertOut[]>()
  for (const alert of list) {
    const site = alert.site_name || 'Sin sede asignada'
    groups.set(site, [...(groups.get(site) ?? []), alert])
  }
  const renderTable = (rows: AlertOut[]) => (
    <table className="grid">
      <thead><tr><th>Severidad</th><th>Estado</th><th>Dispositivo</th><th>Regla</th><th>Detalle</th><th>Desde</th><th></th></tr></thead>
      <tbody>{rows.map(a => (
        <tr key={a.id}>
          <td><span className={`badge ${a.severity}`}>{a.severity === 'critical' ? 'Crítica' : 'Aviso'}{a.escalated ? ' ↑' : ''}</span></td>
          <td><span className={`badge ${a.state}`}>{a.state === 'firing' ? 'Activa' : a.state === 'acknowledged' ? 'Reconocida' : 'Resuelta'}</span></td>
          <td>{a.device_name}<br /><span className="muted">{a.device_ip} · {a.site_name}</span></td>
          <td>{a.rule_name}</td><td>{a.summary}{a.ack_note && <><br /><span className="muted">Nota: {a.ack_note}</span></>}</td>
          <td>{fmtDateTime(a.fired_at ?? a.created_at)}{a.resolved_at && <><br /><span className="muted">hasta {fmtDateTime(a.resolved_at)}</span></>}</td>
          <td>{a.state === 'firing' && <button className="btn" onClick={() => ack(a)}>Reconocer</button>}{' '}{(a.state === 'firing' || a.state === 'acknowledged') && <button className="btn" onClick={() => silence(a)}>Silenciar</button>}</td>
        </tr>
      ))}</tbody>
    </table>
  )
  return (
    <section className="panel">
      <div className="map-toolbar">
        <h3 style={{ margin: 0 }}>Alertas</h3>
        <button className={filter === 'active' ? 'active' : ''} onClick={() => setFilter('active')}>Activas</button>
        <button className={filter === 'resolved' ? 'active' : ''} onClick={() => setFilter('resolved')}>Historial</button>
        <button className={grouped ? 'active' : ''} onClick={() => setGrouped(value => !value)}>{grouped ? 'Agrupadas por sede' : 'Ver por sede'}</button>
        {error && <span className="error">{error}</span>}
      </div>
      {list.length === 0 ? (
        <p className="muted">{filter === 'active' ? 'Sin alertas activas.' : 'Sin alertas resueltas todavía.'}</p>
      ) : grouped ? (
        <div className="alert-site-groups">
          {[...groups.entries()].map(([site, rows]) => {
            const critical = rows.filter(alert => alert.severity === 'critical').length
            return <details className="alert-site-group" key={site} open>
              <summary><strong>{site}</strong><span>{rows.length} alerta(s)</span>{critical > 0 && <b>{critical} crítica(s)</b>}</summary>
              {renderTable(rows)}
            </details>
          })}
        </div>
      ) : (
        renderTable(list)
      )}
      {(silences.data ?? []).length > 0 && (
        <>
          <h3>Silencios vigentes</h3>
          <table className="grid">
            <thead><tr><th>Alcance</th><th>Motivo</th><th>Hasta</th><th></th></tr></thead>
            <tbody>
              {(silences.data ?? []).map(s => (
                <tr key={s.id}>
                  <td>
                    {s.device_id ? `Dispositivo ${deviceName(s.device_id)}` : s.site_id ? `Sede #${s.site_id}` : `Regla #${s.rule_id}`}
                  </td>
                  <td>{s.reason}</td>
                  <td>{fmtDateTime(s.ends_at)}</td>
                  <td><button className="btn" onClick={() => void act(() => apiSend('POST', `/alerts/silences/${s.id}/expire`))}>Terminar</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  )
}
