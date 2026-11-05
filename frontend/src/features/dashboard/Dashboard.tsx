import { useEffect, useState, type CSSProperties } from 'react'
import type { AlertOut, DeviceStatus, SystemStatus } from '../../types/api'
import { fmtAgo, fmtDateTime } from '../../services/format'
import { apiSend } from '../../services/api'

type View = 'dashboard' | 'maps' | 'devices' | 'services' | 'discovery' | 'alerts' | 'reports' | 'system' | 'users' | 'account'
const ORBIT = [[150,64],[275,42],[465,42],[590,64],[610,205],[475,254],[265,254],[130,205]]

function NetworkTopology({ devices, onOpen }: { devices: DeviceStatus[]; onOpen: () => void }) {
  const coreIndex = devices.findIndex(d => d.device_type === 'router' || d.device_type === 'firewall')
  const core = devices[coreIndex] ?? devices[0]
  const leaves = devices.filter((_, i) => !core || devices[i].device_id !== core.device_id).slice(0, ORBIT.length)
  const extra = Math.max(0, devices.length - leaves.length - (core ? 1 : 0))
  if (!devices.length) return <div className="topology-empty"><span>◎</span><strong>Sin dispositivos para visualizar</strong><small>Agrega equipos al inventario para ver la topología.</small></div>
  return <div className="topology-visual">
    <svg viewBox="0 0 740 300" role="img" aria-label="Topología resumida del inventario" onClick={onOpen}>
      <defs>
        <radialGradient id="coreGlow"><stop stopColor="#24d6e7" stopOpacity=".22"/><stop offset="1" stopColor="#24d6e7" stopOpacity="0"/></radialGradient>
        <filter id="nodeGlow"><feGaussianBlur stdDeviation="3" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
      </defs>
      <circle cx="370" cy="150" r="100" fill="url(#coreGlow)"/>
      {leaves.map((device, i) => {
        const point = ORBIT[i]
        return <g key={device.device_id} className="topology-link">
          <line x1="370" y1="150" x2={point[0]} y2={point[1]} className={'topology-line ' + device.state.toLowerCase()}/>
          <circle cx={point[0]} cy={point[1]} r="13" className={'topology-node ' + device.state.toLowerCase()} filter="url(#nodeGlow)"/>
          <text x={point[0]} y={point[1] + 30} className="topology-label" textAnchor="middle">{device.name.length > 17 ? device.name.slice(0, 16) + '…' : device.name}</text>
          <text x={point[0]} y={point[1] + 44} className="topology-ip" textAnchor="middle">{device.ip_address}</text>
          <title>{device.name} · {device.ip_address} · {device.state}</title>
        </g>
      })}
      <circle cx="370" cy="150" r="43" className={'topology-core ' + (core.state === 'UP' ? 'up' : core.state === 'DOWN' ? 'down' : 'unknown')}/>
      <circle cx="370" cy="150" r="30" className="topology-core-inner"/>
      <text x="370" y="147" className="topology-core-glyph" textAnchor="middle">{core.device_type === 'router' || core.device_type === 'firewall' ? '⌘' : '◈'}</text>
      <text x="370" y="165" className="topology-core-name" textAnchor="middle">{core.name.length > 13 ? core.name.slice(0, 12) + '…' : core.name}</text>
      <title>{core.name} · {core.ip_address} · {core.state}</title>
    </svg>
    <div className="topology-legend"><span><i className="legend-up"/>En línea</span><span><i className="legend-down"/>Caído</span><span><i className="legend-unknown"/>Sin confirmar</span>{extra > 0 && <small>+{extra} equipos fuera de la vista</small>}</div>
  </div>
}

interface SiteIncident {
  siteId: number
  siteName: string
  kind: 'edge' | 'gateway' | 'internet' | 'device' | 'unknown'
  title: string
  detail: string
  downCount: number
  unknownCount: number
  alertCount: number
  targetDeviceId: number | null
}

function buildSiteIncidents(devices: DeviceStatus[], alerts: AlertOut[]): SiteIncident[] {
  const sites = new Map<number, DeviceStatus[]>()
  for (const device of devices) sites.set(device.site_id, [...(sites.get(device.site_id) ?? []), device])

  const incidents: SiteIncident[] = []
  for (const [siteId, equipment] of sites) {
    const siteName = equipment[0]?.site_name ?? 'Sede'
    const edge = equipment.filter(device => device.device_type === 'router' || device.device_type === 'firewall')
    const edgeDown = edge.filter(device => device.state === 'DOWN')
    const edgeUp = edge.filter(device => device.state === 'UP')
    const gatewayDown = edgeUp.filter(device => device.wan_gateway_ip && device.wan_gateway_state === 'DOWN')
    const internetDown = edgeUp.filter(device =>
      device.wan_probe_ip && device.wan_probe_state === 'DOWN' && device.wan_gateway_state !== 'DOWN')
    const down = equipment.filter(device => device.state === 'DOWN')
    const unknown = equipment.filter(device => device.state === 'UNKNOWN')
    let kind: SiteIncident['kind'] | null = null
    let title = ''
    let detail = ''

    if (edgeDown.length) {
      kind = 'edge'
      title = 'Router o firewall de borde sin respuesta'
      const otherDown = down.filter(device => !edgeDown.some(edgeDevice => edgeDevice.device_id === device.device_id))
      detail = edgeDown.map(device => device.name + ' (' + device.ip_address + ')').join(', ')
      if (otherDown.length) detail += ' · ' + otherDown.length + ' equipo(s) adicionales caídos'
    } else if (gatewayDown.length) {
      kind = 'gateway'
      title = 'Gateway WAN sin respuesta'
      detail = gatewayDown.map(device => device.name + ' · gateway ' + device.wan_gateway_ip).join(' · ')
      if (down.length) detail += ' · ' + down.length + ' equipo(s) de la sede también caídos'
    } else if (internetDown.length) {
      kind = 'internet'
      title = 'Gateway responde, destino externo no'
      detail = internetDown.map(device => device.name + ' · prueba ' + device.wan_probe_ip).join(' · ')
      if (down.length) detail += ' · ' + down.length + ' equipo(s) de la sede caídos'
    } else if (down.length) {
      kind = 'device'
      title = down.length === 1 ? 'Dispositivo sin respuesta' : down.length + ' dispositivos sin respuesta'
      detail = down.slice(0, 3).map(device => device.name + ' (' + device.ip_address + ')').join(', ')
      if (down.length > 3) detail += ' y ' + (down.length - 3) + ' más'
    } else if (unknown.length && unknown.length === equipment.length) {
      kind = 'unknown'
      title = 'Monitoreo de la sede sin confirmar'
      detail = unknown.length + ' equipo(s) sin una comprobación disponible'
    }

    if (!kind) continue
    incidents.push({
      siteId, siteName, kind, title, detail, downCount: down.length, unknownCount: unknown.length,
      alertCount: alerts.filter(alert => alert.site_name === siteName &&
        (alert.state === 'firing' || alert.state === 'acknowledged')).length,
      targetDeviceId: (edgeDown[0] ?? gatewayDown[0] ?? internetDown[0] ?? down[0] ?? unknown[0])?.device_id ?? null,
    })
  }

  const rank: Record<SiteIncident['kind'], number> = { edge: 0, gateway: 1, internet: 2, device: 3, unknown: 4 }
  return incidents.sort((a, b) => rank[a.kind] - rank[b.kind] || b.downCount - a.downCount || a.siteName.localeCompare(b.siteName, 'es'))
}

function SystemPulse({ system }: { system: SystemStatus | null }) {
  if (!system) return <div className="pulse-empty">Cargando estado del sistema…</div>
  const entries = [
    ...system.checks.map(c => ({ key: c.key, name: c.title, ok: c.ok, note: c.detail ?? 'Comprobación correcta' })),
    ...system.heartbeats.map(h => ({ key: h.worker, name: h.title, ok: h.ok, note: h.age_s == null ? 'Sin latido' : 'Latido hace ' + fmtAgo(new Date(Date.now() - h.age_s * 1000).toISOString()).replace('hace ', '') })),
  ]
  return <div className="system-pulse-list">{entries.slice(0, 8).map(item => <div className="system-pulse-row" key={item.key}>
    <span className={'pulse-led ' + (item.ok ? 'ok' : 'bad')}/>
    <span className="pulse-name">{item.name}</span>
    <span className="pulse-note">{item.note}</span>
    <b className={item.ok ? 'pulse-ok' : 'pulse-bad'}>{item.ok ? 'OK' : 'FALLO'}</b>
  </div>)}</div>
}

export default function Dashboard({ devices, alerts, system, onNavigate, canOperate = false }: { devices: DeviceStatus[]; alerts: AlertOut[]; system: SystemStatus | null; onNavigate: (view: View) => void; canOperate?: boolean }) {
 const [now, setNow] = useState(() => new Date())
 const [pinging, setPinging] = useState<number | null>(null)
 const [pingResult, setPingResult] = useState<Record<number, string>>({})
 useEffect(() => { const timer = window.setInterval(() => setNow(new Date()), 30000); return () => window.clearInterval(timer) }, [])
 const up=devices.filter(d=>d.state==='UP').length, down=devices.filter(d=>d.state==='DOWN').length, unknown=devices.filter(d=>d.state==='UNKNOWN').length
 const availability=devices.length?Math.round(up/devices.length*100):0
 const latest=devices.reduce<string|null>((last,d)=>!last||(d.last_check_at&&d.last_check_at>last)?d.last_check_at:last,null)
 const activeAlertCount=alerts.filter(a=>a.state==='firing'||a.state==='acknowledged').length
 const criticalAlertCount=alerts.filter(a=>(a.state==='firing'||a.state==='acknowledged')&&a.severity==='critical').length
 const activeAlerts=alerts.filter(a=>a.state==='firing'||a.state==='acknowledged').sort((a,b)=>(b.fired_at??b.created_at).localeCompare(a.fired_at??a.created_at)).slice(0,5)
 const siteIncidents=buildSiteIncidents(devices,alerts)
 const healthyChecks=system?.checks.filter(c=>c.ok).length ?? 0
 const systemChecks=system?.checks.length ?? 0
 const clock=now.toLocaleTimeString('es-CO',{hour:'2-digit',minute:'2-digit',second:'2-digit',timeZone:'America/Bogota'})
 return <main className="dashboard command-center">
  <section className="command-hero">
   <div className="command-hero-grid"/>
   <div className="command-hero-content">
    <div><div className="live-kicker"><i/>NETCORE · OPERACIONES DE RED · BOGOTÁ</div><h2>Centro de control</h2><p>Telemetría y estado operacional de tu infraestructura.</p></div>
    <div className="command-clock"><span>{clock}</span><small>HORA LOCAL · UTC−5</small></div>
   </div>
   <div className={'command-system '+(system?.overall_ok===false?'degraded':'')}><span className="command-system-led"/><span>{system?.overall_ok===false?'ATENCIÓN REQUERIDA':'TODOS LOS SISTEMAS OPERATIVOS'}</span><small>{system ? healthyChecks + '/' + systemChecks + ' verificaciones sanas' : 'Sin datos'}</small></div>
  </section>

  <section className="command-metrics" aria-label="Métricas de red">
   <button className="metric-tile" onClick={()=>onNavigate('devices')}><span className="metric-overline">DISPOSITIVOS EN LÍNEA</span><strong className="metric-number green">{up.toString().padStart(2,'0')}<small> / {devices.length}</small></strong><span className="metric-foot"><i className="metric-led green-led"/>Responden al monitoreo</span></button>
   <button className="metric-tile" onClick={()=>onNavigate('devices')}><span className="metric-overline">DISPOSITIVOS CAÍDOS</span><strong className={'metric-number '+(down?'red':'neutral')}>{down.toString().padStart(2,'0')}</strong><span className="metric-foot"><i className={'metric-led '+(down?'red-led':'neutral-led')}/>{down?'Requieren atención':'Sin caídas detectadas'}</span></button>
   <button className="metric-tile" onClick={()=>onNavigate('devices')}><span className="metric-overline">ESTADO DESCONOCIDO</span><strong className={'metric-number '+(unknown?'amber':'neutral')}>{unknown.toString().padStart(2,'0')}</strong><span className="metric-foot"><i className={'metric-led '+(unknown?'amber-led':'neutral-led')}/>Sin confirmación reciente</span></button>
   <button className="metric-tile" onClick={()=>onNavigate('alerts')}><span className="metric-overline">ALERTAS ACTIVAS</span><strong className={'metric-number '+(activeAlertCount?'amber':'green')}>{activeAlertCount.toString().padStart(2,'0')}</strong><span className="metric-foot"><i className={'metric-led '+(activeAlertCount?'amber-led':'green-led')}/>Incidentes por atender</span></button>
   <button className="metric-tile" onClick={()=>onNavigate('alerts')}><span className="metric-overline">ALERTAS CRÍTICAS</span><strong className={'metric-number '+(criticalAlertCount?'red':'neutral')}>{criticalAlertCount.toString().padStart(2,'0')}</strong><span className="metric-foot"><i className={'metric-led '+(criticalAlertCount?'red-led':'neutral-led')}/>Severidad crítica activa</span></button>
   <button className="metric-tile availability-tile" onClick={()=>onNavigate('reports')}>
    <span className="metric-overline">DISPONIBILIDAD ACTUAL</span><span className="metric-main"><strong>{devices.length?availability:'—'}<small>{devices.length?'%':' '}</small></strong><span className="metric-orbit" style={{'--progress':availability+'%'} as CSSProperties}><i>◉</i></span></span>
    <span className="metric-foot">{up} conectados <b>·</b> {devices.length} monitoreados</span>
   </button>
  </section>

  <section className="command-main-grid">
   <article className="panel command-panel topology-panel">
    <header className="command-panel-header"><div><span className="panel-index">01 / RED</span><h3>Topología viva</h3><p>Vista de los nodos principales de tu inventario</p></div><button className="command-link" onClick={()=>onNavigate('maps')}>ABRIR MAPAS <span>↗</span></button></header>
    <NetworkTopology devices={devices} onOpen={()=>onNavigate('maps')}/>
   </article>
   <article className="panel command-panel pulse-panel">
    <header className="command-panel-header"><div><span className="panel-index">02 / PLATAFORMA</span><h3>Salud del sistema</h3><p>Workers, base de datos y comprobaciones</p></div><span className={'system-grade '+(system?.overall_ok===false?'bad':'good')}>{system?.overall_ok===false?'DEGRADADO':'ESTABLE'}</span></header>
    <SystemPulse system={system}/>
    <button className="panel-bottom-link" onClick={()=>onNavigate('system')}>VER DIAGNÓSTICO COMPLETO <span>→</span></button>
   </article>
  </section>

  <section className="command-events-grid">
   <article className="panel command-panel">
    <header className="command-panel-header"><div><span className="panel-index">03 / DIAGNÓSTICO</span><h3>Estado por sede</h3></div><button className="command-link" onClick={()=>onNavigate('devices')}>INVENTARIO ↗</button></header>
    {siteIncidents.length ? <div className="site-diagnosis-list">{siteIncidents.slice(0,8).map((incident,index)=>
      <article className={'site-diagnosis-row ' + incident.kind} key={incident.siteId}>
        <span className="site-diagnosis-index">{String(index+1).padStart(2,'0')}</span>
        <div className="site-diagnosis-copy">
          <b>{incident.siteName}<small>{incident.title}</small></b>
          <p>{incident.detail}</p>
          <span>{incident.downCount} caídos · {incident.unknownCount} sin confirmar · {incident.alertCount} alerta(s) activa(s)</span>
        </div>
        <span className={'site-diagnosis-cause ' + incident.kind}>
          {incident.kind === 'edge' ? 'BORDE' : incident.kind === 'gateway' ? 'GATEWAY WAN' : incident.kind === 'internet' ? 'INTERNET' : incident.kind === 'device' ? 'EQUIPO' : 'MONITOREO'}
        </span>
        <div className="site-diagnosis-actions">
          {canOperate && incident.targetDeviceId != null && <button className="btn secondary" disabled={pinging === incident.targetDeviceId}
            onClick={async()=>{ const id=incident.targetDeviceId!; setPinging(id); setPingResult({...pingResult,[id]:'Comprobando…'}); try { const result=await apiSend<{success:boolean;rtt_ms:number|null;packet_loss:number}>('POST',`/devices/${id}/ping`); setPingResult({...pingResult,[id]:result.success?`Responde · ${result.rtt_ms == null ? 'RTT n/d' : result.rtt_ms.toFixed(1)+' ms'}`:`Sin respuesta · ${result.packet_loss}% pérdida`}) } catch(e) { setPingResult({...pingResult,[id]:e instanceof Error?e.message:String(e)}) } finally { setPinging(null) } }}>
            {pinging === incident.targetDeviceId ? 'Probando…' : 'Probar ping'}
          </button>}
          <button className="site-diagnosis-link" onClick={()=>onNavigate('devices')}>Inventario ↗</button>
          {incident.targetDeviceId != null && pingResult[incident.targetDeviceId] && <small className="muted">{pingResult[incident.targetDeviceId]}</small>}
        </div>
      </article>
    )}</div>:<div className="command-empty"><span>✓</span><div><b>Sedes estables</b><small>No se detectan caídas de borde, gateway WAN ni dispositivos.</small></div></div>}
   </article>
   <article className="panel command-panel">
    <header className="command-panel-header"><div><span className="panel-index">04 / ALERTAS</span><h3>Actividad reciente</h3></div><button className="command-link" onClick={()=>onNavigate('alerts')}>CENTRO DE ALERTAS ↗</button></header>
    {activeAlerts.length?<div className="activity-list">{activeAlerts.map(a=><div className="activity-row" key={a.id}><span className={'activity-severity '+a.severity}/><div className="activity-content"><b>{a.device_name}<span className="activity-rule"> / {a.rule_name}</span></b><small>{a.summary}</small></div><time>{fmtDateTime(a.fired_at??a.created_at)}</time></div>)}</div>:<div className="command-empty"><span>✓</span><div><b>Sin incidentes activos</b><small>El centro de alertas está tranquilo.</small></div></div>}
   </article>
  </section>

  <footer className="command-footer"><span><i className="footer-live"/>SONDEO ACTIVO</span><span>Último ciclo {fmtAgo(latest)}</span><span className="footer-spacer"/>{canOperate && <button onClick={()=>onNavigate('discovery')}>+ DESCUBRIMIENTO PUNTUAL</button>}<button onClick={()=>onNavigate('reports')}>REPORTES ↗</button></footer>
 </main>
}
