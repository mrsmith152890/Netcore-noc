import { useState } from 'react'
import { usePolling } from '../../hooks/usePolling'
import { apiGet, apiSend } from '../../services/api'
import { fmtDateTime } from '../../services/format'
import type { AlertRule, Channel, DeviceStatus, NotificationLog } from '../../types/api'

const RULE_LABELS: Record<string, string> = {
  device_down: 'Dispositivo caído',
  service_down: 'Servicio caído',
  cpu_high: 'CPU alta (%)',
  mem_high: 'Memoria alta (%)',
  latency_high: 'Latencia alta (ms)',
}
const STATUS_LABELS: Record<string, [string, string]> = {
  sent: ['UP', 'Enviada'],
  failed: ['DOWN', 'Fallida'],
  pending: ['UNKNOWN', 'Pendiente'],
  suppressed: ['UNKNOWN', 'Silenciada'],
}
const errMsg = (e: unknown) => (e instanceof Error ? e.message : String(e))

export default function AlertsConfig({ devices }: { devices: DeviceStatus[] }) {
  const [tick, setTick] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [editingChannelId, setEditingChannelId] = useState<number | null>(null)
  const [credentials, setCredentials] = useState({ bot_token: '', chat_id: '' })
  const channels = usePolling(() => apiGet<Channel[]>('/alerts/channels'), 15000, [tick])
  const rules = usePolling(() => apiGet<AlertRule[]>('/alerts/rules'), 15000, [tick])
  const log = usePolling(() => apiGet<NotificationLog[]>('/alerts/notifications?limit=15'), 5000, [tick])

  const [ch, setCh] = useState({ name: '', bot_token: '', chat_id: '', min_severity: 'warning' })
  const [rule, setRule] = useState({
    name: '', rule_type: 'device_down', threshold: '', for_min: '0',
    severity: 'warning', repeat_min: '60', escalate_min: '', device_id: '', check_type: '',
  })

  async function act(fn: () => Promise<unknown>) {
    try {
      await fn()
      setError(null)
      setSuccess(null)
      setTick(t => t + 1)
    } catch (e) {
      setError(errMsg(e))
    }
  }

  async function testChannel(channel: Channel) {
    setError(null)
    setSuccess(null)
    try {
      await apiSend('POST', '/alerts/channels/' + channel.id + '/test')
      setSuccess('Telegram confirmó el envío al canal «' + channel.name + '».')
      setTick(t => t + 1)
    } catch (e) {
      setError(errMsg(e))
      setTick(t => t + 1)
    }
  }

  async function saveChannelCredentials() {
    if (editingChannelId == null) return
    setError(null)
    setSuccess(null)
    try {
      await apiSend('PATCH', '/alerts/channels/' + editingChannelId, credentials)
      setSuccess('Credenciales verificadas y actualizadas correctamente.')
      setCredentials({ bot_token: '', chat_id: '' })
      setEditingChannelId(null)
      setTick(t => t + 1)
    } catch (e) {
      setError(errMsg(e))
    }
  }

  const needsThreshold = !['device_down', 'service_down'].includes(rule.rule_type)
  const deviceName = (id: number | null) => (id ? devices.find(d => d.device_id === id)?.name ?? `#${id}` : 'Todos')

  return (
    <section className="panel">
      <h3 style={{ marginTop: 0 }}>Canales de notificación (Telegram)</h3>
      <div className="form-row">
        <input placeholder="Nombre" value={ch.name} onChange={e => setCh({ ...ch, name: e.target.value })} />
        <input type="password" placeholder="Token del bot (de @BotFather)" value={ch.bot_token} onChange={e => setCh({ ...ch, bot_token: e.target.value })} />
        <input placeholder="chat_id" value={ch.chat_id} onChange={e => setCh({ ...ch, chat_id: e.target.value })} />
        <select value={ch.min_severity} onChange={e => setCh({ ...ch, min_severity: e.target.value })}>
          <option value="warning">Avisos y críticas</option>
          <option value="critical">Solo críticas</option>
        </select>
        <button
          disabled={!ch.name.trim() || !ch.bot_token || !ch.chat_id}
          onClick={() => void act(async () => {
            await apiSend('POST', '/alerts/channels', { ...ch, name: ch.name.trim(), type: 'telegram' })
            setCh({ ...ch, name: '', bot_token: '', chat_id: '' })
          })}
        >
          Agregar canal
        </button>
      </div>
      {error && <p className="error telegram-feedback" role="alert">{error}</p>}
      {success && <p className="success telegram-feedback" role="status">{success}</p>}
      {editingChannelId != null && (
        <div className="telegram-edit">
          <div><strong>Actualizar acceso de Telegram</strong><p className="muted">Pega el token nuevo de @BotFather y el chat_id destino. Se validarán antes de guardar.</p></div>
          <input type="password" autoComplete="new-password" placeholder="Token nuevo del bot" value={credentials.bot_token}
            onChange={e => setCredentials({ ...credentials, bot_token: e.target.value })} />
          <input placeholder="chat_id destino" value={credentials.chat_id}
            onChange={e => setCredentials({ ...credentials, chat_id: e.target.value })} />
          <button className="btn" disabled={!credentials.bot_token.trim() || !credentials.chat_id.trim()}
            onClick={() => void saveChannelCredentials()}>Validar y guardar</button>
          <button className="btn secondary" onClick={() => { setEditingChannelId(null); setCredentials({ bot_token: '', chat_id: '' }) }}>Cancelar</button>
        </div>
      )}
      {(channels.data ?? []).length > 0 && (
        <table className="grid">
          <thead><tr><th>Canal</th><th>Tipo</th><th>Recibe</th><th>Estado</th><th></th></tr></thead>
          <tbody>
            {(channels.data ?? []).map(c => (
              <tr key={c.id}>
                <td>{c.name}</td>
                <td>{c.type}</td>
                <td>{c.min_severity === 'critical' ? 'Solo críticas' : 'Avisos y críticas'}</td>
                <td><span className={`badge ${c.enabled ? 'UP' : 'UNKNOWN'}`}>{c.enabled ? 'Activo' : 'Desactivado'}</span></td>
                <td>
                  <button className="btn" disabled={!c.enabled} onClick={() => void testChannel(c)}>Probar envío</button>{' '}
                  <button className="btn secondary" onClick={() => { setEditingChannelId(c.id); setCredentials({ bot_token: '', chat_id: '' }); setError(null); setSuccess(null) }}>Actualizar acceso</button>{' '}
                  <button className="btn" onClick={() => void act(() => apiSend('PATCH', `/alerts/channels/${c.id}`, { enabled: !c.enabled }))}>
                    {c.enabled ? 'Desactivar' : 'Activar'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h3>Reglas</h3>
      <div className="form-row">
        <input placeholder="Nombre de la regla" value={rule.name} onChange={e => setRule({ ...rule, name: e.target.value })} />
        <select value={rule.rule_type} onChange={e => setRule({ ...rule, rule_type: e.target.value })}>
          {Object.entries(RULE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <input style={{ width: 90 }} type="number" placeholder="Umbral" disabled={!needsThreshold} value={rule.threshold} onChange={e => setRule({ ...rule, threshold: e.target.value })} />
        <label className="muted">Duración (min) <input style={{ width: 60 }} type="number" min="0" value={rule.for_min} onChange={e => setRule({ ...rule, for_min: e.target.value })} /></label>
        <select value={rule.severity} onChange={e => setRule({ ...rule, severity: e.target.value })}>
          <option value="warning">Aviso</option>
          <option value="critical">Crítica</option>
        </select>
        <label className="muted">Recordar cada (min, 0 = no) <input style={{ width: 60 }} type="number" min="0" value={rule.repeat_min} onChange={e => setRule({ ...rule, repeat_min: e.target.value })} /></label>
        <label className="muted">Escalar a crítica en (min) <input style={{ width: 60 }} type="number" min="1" value={rule.escalate_min} onChange={e => setRule({ ...rule, escalate_min: e.target.value })} /></label>
        {rule.rule_type === 'service_down' && (
          <select value={rule.check_type} onChange={e => setRule({ ...rule, check_type: e.target.value })}>
            <option value="">Todos los servicios</option>
            <option value="tcp">Solo TCP</option>
            <option value="http">Solo HTTP</option>
            <option value="dns">Solo DNS</option>
          </select>
        )}
        <select value={rule.device_id} onChange={e => setRule({ ...rule, device_id: e.target.value })}>
          <option value="">Todos los dispositivos</option>
          {devices.map(d => <option key={d.device_id} value={d.device_id}>{d.name}</option>)}
        </select>
        <button
          disabled={!rule.name.trim() || (needsThreshold && !rule.threshold)}
          onClick={() => void act(async () => {
            await apiSend('POST', '/alerts/rules', {
              name: rule.name.trim(),
              rule_type: rule.rule_type,
              threshold: needsThreshold ? Number(rule.threshold) : null,
              for_seconds: Math.round(Number(rule.for_min) * 60),
              recover_after_s: needsThreshold ? 120 : 30,
              severity: rule.severity,
              repeat_interval_s: Math.round(Number(rule.repeat_min) * 60),
              escalate_after_s: rule.escalate_min ? Math.round(Number(rule.escalate_min) * 60) : null,
              device_id: rule.device_id ? Number(rule.device_id) : null,
              check_type: rule.rule_type === 'service_down' && rule.check_type ? rule.check_type : null,
            })
            setRule({ ...rule, name: '', threshold: '' })
          })}
        >
          Crear regla
        </button>
      </div>
      {(rules.data ?? []).length > 0 && (
        <table className="grid">
          <thead><tr><th>Regla</th><th>Condición</th><th>Duración</th><th>Severidad</th><th>Alcance</th><th>Estado</th><th></th></tr></thead>
          <tbody>
            {(rules.data ?? []).map(r => (
              <tr key={r.id}>
                <td>{r.name}</td>
                <td>{RULE_LABELS[r.rule_type] ?? r.rule_type}{r.threshold != null ? ` > ${r.threshold}` : ''}</td>
                <td>{r.for_seconds / 60} min</td>
                <td><span className={`badge ${r.severity}`}>{r.severity === 'critical' ? 'Crítica' : 'Aviso'}</span></td>
                <td>{deviceName(r.device_id)}</td>
                <td><span className={`badge ${r.enabled ? 'UP' : 'UNKNOWN'}`}>{r.enabled ? 'Activa' : 'Desactivada'}</span></td>
                <td><button className="btn" onClick={() => void act(() => apiSend('PATCH', `/alerts/rules/${r.id}`, { enabled: !r.enabled }))}>{r.enabled ? 'Desactivar' : 'Activar'}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h3>Últimos envíos</h3>
      {(log.data ?? []).length === 0 ? (
        <p className="muted">Todavía no hay notificaciones.</p>
      ) : (
        <table className="grid">
          <thead><tr><th>Hora</th><th>Tipo</th><th>Estado</th><th>Intentos</th><th>Mensaje</th></tr></thead>
          <tbody>
            {(log.data ?? []).map(n => {
              const [cls, label] = STATUS_LABELS[n.status] ?? ['UNKNOWN', n.status]
              return (
                <tr key={n.id}>
                  <td>{fmtDateTime(n.created_at)}</td>
                  <td>{n.kind}</td>
                  <td><span className={`badge ${cls}`}>{label}</span>{n.last_error && <><br /><span className="error">{n.last_error}</span></>}</td>
                  <td>{n.attempts}</td>
                  <td className="muted">{n.text.split('\n')[0]}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </section>
  )
}
