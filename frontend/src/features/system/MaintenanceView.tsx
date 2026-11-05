import { useMemo, useState } from 'react'
import { usePolling } from '../../hooks/usePolling'
import { apiGet, apiSend } from '../../services/api'
import { fmtDateTime } from '../../services/format'
import type { DeviceStatus, Silence } from '../../types/api'

const localInput = (date: Date) => { const d = new Date(date.getTime() - date.getTimezoneOffset() * 60000); return d.toISOString().slice(0, 16) }
const nextHour = () => { const d = new Date(); d.setMinutes(d.getMinutes() + 15, 0, 0); return d }
const message = (e: unknown) => e instanceof Error ? e.message : String(e)

export default function MaintenanceView({ devices }: { devices: DeviceStatus[] }) {
  const [tick, setTick] = useState(0)
  const [scope, setScope] = useState('')
  const [starts, setStarts] = useState(() => localInput(nextHour()))
  const [ends, setEnds] = useState(() => { const d = nextHour(); d.setHours(d.getHours() + 1); return localInput(d) })
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<number | null>(null)
  const rows = usePolling(() => apiGet<Silence[]>('/alerts/silences?only_active=false'), 15000, [tick])
  const now = Date.now()
  const windows = useMemo(() => (rows.data ?? []).filter(row => row.reason.startsWith('MANTENIMIENTO:')).sort((a,b)=>a.starts_at.localeCompare(b.starts_at)), [rows.data])
  const targetName = (row: Silence) => row.device_id ? devices.find(d=>d.device_id===row.device_id)?.name ?? `Dispositivo #${row.device_id}` : row.site_id ? devices.find(d=>d.site_id===row.site_id)?.site_name ?? `Sede #${row.site_id}` : `Regla #${row.rule_id}`
  async function create() {
    setError(null)
    if (!scope || !reason.trim()) { setError('Selecciona una sede o dispositivo y describe el mantenimiento.'); return }
    const from = new Date(starts), until = new Date(ends)
    if (!Number.isFinite(+from) || !Number.isFinite(+until) || until <= from) { setError('La fecha de fin debe ser posterior al inicio.'); return }
    const target = scope.startsWith('device:') ? {device_id:Number(scope.slice(7))} : {site_id:Number(scope.slice(5))}
    try {
      await apiSend('POST','/alerts/silences',{...target,starts_at:from.toISOString(),ends_at:until.toISOString(),reason:'MANTENIMIENTO: '+reason.trim()})
      setReason(''); setTick(t=>t+1)
    } catch(e) { setError(message(e)) }
  }
  async function cancel(row: Silence) {
    setBusy(row.id); setError(null)
    try { await apiSend('POST',`/alerts/silences/${row.id}/expire`); setTick(t=>t+1) }
    catch(e) { setError(message(e)) } finally { setBusy(null) }
  }
  return <main className="maintenance-page">
    <section className="panel"><div className="sites-section-heading"><span>◷</span><div><span className="panel-index">OPERACIÓN · PROGRAMACIÓN</span><h2>Ventanas de mantenimiento</h2><p>Programa cuándo silenciar avisos de una sede completa o un equipo puntual.</p></div></div>
      <p className="muted">Durante la ventana, las alertas y el estado siguen visibles en NetCore NOC; se silencian las notificaciones asociadas. Las fechas se interpretan en tu zona horaria local.</p>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="form-row">
        <label>Alcance<select value={scope} onChange={e=>setScope(e.target.value)}><option value="">Selecciona sede o equipo…</option>
          {[...new Map(devices.map(d=>[d.site_id,{id:d.site_id,name:d.site_name}])).values()].map(site=><option value={`site:${site.id}`} key={`s${site.id}`}>Sede completa · {site.name}</option>)}
          {devices.map(d=><option value={`device:${d.device_id}`} key={`d${d.device_id}`}>Equipo · {d.name} ({d.ip_address})</option>)}
        </select></label>
        <label>Inicio<input type="datetime-local" value={starts} onChange={e=>setStarts(e.target.value)} /></label>
        <label>Fin<input type="datetime-local" value={ends} onChange={e=>setEnds(e.target.value)} /></label>
        <label>Motivo<input maxLength={220} placeholder="Ej.: mantenimiento del enlace WAN" value={reason} onChange={e=>setReason(e.target.value)} /></label>
        <button type="button" disabled={!scope || !reason.trim()} onClick={()=>void create()}>Programar ventana</button>
      </div>
    </section>
    <section className="panel"><h3>Ventanas programadas</h3>
      {rows.error && <p className="error">{rows.error}</p>}
      {!windows.length ? <p className="muted">No hay ventanas de mantenimiento registradas.</p> : <table className="grid"><thead><tr><th>Estado</th><th>Alcance</th><th>Motivo</th><th>Inicio</th><th>Fin</th><th></th></tr></thead><tbody>{windows.map(row=>{
        const start=Date.parse(row.starts_at), end=Date.parse(row.ends_at), active=start<=now&&now<end, future=start>now&&end>now
        return <tr key={row.id}><td><span className={`badge ${active?'UNKNOWN':future?'UP':'DOWN'}`}>{active?'En curso':future?'Programada':'Finalizada'}</span></td><td>{targetName(row)}</td><td>{row.reason.replace(/^MANTENIMIENTO:\s*/, '')}</td><td>{fmtDateTime(row.starts_at)}</td><td>{fmtDateTime(row.ends_at)}</td><td>{(active||future)&&<button className="btn secondary" disabled={busy===row.id} onClick={()=>void cancel(row)}>{busy===row.id?'Cancelando…':'Cancelar'}</button>}</td></tr>
      })}</tbody></table>}
    </section>
  </main>
}
