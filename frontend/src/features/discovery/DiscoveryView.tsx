import { useCallback, useEffect, useState } from 'react'
import { usePolling } from '../../hooks/usePolling'
import { apiGet, apiSend } from '../../services/api'
import type { DiscoveredHost, DiscoveryRun, DiscoveryScope, ImportResult, SiteInfo } from '../../types/api'

const DEVICE_TYPES = ['router', 'switch', 'firewall', 'server', 'ap', 'other']
const errMsg = (e: unknown) => (e instanceof Error ? e.message : String(e))

type Edit = { selected: boolean; name: string; device_type: string; vendor: string }

function HostsImport({ run, hosts, onDone }: { run: DiscoveryRun; hosts: DiscoveredHost[]; onDone: () => void }) {
  const [edits, setEdits] = useState<Record<number, Edit>>(() =>
    Object.fromEntries(
      hosts.map(h => [
        h.id,
        { selected: false, name: h.sys_name || h.ip, device_type: h.device_type, vendor: h.vendor ?? '' },
      ]),
    ),
  )
  const [enableSnmp, setEnableSnmp] = useState(true)
  const [info, setInfo] = useState<string | null>(null)

  const patch = (id: number, p: Partial<Edit>) => setEdits(e => ({ ...e, [id]: { ...e[id], ...p } }))
  const selectable = hosts.filter(h => h.status === 'new')
  const chosen = selectable.filter(h => edits[h.id]?.selected)
  const allSelected = selectable.length > 0 && chosen.length === selectable.length

  const toggleAll = (v: boolean) =>
    setEdits(e => {
      const next = { ...e }
      for (const h of selectable) next[h.id] = { ...next[h.id], selected: v }
      return next
    })

  async function doImport() {
    const items = chosen.map(h => ({
      host_id: h.id,
      name: edits[h.id].name.trim(),
      device_type: edits[h.id].device_type,
      vendor: edits[h.id].vendor.trim() || null,
    }))
    if (items.length === 0) return
    if (items.some(i => !i.name)) {
      setInfo('Todos los dispositivos seleccionados necesitan un nombre')
      return
    }
    try {
      const r = await apiSend<ImportResult>('POST', `/discovery/runs/${run.id}/import`, {
        items,
        enable_snmp: enableSnmp,
      })
      setInfo(
        `${r.imported.length} importados, ${r.skipped.length} omitidos` +
          (r.skipped.length ? `: ${r.skipped.map(s => s.reason).join('; ')}` : ''),
      )
      onDone()
    } catch (e) {
      setInfo(errMsg(e))
    }
  }

  if (hosts.length === 0) return <p className="muted">No respondió ningún host en este rango.</p>

  return (
    <>
      <table className="grid">
        <thead>
          <tr>
            <th><input type="checkbox" checked={allSelected} onChange={e => toggleAll(e.target.checked)} /></th>
            <th>IP</th><th>Nombre</th><th>Tipo</th><th>Fabricante</th><th>SNMP</th><th>RTT</th><th>Estado</th>
          </tr>
        </thead>
        <tbody>
          {hosts.map(h => {
            const e = edits[h.id]
            const locked = h.status !== 'new'
            return (
              <tr key={h.id} title={h.sys_descr ?? ''}>
                <td>
                  <input type="checkbox" disabled={locked} checked={!locked && !!e?.selected}
                    onChange={ev => patch(h.id, { selected: ev.target.checked })} />
                </td>
                <td>{h.ip}</td>
                <td><input type="text" disabled={locked} value={e?.name ?? ''} onChange={ev => patch(h.id, { name: ev.target.value })} /></td>
                <td>
                  <select disabled={locked} value={e?.device_type ?? 'other'} onChange={ev => patch(h.id, { device_type: ev.target.value })}>
                    {DEVICE_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </td>
                <td><input type="text" disabled={locked} value={e?.vendor ?? ''} onChange={ev => patch(h.id, { vendor: ev.target.value })} /></td>
                <td>{h.snmp_ok ? <span className="badge UP">SNMP</span> : <span className="muted">—</span>}</td>
                <td>{h.rtt_ms != null ? `${h.rtt_ms.toFixed(1)} ms` : '—'}</td>
                <td>
                  {h.status === 'registered' && <span className="badge UNKNOWN">Ya registrado</span>}
                  {h.status === 'imported' && <span className="badge UP">Importado</span>}
                  {h.status === 'new' && <span className="muted">Nuevo</span>}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <div className="form-row" style={{ marginTop: 12 }}>
        <button disabled={chosen.length === 0} onClick={doImport}>Importar {chosen.length} seleccionados</button>
        <label className="muted">
          <input type="checkbox" checked={enableSnmp} onChange={e => setEnableSnmp(e.target.checked)} /> Activar SNMP en los que respondieron
        </label>
        {info && <span className="muted">{info}</span>}
      </div>
    </>
  )
}

function RunPanel({ runId }: { runId: number }) {
  const run = usePolling(() => apiGet<DiscoveryRun>(`/discovery/runs/${runId}`), 2000, [runId])
  const [hosts, setHosts] = useState<DiscoveredHost[] | null>(null)
  const status = run.data?.status

  const loadHosts = useCallback(() => {
    apiGet<DiscoveredHost[]>(`/discovery/runs/${runId}/hosts`).then(setHosts).catch(() => undefined)
  }, [runId])

  useEffect(() => {
    if (status === 'done') loadHosts()
  }, [status, loadHosts])

  const r = run.data
  if (!r) return <p className="muted">Cargando…</p>

  return (
    <div>
      <p>
        <strong>Escaneo #{r.id}</strong> ·{' '}
        {r.status === 'pending' && 'En cola (¿está corriendo el worker de descubrimiento?)'}
        {r.status === 'running' && ('Escaneando… ' + r.hosts_scanned + '/' + (r.hosts_total || '…') + ' direcciones; ' + r.hosts_alive + ' responden')}
        {r.status === 'done' && `${r.hosts_alive} de ${r.hosts_total} direcciones respondieron · ${r.hosts_snmp} con SNMP`}
        {r.status === 'failed' && <span className="error">Falló: {r.error}</span>}
        {r.status === 'cancelled' && 'Cancelado'}{' '}
        {(r.status === 'pending' || r.status === 'running') && (
          <button className="btn" onClick={() => void apiSend('POST', `/discovery/runs/${r.id}/cancel`)}>Cancelar</button>
        )}
      </p>
      {r.status === 'done' && hosts && <HostsImport key={r.id} run={r} hosts={hosts} onDone={loadHosts} />}
    </div>
  )
}

export default function DiscoveryView() {
  const [scopes, setScopes] = useState<DiscoveryScope[]>([])
  const [sites, setSites] = useState<SiteInfo[]>([])
  const [activeRun, setActiveRun] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [deletingScopeId, setDeletingScopeId] = useState<number | null>(null)
  const [form, setForm] = useState({ site_id: '', cidr: '', community: '', description: '', allow_public: false })

  const load = useCallback(async () => {
    try {
      const [sc, st, runs] = await Promise.all([
        apiGet<DiscoveryScope[]>('/discovery/scopes'),
        apiGet<SiteInfo[]>('/sites'),
        apiGet<DiscoveryRun[]>('/discovery/runs?limit=1'),
      ])
      setScopes(sc)
      setSites(st)
      setForm(f => (f.site_id || !st[0] ? f : { ...f, site_id: String(st[0].id) }))
      setActiveRun(cur => cur ?? runs[0]?.id ?? null)
    } catch (e) {
      setError(errMsg(e))
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function createScope() {
    try {
      await apiSend('POST', '/discovery/scopes', {
        site_id: Number(form.site_id),
        cidr: form.cidr.trim(),
        community: form.community || null,
        description: form.description.trim() || null,
        allow_public: form.allow_public,
      })
      setForm(f => ({ ...f, cidr: '', community: '', description: '', allow_public: false }))
      setError(null)
      await load()
    } catch (e) {
      setError(errMsg(e))
    }
  }

  async function deleteScope(scope: DiscoveryScope) {
    const confirmed = window.confirm(
      '¿Eliminar el rango autorizado ' + scope.cidr + ' de ' + siteName(scope.site_id) + '? ' +
      'Dejará de estar disponible para nuevos escaneos. El historial existente se conservará.'
    )
    if (!confirmed) return
    setDeletingScopeId(scope.id)
    setError(null)
    try {
      await apiSend('DELETE', '/discovery/scopes/' + scope.id)
      setScopes(current => current.filter(item => item.id !== scope.id))
    } catch (e) {
      setError(errMsg(e))
    } finally {
      setDeletingScopeId(null)
    }
  }

  async function scan(scopeId: number) {
    try {
      const run = await apiSend<DiscoveryRun>('POST', `/discovery/scopes/${scopeId}/runs`)
      setActiveRun(run.id)
      setError(null)
    } catch (e) {
      setError(errMsg(e))
    }
  }

  const siteName = (id: number) => sites.find(s => s.id === id)?.name ?? `#${id}`

  return (
    <main>
      <section className="panel">
        <h3 style={{ marginTop: 0 }}>Rangos autorizados</h3>
        <p className="muted">Solo se escanean rangos registrados aquí, de hasta 1024 direcciones. Los rangos públicos requieren autorización explícita por rango y deben pertenecer a tu VPN/red.</p>
        <div className="form-row">
          <select value={form.site_id} onChange={e => setForm({ ...form, site_id: e.target.value })}>
            {sites.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <input placeholder="CIDR, p. ej. 192.168.88.0/24" value={form.cidr} onChange={e => setForm({ ...form, cidr: e.target.value })} />
          <input type="password" placeholder="Comunidad SNMP (opcional)" value={form.community} onChange={e => setForm({ ...form, community: e.target.value })} />
          <input placeholder="Descripción" value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} />
          <label className="muted"><input type="checkbox" checked={form.allow_public} onChange={e => setForm({ ...form, allow_public: e.target.checked })} /> Autorizar rango público propio (VPN)</label>
          <button disabled={!form.site_id || !form.cidr.trim()} onClick={createScope}>Registrar rango</button>
        </div>
        {error && <p className="error">{error}</p>}
        {scopes.length > 0 && (
          <table className="grid">
            <thead><tr><th>Sede</th><th>Rango</th><th>Descripción</th><th>SNMP</th><th>Acciones</th></tr></thead>
            <tbody>
              {scopes.map(s => (
                <tr key={s.id}>
                  <td>{siteName(s.site_id)}</td>
                  <td>{s.cidr}</td>
                  <td>{s.description ?? '—'}</td>
                  <td>{s.has_community ? 'Sí' : '—'}</td>
                  <td><div className="scope-actions">
                    <button className="btn" disabled={deletingScopeId === s.id} onClick={() => void scan(s.id)}>Escanear</button>
                    <button className="btn danger" disabled={deletingScopeId === s.id} onClick={() => void deleteScope(s)}>
                      {deletingScopeId === s.id ? 'Eliminando…' : 'Eliminar'}
                    </button>
                  </div></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      {activeRun != null && (
        <section className="panel">
          <RunPanel key={activeRun} runId={activeRun} />
        </section>
      )}
    </main>
  )
}
