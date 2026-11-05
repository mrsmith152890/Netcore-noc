import { useState } from 'react'
import { usePolling } from '../../hooks/usePolling'
import { apiGet } from '../../services/api'
import { fmtDateTime } from '../../services/format'

interface AuditRow { id:number; at:string; username:string|null; ip:string|null; method:string; path:string; status_code:number; detail:string|null }
export default function AuditView() {
  const [username,setUsername]=useState(''), [filter,setFilter]=useState('')
  const path='/audit?limit=250'+(filter?'&username='+encodeURIComponent(filter):'')
  const {data,error}=usePolling(()=>apiGet<AuditRow[]>(path),15000,[filter])
  return <main className="audit-page"><section className="panel">
    <div className="sites-section-heading"><span>≋</span><div><span className="panel-index">SEGURIDAD · TRAZABILIDAD</span><h2>Historial de cambios</h2><p>Acciones realizadas y accesos denegados registrados por el sistema. Visible solo para administradores.</p></div></div>
    <div className="form-row"><input placeholder="Filtrar por usuario" value={username} onChange={e=>setUsername(e.target.value)} onKeyDown={e=>{if(e.key==='Enter')setFilter(username.trim())}} /><button type="button" onClick={()=>setFilter(username.trim())}>Buscar</button><button className="btn secondary" type="button" onClick={()=>{setUsername('');setFilter('')}}>Limpiar</button><span className="muted">{data?.length ?? 0} eventos recientes</span></div>
    {error&&<p className="error">{error}</p>}
    {!data?.length&&!error?<p className="muted">Cargando historial o no hay eventos para mostrar.</p>:<div className="audit-table-wrap"><table className="grid"><thead><tr><th>Fecha</th><th>Usuario</th><th>Acción</th><th>Ruta</th><th>IP</th><th>Resultado</th><th>Detalle</th></tr></thead><tbody>{(data??[]).map(row=><tr key={row.id}><td>{fmtDateTime(row.at)}</td><td>{row.username??'Sistema'}</td><td><code>{row.method}</code></td><td><code>{row.path}</code></td><td>{row.ip??'—'}</td><td><span className={`badge ${row.status_code<400?'UP':'DOWN'}`}>{row.status_code}</span></td><td className="muted">{row.detail??'—'}</td></tr>)}</tbody></table></div>}
  </section></main>
}
