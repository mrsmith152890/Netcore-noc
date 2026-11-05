import type { MapSummary } from '../../types/api'

interface Domain { id: number; name: string }

function MapButton({ map, selectedId, onSelect }: { map: MapSummary; selectedId: number | null; onSelect: (id: number) => void }) {
  return <button type="button" className={`map-explorer-map ${selectedId === map.id ? 'active' : ''}`}
    onClick={() => onSelect(map.id)} title={map.name}>
    <span aria-hidden="true">▧</span><span>{map.name}</span>
  </button>
}

export default function MapExplorer({ maps, domains, selectedId, activeDomainId, onSelect, onSelectDomain }: {
  maps: MapSummary[]; domains: Domain[]; selectedId: number | null; activeDomainId: number | null
  onSelect: (id: number) => void; onSelectDomain: (id: number | null) => void
}) {
  const unassigned = maps.filter(map => map.domain_ids.length === 0)
  return (
    <section className="map-explorer" aria-label="Explorador de mapas">
      <div className="map-explorer-heading">
        <div><strong>Explorador de mapas</strong><p>Selecciona un dominio para ver todos sus mapas juntos, o abre un mapa individual.</p></div>
        <span>{maps.length} mapas</span>
      </div>
      <div className="map-explorer-tree">
        {domains.map(domain => {
          const domainMaps = maps.filter(map => map.domain_ids.includes(domain.id))
          return <section className={`map-explorer-domain ${activeDomainId === domain.id ? 'active' : ''}`} key={domain.id}>
            <button type="button" className="map-explorer-domain-select" onClick={() => onSelectDomain(domain.id)}>
              <span className="map-tree-icon">▰</span><b>{domain.name}</b><small>{domainMaps.length} mapas</small>
            </button>
            {activeDomainId === domain.id && <div className="map-explorer-maps">
              {domainMaps.length ? domainMaps.map(map => <MapButton key={map.id} map={map} selectedId={selectedId} onSelect={onSelect} />)
                : <span className="map-explorer-empty">Este dominio aún no tiene mapas</span>}
            </div>}
          </section>
        })}
        <section className={`map-explorer-domain ${activeDomainId === -1 ? 'active' : ''}`}>
          <button type="button" className="map-explorer-domain-select" onClick={() => onSelectDomain(null)}>
            <span className="map-tree-icon">▱</span><b>Sin clasificar</b><small>{unassigned.length} mapas</small>
          </button>
          {activeDomainId === -1 && <div className="map-explorer-maps">
            {unassigned.length ? unassigned.map(map => <MapButton key={map.id} map={map} selectedId={selectedId} onSelect={onSelect} />)
              : <span className="map-explorer-empty">No hay mapas sin dominio</span>}
          </div>}
        </section>
        {maps.length === 0 && <p className="map-explorer-empty">Crea un mapa manual o descubre una red para comenzar.</p>}
      </div>
    </section>
  )
}
