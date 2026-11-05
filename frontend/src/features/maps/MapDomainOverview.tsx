import MapCanvas from './MapCanvas'
import type { DeviceStatus, MapSummary } from '../../types/api'

export default function MapDomainOverview({ maps, statuses, allMaps, domainName, onOpenMap }: {
  maps: MapSummary[]
  statuses: DeviceStatus[]
  allMaps: MapSummary[]
  domainName: string
  onOpenMap: (id: number) => void
}) {
  return (
    <section className="map-domain-overview">
      <header className="map-domain-overview-heading">
        <div><span className="panel-index">VISTA DEL DOMINIO</span>
          <h3>{domainName}</h3>
          <p>{maps.length} mapa(s) abiertos a la vez. Selecciona un mapa arriba para enfocarlo individualmente.</p>
        </div>
        <span>{maps.length} mapas</span>
      </header>
      {!maps.length ? <p className="muted">Este dominio aún no tiene mapas.</p> : (
        <div className="map-domain-overview-grid">
          {maps.map((map, index) => (
            <article className="map-domain-overview-card" key={map.id}>
              <header>
                <div><small>MAPA {String(index + 1).padStart(2, '0')}</small><strong>{map.name}</strong></div>
                <button type="button" onClick={() => onOpenMap(map.id)}>Ver solo este mapa ↗</button>
              </header>
              <MapCanvas mapId={map.id} statuses={statuses} maps={allMaps} onOpenMap={onOpenMap} />
            </article>
          ))}
        </div>
      )}
    </section>
  )
}
