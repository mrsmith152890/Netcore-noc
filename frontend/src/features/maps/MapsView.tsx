import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiSend } from '../../services/api'
import type { DeviceStatus, MapSummary } from '../../types/api'
import MapCanvas from './MapCanvas'
import MapDomainOverview from './MapDomainOverview'
import MapExplorer from './MapExplorer'

interface MapDomainOption { id: number; name: string }

interface RouterOption {
  id: number
  name: string
  ip_address: string
  device_type: string
}
interface ScanHost {
  ip: string
  source: 'ping'
  label?: string | null
  rtt_ms: number | null
}
interface NetworkScan {
  router_device_id: number
  router_name: string
  cidr: string
  arp_available: boolean
  arp_error: string | null
  hosts: ScanHost[]
}

const SOURCE_LABEL: Record<ScanHost['source'], string> = { ping: 'Respondió ping' }

export default function MapsView({ statuses }: { statuses: DeviceStatus[] }) {
  const [maps, setMaps] = useState<MapSummary[]>([])
  const [domains, setDomains] = useState<MapDomainOption[]>([])
  const [routers, setRouters] = useState<RouterOption[]>([])
  const [domainFilter, setDomainFilter] = useState('')
  const [newMapDomainId, setNewMapDomainId] = useState('')
  const [selected, setSelected] = useState<number | null>(null)
  const [trail, setTrail] = useState<number[]>([])
  const [error, setError] = useState<string | null>(null)
  const [discoverOpen, setDiscoverOpen] = useState(false)
  const [routerId, setRouterId] = useState('')
  const [cidr, setCidr] = useState('')
  const [scan, setScan] = useState<NetworkScan | null>(null)
  const [selectedIps, setSelectedIps] = useState<Set<string>>(new Set())
  const [hostNames, setHostNames] = useState<Record<string, string>>({})
  const [mapName, setMapName] = useState('')
  const [busy, setBusy] = useState(false)
  const [overviewMode, setOverviewMode] = useState(false)

  const loadMaps = useCallback(async () => {
    try {
      const [list, domainList] = await Promise.all([
        apiGet<MapSummary[]>('/maps'),
        apiGet<MapDomainOption[]>('/maps/domains'),
      ])
      setMaps(list)
      setDomains(domainList)
      setSelected(cur => cur ?? list[0]?.id ?? null)
      setDomainFilter(cur => cur || (list[0]?.domain_ids[0] == null ? '-1' : String(list[0].domain_ids[0])))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    void loadMaps()
    void apiGet<RouterOption[]>('/devices')
      .then(devices => {
        const list = devices
        setRouters(list)
        const router = list.find(d => d.device_type === 'router')
        setRouterId(router ? String(router.id) : '')
      })
      .catch(e => setError(e instanceof Error ? e.message : String(e)))
  }, [loadMaps])

  const visibleMaps = maps.filter(map => !domainFilter || (domainFilter === '-1' ? map.domain_ids.length === 0 : map.domain_ids.includes(Number(domainFilter))))
  const byId = new Map(maps.map(m => [m.id, m]))
  const current = selected != null ? byId.get(selected) ?? null : null
  const crumbs = trail.filter(id => byId.has(id))
  const fail = (e: unknown) => setError(e instanceof Error ? e.message : String(e))

  const open = (id: number) => {
    if (overviewMode) setTrail([])
    else setTrail(t => (selected != null ? [...t, selected] : t))
    setOverviewMode(false)
    setSelected(id)
  }
  const goTo = (index: number) => {
    setSelected(crumbs[index])
    setTrail(crumbs.slice(0, index))
  }

  async function createMap() {
    const name = window.prompt('Nombre del nuevo mapa')
    if (!name?.trim()) return
    try {
      const m = await apiSend<MapSummary>('POST', '/maps', { name: name.trim(), domain_ids: newMapDomainId ? [Number(newMapDomainId)] : [] })
      await loadMaps()
      setTrail([])
      setSelected(m.id)
      setError(null)
    } catch (e) {
      fail(e)
    }
  }

  async function scanNetwork() {
    if (!routerId || !cidr.trim()) return
    setBusy(true)
    setError(null)
    setScan(null)
    try {
      const result = await apiSend<NetworkScan>('POST', '/maps/discover', {
        router_device_id: Number(routerId),
        cidr: cidr.trim(),
      })
      setScan(result)
      setSelectedIps(new Set(result.hosts.map(host => host.ip)))
      setHostNames(Object.fromEntries(result.hosts.map(host => [host.ip, host.label ?? ''])))
      const router = routers.find(r => r.id === result.router_device_id)
      setMapName(((router?.name ?? result.router_name) + ' ' + result.cidr).slice(0, 100))
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e)
      setError(message.includes('Este rango no es privado')
        ? message + '. Regístralo en Descubrimiento para la sede de este router y marca “Autorizar rango público propio (VPN)”.'
        : message)
    } finally {
      setBusy(false)
    }
  }

  async function createMapFromScan() {
    if (!scan || !mapName.trim()) return
    setBusy(true)
    try {
      const m = await apiSend<MapSummary>('POST', '/maps/from-scan', {
        name: mapName.trim(),
        domain_ids: newMapDomainId ? [Number(newMapDomainId)] : [],
        router_device_id: scan.router_device_id,
        cidr: scan.cidr,
        hosts: scan.hosts.filter(host => selectedIps.has(host.ip)).map(host => ({
          ...host,
          label: hostNames[host.ip]?.trim() || null,
        })),
      })
      await loadMaps()
      setTrail([])
      setSelected(m.id)
      setDiscoverOpen(false)
      setScan(null)
      setError(null)
    } catch (e) {
      fail(e)
    } finally {
      setBusy(false)
    }
  }

  async function renameMap() {
    if (!current) return
    const name = window.prompt('Nuevo nombre', current.name)
    if (!name?.trim() || name.trim() === current.name) return
    try {
      await apiSend('PATCH', '/maps/' + current.id, { name: name.trim() })
      await loadMaps()
      setError(null)
    } catch (e) {
      fail(e)
    }
  }

  async function deleteMap() {
    if (!current) return
    const ok = window.confirm('¿Eliminar el mapa «' + current.name + '»? Desaparecerá también como submapa de otros mapas. ' +
      'Los dispositivos y su histórico no se borran.')
    if (!ok) return
    try {
      await apiSend('DELETE', '/maps/' + current.id)
      setTrail([])
      setSelected(null)
      await loadMaps()
      setError(null)
    } catch (e) {
      fail(e)
    }
  }

  return (
    <section className="panel">
      <MapExplorer maps={maps} domains={domains} selectedId={overviewMode ? null : selected}
        activeDomainId={domainFilter ? (domainFilter === '-1' ? -1 : Number(domainFilter)) : null}
        onSelectDomain={id => {
          setDomainFilter(id == null ? '-1' : String(id))
          setNewMapDomainId(id == null ? '' : String(id))
          setSelected(null)
          setTrail([])
          setOverviewMode(true)
        }}
        onSelect={id => {
          const map = maps.find(item => item.id === id)
          setSelected(id)
          setTrail([])
          setOverviewMode(false)
          setDomainFilter(map?.domain_ids.includes(Number(domainFilter))
            ? domainFilter
            : map?.domain_ids[0] == null ? '-1' : String(map.domain_ids[0]))
        }} />

      <div className="map-toolbar map-actions-toolbar">
        <label className="map-new-map-group">Dominio de mapas nuevos
          <select value={newMapDomainId} onChange={e => setNewMapDomainId(e.target.value)}>
            <option value="">Sin clasificar</option>
            {domains.map(domain => <option key={domain.id} value={domain.id}>{domain.name}</option>)}
          </select>
        </label>
        <button className={overviewMode ? 'active' : ''} onClick={() => {
          const next = !overviewMode
          setOverviewMode(next)
          setSelected(next ? null : visibleMaps[0]?.id ?? null)
          setTrail([])
        }}>
          {overviewMode ? 'Abrir primer mapa' : 'Vista consolidada'}
        </button>
        <button onClick={createMap}>Nuevo mapa manual</button>
        <button onClick={() => { setDiscoverOpen(v => !v); setScan(null); setError(null) }}>Descubrir red</button>
        <button onClick={renameMap} disabled={!current}>Renombrar mapa</button>
        <button className="danger" onClick={deleteMap} disabled={!current}>Eliminar mapa</button>
        {error && <span className="error">{error}</span>}
      </div>

      {discoverOpen && (
        <div className="panel">
          <h3>Descubrimiento puntual de una subred</h3>
          <div className="form-row">
            <select value={routerId} onChange={e => setRouterId(e.target.value)} disabled={busy || !routers.length}>
              <option value="">Selecciona router o equipo de borde…</option>
              {!routers.length && <option value="" disabled>No hay dispositivos habilitados en el inventario</option>}
              {routers.map(router => (
                <option key={router.id} value={router.id}>
                  {router.name} ({router.ip_address}) · {router.device_type}
                </option>
              ))}
            </select>
            <input value={cidr} onChange={e => setCidr(e.target.value)}
              placeholder="IP/prefijo, por ejemplo 192.0.2.1/28"
              aria-label="Subred del router" disabled={busy} />
            <button onClick={() => void scanNetwork()} disabled={busy || !routerId || !cidr.trim()}>
              {busy && !scan ? 'Buscando…' : 'Buscar IPs'}
            </button>
            <button onClick={() => { setDiscoverOpen(false); setScan(null) }} disabled={busy}>Cerrar</button>
          </div>
          <p className="muted">
            Solo se agregarán IP que respondan ping. Si hay SNMP, la tabla ARP se consulta como referencia,
            pero no agrega equipos que no respondan. Puedes asignarles nombre antes de crear el mapa.
            Si el rango usa IP públicas, primero autorízalo en Descubrimiento para la sede del router.
          </p>
          {scan && (
            <div>
              <p>
                <strong>{scan.hosts.length} IP(s) encontradas</strong> en {scan.cidr}.
                {scan.arp_available ? ' ARP consultada como referencia.' : ' ' + (scan.arp_error ?? 'Solo se consultó ping.')}
              </p>
              {scan.hosts.length > 0 ? (
                <div style={{ maxHeight: 220, overflowY: 'auto', marginBottom: 12 }}>
                  {scan.hosts.map(host => (
                    <div className="scan-host-row" key={host.ip}>
                      <input type="checkbox" checked={selectedIps.has(host.ip)}
                        onChange={e => setSelectedIps(current => {
                          const next = new Set(current)
                          if (e.target.checked) next.add(host.ip)
                          else next.delete(host.ip)
                          return next
                        })} />
                      <span>{host.ip}</span>
                      <span className="muted">{SOURCE_LABEL[host.source]}</span>
                      {host.rtt_ms != null && <span className="muted">{host.rtt_ms.toFixed(1)} ms</span>}
                      <input className="discovery-host-name" value={hostNames[host.ip] ?? ''} maxLength={200}
                        onChange={e => setHostNames(current => ({ ...current, [host.ip]: e.target.value }))}
                        placeholder="Nombre opcional" aria-label={'Nombre visible para ' + host.ip} />
                    </div>
                  ))}
                </div>
              ) : <p className="muted">No se detectaron IPs; el mapa aún puede crearse con el router.</p>}
              <div className="form-row">
                <input value={mapName} onChange={e => setMapName(e.target.value)} maxLength={100}
                  placeholder="Nombre del mapa" aria-label="Nombre del mapa" disabled={busy} />
                <button onClick={() => void createMapFromScan()} disabled={busy || !mapName.trim()}>
                  {busy ? 'Creando…' : 'Crear mapa con ' + selectedIps.size + ' IP(s)'}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {crumbs.length > 0 && current && (
        <div className="crumbs">
          <button onClick={() => goTo(crumbs.length - 1)}>← Volver</button>
          {crumbs.map((id, i) => (
            <span key={String(id) + '-' + i}>
              <button onClick={() => goTo(i)}>{byId.get(id)?.name}</button> ›{' '}
            </span>
          ))}
          <strong>{current.name}</strong>
        </div>
      )}
      {overviewMode ? (
        <MapDomainOverview maps={visibleMaps} statuses={statuses} allMaps={maps}
          domainName={domainFilter === '-1' ? 'Sin clasificar' : domains.find(domain => String(domain.id) === domainFilter)?.name ?? 'Todos los dominios'}
          onOpenMap={open} />
      ) : selected != null ? (
        <MapCanvas key={selected} mapId={selected} statuses={statuses} maps={maps} onOpenMap={open} />
      ) : (
        <p className="muted">Crea un mapa manual o descubre una subred para empezar.</p>
      )}
    </section>
  )
}
