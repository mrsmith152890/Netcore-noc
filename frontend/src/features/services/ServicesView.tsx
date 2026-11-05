import { useState } from 'react'
import TimeSeriesChart from '../../components/TimeSeriesChart'
import { usePolling } from '../../hooks/usePolling'
import { apiGet, apiSend } from '../../services/api'
import { fmtAgo, fmtTime } from '../../services/format'
import type { DeviceStatus, ServiceCheck, ServiceResult } from '../../types/api'

const errMsg = (e: unknown) => (e instanceof Error ? e.message : String(e))

const EMPTY = {
  device_id: '', name: '', kind: 'http', host: '', port: '', url: 'http://{ip}/',
  expect_status: '200-399', expect_text: '', verify_tls: true,
  dns_query: '', dns_type: 'A', dns_expect: '', interval_s: '60', timeout_s: '5',
}

const targetOf = (c: ServiceCheck) =>
  c.kind === 'tcp'
    ? `${c.host || 'IP del equipo'}:${c.port}`
    : c.kind === 'http'
      ? (c.url ?? '')
      : `${c.dns_query} (${c.dns_type}) @ ${c.host || 'IP del equipo'}`

function Latency({ checkId }: { checkId: number }) {
  const { data } = usePolling(
    () => apiGet<ServiceResult[]>(`/services/${checkId}/results?minutes=60`),
    15000,
    [checkId],
  )
  const rows = (data ?? []).map(r => ({ t: fmtTime(r.checked_at), ms: r.success ? r.latency_ms : null }))
  return (
    <TimeSeriesChart
      data={rows}
      yFormatter={v => `${v.toFixed(0)} ms`}
      series={[{ key: 'ms', label: 'Latencia', color: '#38bdf8' }]}
      height={180}
    />
  )
}

interface Props {
  devices: DeviceStatus[]
  isAdmin: boolean
  canOperate: boolean
}

export default function ServicesView({ devices, isAdmin, canOperate }: Props) {
  const [tick, setTick] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<number | null>(null)
  const [form, setForm] = useState(EMPTY)
  const checks = usePolling(() => apiGet<ServiceCheck[]>('/services'), 5000, [tick])

  async function act(fn: () => Promise<unknown>) {
    try {
      await fn()
      setError(null)
      setTick(t => t + 1)
    } catch (e) {
      setError(errMsg(e))
    }
  }

  const create = () =>
    act(async () => {
      const k = form.kind
      await apiSend('POST', '/services', {
        device_id: Number(form.device_id),
        name: form.name.trim(),
        kind: k,
        host: k === 'http' ? null : form.host.trim() || null,
        port: k === 'http' ? null : form.port ? Number(form.port) : null,
        url: k === 'http' ? form.url.trim() : null,
        expect_status: k === 'http' ? form.expect_status.trim() || null : null,
        expect_text: k === 'http' ? form.expect_text.trim() || null : null,
        verify_tls: form.verify_tls,
        dns_query: k === 'dns' ? form.dns_query.trim() : null,
        dns_type: form.dns_type,
        dns_expect: k === 'dns' ? form.dns_expect.trim() || null : null,
        interval_s: Number(form.interval_s),
        timeout_s: Number(form.timeout_s),
      })
      setForm({ ...EMPTY, device_id: form.device_id })
    })

  const list = checks.data ?? []
  const selectedCheck = list.find(c => c.id === selected) ?? null
  const canCreate = form.device_id && form.name.trim() &&
    (form.kind === 'tcp' ? form.port : form.kind === 'http' ? form.url.trim() : form.dns_query.trim())

  return (
    <main>
      <section className="panel">
        <h3 style={{ marginTop: 0 }}>Comprobaciones de servicios</h3>
        {isAdmin && (
          <div className="form-row">
            <select value={form.device_id} onChange={e => setForm({ ...form, device_id: e.target.value })}>
              <option value="">Dispositivo…</option>
              {devices.map(d => <option key={d.device_id} value={d.device_id}>{d.name}</option>)}
            </select>
            <input placeholder="Nombre (ej.: Web, SSH, DNS)" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
            <select value={form.kind} onChange={e => setForm({ ...form, kind: e.target.value })}>
              <option value="http">HTTP(S)</option>
              <option value="tcp">TCP</option>
              <option value="dns">DNS</option>
            </select>
            {form.kind === 'tcp' && (
              <>
                <input style={{ width: 90 }} type="number" placeholder="Puerto" value={form.port} onChange={e => setForm({ ...form, port: e.target.value })} />
                <input placeholder="Destino (opcional)" value={form.host} onChange={e => setForm({ ...form, host: e.target.value })} />
              </>
            )}
            {form.kind === 'http' && (
              <>
                <input style={{ width: 280 }} placeholder="URL (admite {ip})" value={form.url} onChange={e => setForm({ ...form, url: e.target.value })} />
                <input style={{ width: 110 }} placeholder="Códigos OK" value={form.expect_status} onChange={e => setForm({ ...form, expect_status: e.target.value })} />
                <input placeholder="Texto esperado (opcional)" value={form.expect_text} onChange={e => setForm({ ...form, expect_text: e.target.value })} />
                <label className="muted"><input type="checkbox" checked={form.verify_tls} onChange={e => setForm({ ...form, verify_tls: e.target.checked })} /> Verificar TLS</label>
              </>
            )}
            {form.kind === 'dns' && (
              <>
                <input placeholder="Nombre a consultar" value={form.dns_query} onChange={e => setForm({ ...form, dns_query: e.target.value })} />
                <select value={form.dns_type} onChange={e => setForm({ ...form, dns_type: e.target.value })}>
                  {['A', 'AAAA', 'MX', 'TXT', 'CNAME', 'NS'].map(t => <option key={t}>{t}</option>)}
                </select>
                <input placeholder="Servidor DNS (IP, opcional)" value={form.host} onChange={e => setForm({ ...form, host: e.target.value })} />
                <input placeholder="Respuesta esperada (opcional)" value={form.dns_expect} onChange={e => setForm({ ...form, dns_expect: e.target.value })} />
              </>
            )}
            <label className="muted">Cada (s) <input style={{ width: 60 }} type="number" min="10" value={form.interval_s} onChange={e => setForm({ ...form, interval_s: e.target.value })} /></label>
            <label className="muted">Timeout (s) <input style={{ width: 50 }} type="number" min="1" value={form.timeout_s} onChange={e => setForm({ ...form, timeout_s: e.target.value })} /></label>
            <button disabled={!canCreate} onClick={() => void create()}>Agregar</button>
          </div>
        )}
        {error && <p className="error">{error}</p>}
        {list.length === 0 ? (
          <p className="muted">Todavía no hay comprobaciones de servicios.</p>
        ) : (
          <table className="grid">
            <thead>
              <tr><th>Estado</th><th>Dispositivo</th><th>Servicio</th><th>Destino</th><th>Latencia</th><th>Última</th><th>Error</th><th></th></tr>
            </thead>
            <tbody>
              {list.map(c => (
                <tr key={c.id} className={c.id === selected ? 'selected' : ''} onClick={() => setSelected(c.id)}>
                  <td><span className={`badge ${c.enabled ? c.state : 'UNKNOWN'}`}>{c.enabled ? c.state : 'OFF'}</span></td>
                  <td>{c.device_name}</td>
                  <td>{c.name} <span className="muted">({c.kind.toUpperCase()})</span></td>
                  <td className="muted">{targetOf(c)}</td>
                  <td>{c.last_latency_ms != null && c.state === 'UP' ? `${c.last_latency_ms.toFixed(0)} ms` : '—'}</td>
                  <td>{fmtAgo(c.last_check_at)}</td>
                  <td className="error">{c.state === 'DOWN' || c.consecutive_failures > 0 ? c.last_error : ''}</td>
                  <td onClick={e => e.stopPropagation()}>
                    {canOperate && <button className="btn" onClick={() => void act(() => apiSend('POST', `/services/${c.id}/recheck`))}>Reverificar</button>}{' '}
                    {isAdmin && (
                      <>
                        <button className="btn" onClick={() => void act(() => apiSend('PATCH', `/services/${c.id}`, { enabled: !c.enabled }))}>
                          {c.enabled ? 'Desactivar' : 'Activar'}
                        </button>{' '}
                        <button className="btn" onClick={() => {
                          if (window.confirm(`¿Eliminar la comprobación «${c.name}» y su histórico?`))
                            void act(() => apiSend('DELETE', `/services/${c.id}`))
                        }}>Eliminar</button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      {selectedCheck && (
        <section className="panel">
          <h3 style={{ marginTop: 0 }}>Latencia — {selectedCheck.device_name} · {selectedCheck.name} (última hora)</h3>
          <Latency key={selectedCheck.id} checkId={selectedCheck.id} />
        </section>
      )}
    </main>
  )
}
