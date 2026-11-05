import { useState } from 'react'
import TimeSeriesChart from '../../components/TimeSeriesChart'
import { usePolling } from '../../hooks/usePolling'
import { apiGet } from '../../services/api'
import { fmtBps, fmtBytes, fmtTime, fmtUptime } from '../../services/format'
import type { DeviceStatus, InterfaceInfo, InterfaceSample, MetricSample, PingSample, SnmpIdentity, StatusEvent } from '../../types/api'

const RANGES = [
  { label: '15 min', minutes: 15 },
  { label: '1 h', minutes: 60 },
  { label: '6 h', minutes: 360 },
  { label: '24 h', minutes: 1440 },
]

function InterfaceTraffic({ ifaceId, minutes }: { ifaceId: number; minutes: number }) {
  const { data } = usePolling(
    () => apiGet<InterfaceSample[]>(`/interfaces/${ifaceId}/samples?minutes=${minutes}`),
    15000,
    [ifaceId, minutes],
  )
  const rows = (data ?? []).map(s => ({ t: fmtTime(s.sampled_at), in: s.in_bps, out: s.out_bps }))
  return (
    <TimeSeriesChart
      data={rows}
      yFormatter={fmtBps}
      series={[
        { key: 'in', label: 'Entrada', color: '#4ade80' },
        { key: 'out', label: 'Salida', color: '#60a5fa' },
      ]}
    />
  )
}

export default function DeviceDetail({ device }: { device: DeviceStatus }) {
  const id = device.device_id
  const [minutes, setMinutes] = useState(60)
  const [ifaceId, setIfaceId] = useState<number | null>(null)

  const identity = usePolling(() => apiGet<SnmpIdentity>(`/devices/${id}/snmp/identity`), 30000, [id])
  const metrics = usePolling(
    () => apiGet<MetricSample[]>(`/devices/${id}/metrics?minutes=${minutes}`),
    15000,
    [id, minutes],
  )
  const pingHistory = usePolling(() => apiGet<PingSample[]>('/devices/' + id + '/ping-history?minutes=' + minutes), 15000, [id, minutes])
  const events = usePolling(() => apiGet<StatusEvent[]>('/devices/' + id + '/events?limit=12'), 30000, [id])
  const interfaces = usePolling(() => apiGet<InterfaceInfo[]>(`/devices/${id}/interfaces`), 15000, [id])

  const rows = (metrics.data ?? []).map(m => ({ t: fmtTime(m.sampled_at), cpu: m.cpu_pct, mem: m.mem_pct }))
  const last = metrics.data?.at(-1)
  const ident = identity.data
  const pingSamples = pingHistory.data ?? []
  const successfulPings = pingSamples.filter(sample => sample.success && sample.rtt_ms != null)
  const avgPing = successfulPings.length ? successfulPings.reduce((sum, sample) => sum + (sample.rtt_ms ?? 0), 0) / successfulPings.length : null
  const avgLoss = pingSamples.length ? pingSamples.reduce((sum, sample) => sum + sample.packet_loss, 0) / pingSamples.length : null
  const pingRows = pingSamples.map(sample => ({ t: fmtTime(sample.checked_at), rtt: sample.success ? sample.rtt_ms : null }))

  return (
    <section className="panel detail">
      <div className="detail-head device-title">
        <div>
          <h2>{device.name}</h2>
          <p className="muted device-subtitle">
            {device.ip_address} · {ident?.sys_name ?? 'Dispositivo de red'}
          </p>
        </div>
        <span className={`badge ${device.state}`}>{device.state}</span>
        <div className="ranges">
          {RANGES.map(r => (
            <button key={r.minutes} className={r.minutes === minutes ? 'active' : ''} onClick={() => setMinutes(r.minutes)}>
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {ident ? (
        <p className="muted">
          {ident.sys_name ?? '—'} · uptime {fmtUptime(ident.uptime_s)}
          {ident.last_error && <span className="error"> · último error SNMP: {ident.last_error}</span>}
          <br />
          {ident.sys_descr}
        </p>
      ) : (
        <p className="muted">Sin datos SNMP todavía (configura la comunidad y espera un ciclo del poller).</p>
      )}

      {['router', 'firewall'].includes(device.device_type) && (device.wan_gateway_ip || device.wan_probe_ip) && (
        <section className="wan-status">
          <div className="wan-status-heading">
            <div><p className="eyebrow">DIAGNÓSTICO DE ENLACE</p><h3>Conectividad WAN</h3></div>
            <span className="muted">{device.wan_checked_at ? 'Comprobado ' + fmtTime(device.wan_checked_at) : 'Esperando primera comprobación'}</span>
          </div>
          <div className="wan-checks">
            {device.wan_gateway_ip && <div className="wan-check">
              <span>Gateway WAN</span><strong>{device.wan_gateway_ip}</strong>
              <b className={'badge ' + (device.wan_gateway_state ?? 'UNKNOWN')}>{device.wan_gateway_state ?? 'Pendiente'}</b>
              <small>{device.wan_gateway_rtt_ms == null ? 'Sin latencia' : device.wan_gateway_rtt_ms.toFixed(1) + ' ms'}</small>
            </div>}
            {device.wan_probe_ip && <div className="wan-check">
              <span>Destino externo</span><strong>{device.wan_probe_ip}</strong>
              <b className={'badge ' + (device.wan_probe_state ?? 'UNKNOWN')}>{device.wan_probe_state ?? 'Pendiente'}</b>
              <small>{device.wan_probe_rtt_ms == null ? 'Sin latencia' : device.wan_probe_rtt_ms.toFixed(1) + ' ms'}</small>
            </div>}
          </div>
          <p className="muted wan-note">Las pruebas salen desde el servidor NOC. Si el router usa DHCP, configura solo un gateway conocido o deja las comprobaciones WAN vacías. Algunos gateways bloquean ICMP.</p>
        </section>
      )}

      <div className="device-kpis">
        <article className="device-kpi">
          <span className="device-kpi-label">Estado del equipo</span>
          <strong className={`device-kpi-value state-${device.state.toLowerCase()}`}>
            {device.state}
          </strong>
          <span className="muted">Disponibilidad de red</span>
        </article>
        <article className="device-kpi">
          <span className="device-kpi-label">Latencia</span>
          <strong className="device-kpi-value">
            {device.last_rtt_ms == null ? '—' : `${device.last_rtt_ms.toFixed(1)} ms`}
          </strong>
          <span className="muted">Última comprobación</span>
        </article>
        <article className="device-kpi">
          <span className="device-kpi-label">CPU</span>
          <strong className="device-kpi-value">
            {last?.cpu_pct == null ? '—' : `${last.cpu_pct.toFixed(1)} %`}
          </strong>
          <span className="muted">Uso del procesador</span>
        </article>
        <article className="device-kpi">
          <span className="device-kpi-label">Memoria utilizada</span>
          <strong className="device-kpi-value">
            {last?.mem_used == null ? '—' : fmtBytes(last.mem_used)}
          </strong>
          <span className="muted">
            {last?.mem_total == null ? 'Capacidad desconocida' : `de ${fmtBytes(last.mem_total)}`}
          </span>
        </article>
      </div>

      <div className="history-summary">
        <div><span>Latencia media del periodo</span><strong>{avgPing == null ? '—' : avgPing.toFixed(1) + ' ms'}</strong></div>
        <div><span>Pérdida media</span><strong className={avgLoss != null && avgLoss > 0 ? 'history-loss' : ''}>{avgLoss == null ? '—' : avgLoss.toFixed(2) + ' %'}</strong></div>
        <div><span>Comprobaciones</span><strong>{pingSamples.length}</strong></div>
        <div><span>Correctas</span><strong>{pingSamples.length ? Math.round(successfulPings.length / pingSamples.length * 100) + '%' : '—'}</strong></div>
      </div>
      <h3>Historial de ping</h3>
      <TimeSeriesChart data={pingRows} yFormatter={v => v.toFixed(1) + ' ms'}
        series={[{ key: 'rtt', label: 'Latencia ICMP', color: '#60a5fa' }]} />
      <h3>Cambios recientes de estado</h3>
      {(events.data ?? []).length ? (
        <div className="status-event-list">
          {(events.data ?? []).map((event, index) => (
            <div className="status-event" key={event.at + index}>
              <span className={'event-state-dot ' + event.to_state.toLowerCase()} />
              <span><strong>{event.from_state} → {event.to_state}</strong><small>{fmtTime(event.at)}</small></span>
            </div>
          ))}
        </div>
      ) : <p className="muted">Todavía no hay transiciones de estado registradas.</p>}

      <h3>
        CPU y memoria
        {last && (
          <span className="muted">
            {' '}— CPU {last.cpu_pct ?? '—'} % · RAM {fmtBytes(last.mem_used)} / {fmtBytes(last.mem_total)}
          </span>
        )}
      </h3>
      <TimeSeriesChart
        data={rows}
        yFormatter={v => `${v.toFixed(0)} %`}
        series={[
          { key: 'cpu', label: 'CPU %', color: '#f59e0b' },
          { key: 'mem', label: 'Memoria %', color: '#a78bfa' },
        ]}
      />

      <h3>Interfaces</h3>
      {interfaces.data && interfaces.data.length > 0 ? (
        <table className="grid">
          <thead>
            <tr><th>Interfaz</th><th>Estado</th><th>Velocidad</th><th>Entrada</th><th>Salida</th></tr>
          </thead>
          <tbody>
            {interfaces.data.map(i => (
              <tr
                key={i.id}
                className={i.id === ifaceId ? 'selected' : ''}
                onClick={() => setIfaceId(i.id)}
              >
                <td>{i.name ?? i.descr ?? `if${i.if_index}`}</td>
                <td>{i.oper_status ?? '—'}</td>
                <td>{fmtBps(i.speed_bps)}</td>
                <td>{fmtBps(i.in_bps)}</td>
                <td>{fmtBps(i.out_bps)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted">Sin interfaces descubiertas todavía.</p>
      )}

      {ifaceId != null && (
        <>
          <h3>Tráfico de la interfaz seleccionada</h3>
          <InterfaceTraffic key={ifaceId} ifaceId={ifaceId} minutes={minutes} />
        </>
      )}
    </section>
  )
}
