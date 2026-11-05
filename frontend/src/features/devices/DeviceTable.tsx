import { useMemo, useState } from 'react'
import { fmtAgo } from '../../services/format'
import type { DeviceStatus } from '../../types/api'

interface Props {
  devices: DeviceStatus[]
  selectedId: number | null
  onSelect: (id: number) => void
  canDelete?: boolean
  onDelete?: (id: number) => void
}

export default function DeviceTable({ devices, selectedId, onSelect, canDelete = false, onDelete = () => undefined }: Props) {
  const [query, setQuery] = useState('')
  const filtered = useMemo(() => {
    const value = query.trim().toLocaleLowerCase()
    if (!value) return devices
    return devices.filter(device =>
      device.name.toLocaleLowerCase().includes(value) ||
      device.ip_address.toLocaleLowerCase().includes(value) ||
      device.device_type.toLocaleLowerCase().includes(value) ||
      device.state.toLocaleLowerCase().includes(value))
  }, [devices, query])

  return (
    <>
      <div className="device-search">
        <label htmlFor="device-search-input">Buscar dispositivo</label>
        <div className="device-search-control">
          <span aria-hidden="true">⌕</span>
          <input id="device-search-input" type="search" value={query}
            onChange={event => setQuery(event.target.value)}
            placeholder="Nombre, dirección IP o estado…" />
          {query && <button type="button" onClick={() => setQuery('')} aria-label="Limpiar búsqueda">×</button>}
        </div>
        <span className="device-search-count">{filtered.length} de {devices.length}</span>
      </div>
      {filtered.length === 0 ? (
        <p className="muted device-search-empty">{devices.length ? 'No hay dispositivos que coincidan con la búsqueda.' : 'No hay dispositivos activos.'}</p>
      ) : (
        <table className="grid">
          <thead>
            <tr>
              <th>Estado</th><th>Dispositivo</th><th>IP</th><th>Latencia</th><th>Último cambio</th>
              {canDelete && <th>Acciones</th>}
            </tr>
          </thead>
          <tbody>
            {filtered.map(d => (
              <tr key={d.device_id} className={d.device_id === selectedId ? 'selected' : ''} onClick={() => onSelect(d.device_id)}>
                <td><span className={`badge ${d.state}`}>{d.state}</span></td>
                <td>{d.name}</td><td>{d.ip_address}</td>
                <td>{d.last_rtt_ms != null ? `${d.last_rtt_ms.toFixed(1)} ms` : '—'}</td>
                <td>{fmtAgo(d.last_change_at)}</td>
                {canDelete && <td><button className="btn danger" aria-label={'Eliminar ' + d.name}
                  onClick={e => { e.stopPropagation(); onDelete(d.device_id) }}>Eliminar</button></td>}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}
