import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiSend } from '../../services/api'
import type { DeviceStatus, MapDetail, MapSummary } from '../../types/api'

interface MapDomainOption { id: number; name: string }
interface DeviceEntry {
  key: string; mapName: string; name: string; ip: string; state: string
  deviceId: number | null; iconData: string | null
}

export default function MapsOrganizationView({ statuses }: { statuses: DeviceStatus[] }) {
  const [domains, setDomains] = useState<MapDomainOption[]>([])
  const [maps, setMaps] = useState<MapSummary[]>([])
  const [newDomainName, setNewDomainName] = useState('')
  const [deleteDomainId, setDeleteDomainId] = useState('')
  const [inventoryDomainId, setInventoryDomainId] = useState('')
  const [deviceEntries, setDeviceEntries] = useState<DeviceEntry[]>([])
  const [selectedMapId, setSelectedMapId] = useState('')
  const [assignDomainId, setAssignDomainId] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loadingDevices, setLoadingDevices] = useState(false)

  const load = useCallback(async () => {
    try {
      const [domainList, mapList] = await Promise.all([
        apiGet<MapDomainOption[]>('/maps/domains'), apiGet<MapSummary[]>('/maps'),
      ])
      setDomains(domainList)
      setMaps(mapList)
      setInventoryDomainId(current => current || String(domainList[0]?.id ?? ''))
      setDeleteDomainId(current => current || String(domainList[0]?.id ?? ''))
      setSelectedMapId(current => current || String(mapList[0]?.id ?? ''))
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
  }, [])
  useEffect(() => { void load() }, [load])

  const selectedMap = maps.find(map => String(map.id) === selectedMapId)
  const inventoryMaps = maps.filter(map => inventoryDomainId
    ? map.domain_ids.includes(Number(inventoryDomainId))
    : map.domain_ids.length === 0)
  const deviceTree = new Map<string, DeviceEntry[]>()
  for (const entry of deviceEntries) deviceTree.set(entry.mapName, [...(deviceTree.get(entry.mapName) ?? []), entry])

  useEffect(() => {
    let active = true
    setDeviceEntries([])
    if (!inventoryMaps.length) { setLoadingDevices(false); return }
    setLoadingDevices(true)
    Promise.all(inventoryMaps.map(map => apiGet<MapDetail>('/maps/' + map.id).then(detail => ({ map, detail }))))
      .then(rows => {
        if (!active) return
        const entries: DeviceEntry[] = []
        for (const { map, detail } of rows) for (const node of detail.nodes) {
          if (node.node_type === 'device' && node.device_id != null) entries.push({
            key: map.id + ':' + node.id, mapName: map.name,
            name: node.label || node.device_name || 'Equipo', ip: node.device_ip || '—',
            state: node.device_enabled === false ? 'DISABLED' : 'UNKNOWN',
            deviceId: node.device_id, iconData: node.icon_data,
          })
          else if (node.node_type === 'ip' && node.ip_address) entries.push({
            key: map.id + ':' + node.id, mapName: map.name,
            name: node.label || node.ip_address, ip: node.ip_address,
            state: node.last_ping_ok ? 'UP' : node.last_ping_ok === false ? 'DOWN' : 'UNKNOWN',
            deviceId: null, iconData: node.icon_data,
          })
          else if (node.node_type === 'map') for (const id of node.child_device_ids ?? []) entries.push({
            key: map.id + ':' + node.id + ':' + id, mapName: node.child_map_name || map.name,
            name: 'Equipo ' + id, ip: '—', state: 'UNKNOWN', deviceId: id, iconData: null,
          })
        }
        setDeviceEntries([...new Map(entries.map(entry => [entry.key, entry])).values()]
          .sort((a, b) => a.name.localeCompare(b.name, 'es')))
        setLoadingDevices(false)
      })
      .catch(e => { if (active) { setError(e instanceof Error ? e.message : String(e)); setLoadingDevices(false) } })
    return () => { active = false }
  }, [inventoryMaps.map(map => map.id).join(',')])

  async function createDomain() {
    if (!newDomainName.trim()) return
    try {
      await apiSend('POST', '/maps/domains', { name: newDomainName.trim() })
      setNewDomainName(''); setError(null); await load()
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
  }

  async function deleteDomain() {
    const domain = domains.find(item => String(item.id) === deleteDomainId)
    if (!domain || !window.confirm('¿Eliminar el dominio «' + domain.name + '»? Los mapas quedarán sin clasificar.')) return
    try {
      await apiSend('DELETE', '/maps/domains/' + domain.id)
      setError(null); await load()
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
  }

  async function assignMap(domainId: number, remove = false) {
    if (!selectedMap) return
    const current = selectedMap.domain_ids ?? []
    const next = remove
      ? current.filter(id => id !== domainId)
      : [...new Set([...current, domainId])]
    try {
      await apiSend('PATCH', '/maps/' + selectedMap.id, { domain_ids: next })
      setError(null)
      await load()
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
  }

  async function removeAllAssignments() {
    if (!selectedMap || !selectedMap.domain_ids.length) return
    if (!window.confirm('¿Quitar todas las asignaciones de dominio del mapa «' + selectedMap.name + '»? El mapa no se eliminará.')) return
    try {
      await apiSend('PATCH', '/maps/' + selectedMap.id, { domain_ids: [] })
      setError(null)
      await load()
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
  }

  return (
    <main className="map-organization-page">
      <section className="map-organization-hero">
        <span className="map-organization-icon" aria-hidden="true">⌘</span>
        <div><span className="panel-index">ORGANIZACIÓN DE RED</span><h2>Dominios de mapas</h2>
          <p>Clasifica los mapas por tipo de sede o negocio y consulta sus equipos.</p></div>
        <div className="map-organization-totals"><b>{domains.length}<small>dominios</small></b><b>{maps.length}<small>mapas</small></b></div>
      </section>

      {error && <p className="error map-organization-error">{error}</p>}
      <div className="map-organization-grid">
        <section className="panel map-organization-card">
          <header><span className="map-admin-number">01</span><div><h3>Dominios</h3><p>Por ejemplo: centros comerciales, hoteles o clínicas.</p></div></header>
          <label>Nombre del nuevo dominio<input value={newDomainName} maxLength={100} placeholder="Ej.: Centros comerciales"
            onChange={event => setNewDomainName(event.target.value)} /></label>
          <button onClick={() => void createDomain()} disabled={!newDomainName.trim()}>＋ Crear dominio</button>
          <div className="map-admin-divider" />
          <label>Dominio que deseas eliminar
            <select value={deleteDomainId} onChange={event => setDeleteDomainId(event.target.value)}>
              <option value="">Seleccionar dominio…</option>
              {domains.map(domain => <option key={domain.id} value={domain.id}>{domain.name}</option>)}
            </select>
          </label>
          <button className="danger" onClick={() => void deleteDomain()} disabled={!deleteDomainId}>Eliminar dominio</button>
          <small className="map-organization-note">Al eliminarlo, los mapas quedan sin clasificar.</small>
        </section>

        <section className="panel map-organization-card">
          <header><span className="map-admin-number">02</span><div><h3>Asignar mapas</h3><p>Un mapa puede pertenecer a varios dominios a la vez.</p></div></header>
          <label>Mapa<select value={selectedMapId} onChange={event => { setSelectedMapId(event.target.value); setAssignDomainId('') }}>
            {maps.length === 0 && <option value="">No hay mapas</option>}
            {maps.map(map => <option key={map.id} value={map.id}>{map.name}</option>)}
          </select></label>
          <div className="map-domain-assignment-label">Dominios asignados</div>
          {selectedMap?.domain_ids.length ? <div className="map-domain-assignment-list">
            {selectedMap.domain_ids.map((id, index) => {
              const domain = domains.find(item => item.id === id)
              return <div className="map-domain-assignment" key={id}>
                <span className="map-domain-assignment-dot" />
                <strong>{domain?.name ?? selectedMap.domain_names[index] ?? 'Dominio ' + id}</strong>
                <button type="button" className="map-domain-remove" onClick={() => void assignMap(id, true)} title="Quitar este dominio" aria-label="Quitar dominio">×</button>
              </div>
            })}
          </div> : <p className="map-organization-note">Este mapa todavía no está asignado a un dominio.</p>}
          <div className="map-domain-add-row">
            <select value={assignDomainId} disabled={!selectedMap || domains.every(domain => selectedMap.domain_ids.includes(domain.id))}
              onChange={event => setAssignDomainId(event.target.value)}>
              <option value="">Seleccionar dominio para agregar…</option>
              {domains.filter(domain => !selectedMap?.domain_ids.includes(domain.id)).map(domain =>
                <option key={domain.id} value={domain.id}>{domain.name}</option>)}
            </select>
            <button type="button" className="map-domain-add-button" onClick={() => {
              if (!assignDomainId) return
              void assignMap(Number(assignDomainId))
              setAssignDomainId('')
            }} disabled={!assignDomainId || !selectedMap || domains.every(domain => selectedMap.domain_ids.includes(domain.id))}>
              {!domains.length ? 'Crea un dominio primero' : !selectedMap ? 'Selecciona un mapa'
                : domains.every(domain => selectedMap.domain_ids.includes(domain.id))
                  ? 'Todos asignados' : assignDomainId ? 'Agregar dominio' : 'Selecciona un dominio'}
            </button>
          </div>
          {selectedMap?.domain_ids.length ? <button className="danger map-domain-clear" onClick={() => void removeAllAssignments()}>
            Quitar todas las asignaciones
          </button> : null}
        </section>

        <section className="panel map-organization-card map-organization-devices">
          <header><span className="map-admin-number">03</span><div><h3>Equipos por dominio</h3><p>Consulta los dispositivos e IP de los mapas de cada dominio.</p></div></header>
          <label>Dominio<select value={inventoryDomainId} onChange={event => setInventoryDomainId(event.target.value)}>
            <option value="">Sin clasificar</option>
            {domains.map(domain => <option key={domain.id} value={domain.id}>{domain.name}</option>)}
          </select></label>
          <div className="map-device-catalog-heading">
            <b>{loadingDevices ? 'Buscando equipos…' : deviceEntries.length + ' equipos encontrados'}</b>
            <span>{inventoryMaps.length} mapas</span>
          </div>
          {loadingDevices ? <p className="muted">Cargando equipos de los mapas seleccionados…</p> :
            inventoryMaps.length ? <div className="map-device-tree">
              {inventoryMaps.map(map => {
                const entries = deviceTree.get(map.name) ?? []
                return <details className="map-device-tree-map" key={map.id} open>
                  <summary>
                    <span className="map-tree-folder" aria-hidden="true">▰</span>
                    <strong>{map.name}</strong>
                    <small>{entries.length} equipo(s)</small>
                  </summary>
                  {entries.length ? <ul>
                    {entries.map(entry => {
                      const status = entry.deviceId == null ? undefined : statuses.find(item => item.device_id === entry.deviceId)
                      const name = status?.name ?? entry.name
                      const ip = status?.ip_address ?? entry.ip
                      const state = status?.state ?? entry.state
                      return <li className="map-device-tree-item" key={entry.key}>
                        <span className="map-device-tree-branch" aria-hidden="true" />
                        <span className="map-device-tree-icon">{entry.iconData
                          ? <img src={entry.iconData} alt="" />
                          : <span aria-hidden="true">{entry.deviceId == null ? '⌁' : '▣'}</span>}</span>
                        <span className="map-device-tree-copy"><strong title={name}>{name}</strong><code>{ip}</code></span>
                        <span className={'badge ' + state}>{state}</span>
                      </li>
                    })}
                  </ul> : <p className="map-device-tree-empty">Este mapa no tiene equipos agregados.</p>}
                </details>
              })}
            </div> : <div className="map-device-catalog-empty"><span aria-hidden="true">⌕</span>
              <b>No hay mapas en esta ubicación</b><small>Asigna mapas a este dominio o agrega equipos desde Mapas.</small>
            </div>}
          <small className="map-organization-note">Cada mapa contiene sus dispositivos registrados e IP manuales.</small>
        </section>
      </div>
    </main>
  )
}
