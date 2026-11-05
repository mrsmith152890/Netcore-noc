import { usePolling } from '../../hooks/usePolling'
import { apiGet } from '../../services/api'
import { fmtAgo, fmtSeconds } from '../../services/format'
import type { SystemStatus } from '../../types/api'

export default function SystemView() {
  const { data, error } = usePolling(() => apiGet<SystemStatus>('/system/status'), 10000)
  if (error) return <main><p className="error">{error}</p></main>
  if (!data) return <main><p className="muted">Cargando…</p></main>

  return (
    <main>
      <section className="panel">
        <h3 style={{ marginTop: 0 }}>
          Estado del sistema{' '}
          {data.overall_ok
            ? <span className="badge UP">Todo en orden</span>
            : <span className="badge DOWN">{data.problems} fallos</span>}
        </h3>
        {!data.watchdog_ok && (
          <p className="error">
            El vigilante no está respondiendo
            {data.watchdog_age_s != null ? ` (última comprobación hace ${fmtSeconds(data.watchdog_age_s)})` : ''}.
            Revisa <code>systemctl status netcore-watchdog</code>.
          </p>
        )}
        <table className="grid">
          <thead><tr><th>Componente</th><th>Estado</th><th>Detalle</th><th>Desde</th></tr></thead>
          <tbody>
            {data.checks.map(c => (
              <tr key={c.key}>
                <td>{c.title}</td>
                <td><span className={`badge ${c.ok ? 'UP' : 'DOWN'}`}>{c.ok ? 'OK' : 'FALLA'}</span></td>
                <td className="muted">{c.detail}</td>
                <td>{fmtAgo(c.since)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="panel">
        <h3 style={{ marginTop: 0 }}>Copias y recuperación</h3>
        <p className="muted">El sistema programa copias diarias y una restauración de verificación. El resultado de restauración se actualiza también cuando falla.</p>
        <table className="grid"><thead><tr><th>Proceso</th><th>Estado</th><th>Último resultado</th><th>Última ejecución</th></tr></thead><tbody>
          {data.heartbeats.filter(h => h.worker === 'backup' || h.worker === 'restore_test').map(h => <tr key={h.worker}><td>{h.title}</td><td><span className={`badge ${h.ok ? 'UP' : 'DOWN'}`}>{h.ok ? 'OK' : 'REVISAR'}</span></td><td className="muted">{h.detail ?? 'Sin resultado registrado'}</td><td>{h.age_s != null ? `hace ${fmtSeconds(h.age_s)}` : 'Sin ejecución'}</td></tr>)}
        </tbody></table>
      </section>
      <section className="panel">
        <h3 style={{ marginTop: 0 }}>Latidos de los procesos</h3>
        <table className="grid">
          <thead><tr><th>Proceso</th><th>Último latido</th><th>Máximo permitido</th><th>Duración del ciclo</th><th>Detalle</th></tr></thead>
          <tbody>
            {data.heartbeats.map(h => (
              <tr key={h.worker}>
                <td>{h.title}</td>
                <td><span className={`badge ${h.ok ? 'UP' : 'DOWN'}`}>{h.age_s != null ? `hace ${fmtSeconds(h.age_s)}` : 'nunca'}</span></td>
                <td>{fmtSeconds(h.expected_s)}</td>
                <td>{h.cycle_ms != null ? `${(h.cycle_ms / 1000).toFixed(1)} s` : '—'}</td>
                <td className="muted">{h.detail ?? ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted">La duración del ciclo debe ser claramente menor que el intervalo configurado de cada proceso; si se acerca, hay que ajustar la concurrencia.</p>
      </section>
    </main>
  )
}
