import '@xyflow/react/dist/style.css'
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Background,
  ConnectionMode,
  Controls,
  MiniMap,
  ReactFlow,
  applyEdgeChanges,
  applyNodeChanges,
  type Connection,
  type Edge,
  type EdgeChange,
  type NodeChange,
} from '@xyflow/react'
import { apiGet, apiSend } from '../../services/api'
import type { DeviceStatus, MapDetail, MapLinkOut, MapNodeOut, MapSummary } from '../../types/api'
import { nodeTypes, type FlowNode, type NodeState } from './MapNodes'

interface IdentityDraft { nodeId: string; label: string; iconData: string | null }

interface NodeProbeResult {
  node_id: number
  ip_address: string
  ping_ok: boolean
  rtt_ms: number | null
  snmp_checked: boolean
  snmp_ok: boolean | null
  state: NodeState
  checked_at: string
}

function toFlowNode(n: MapNodeOut): FlowNode {
  const id = String(n.id)
  const position = { x: n.x, y: n.y }
  if (n.node_type === 'label') {
    return { id, type: 'label', position, data: { text: n.label ?? '' } }
  }
  if (n.node_type === 'ip') {
    return {
      id, type: 'ip', position,
      data: {
        label: n.label ?? '', ip: n.ip_address ?? '', source: n.discovery_source ?? 'manual',
        iconData: n.icon_data ?? null, state: 'UNKNOWN', lastPingOk: n.last_ping_ok, lastSnmpOk: n.last_snmp_ok,
        lastArpSeen: n.last_arp_seen, lastCheckedAt: n.last_checked_at,
      },
    }
  }
  if (n.node_type === 'map') {
    return {
      id, type: 'submap', position,
      data: {
        name: n.child_map_name ?? '?', mapId: n.child_map_id ?? 0, deviceIds: n.child_device_ids ?? [],
        state: 'UNKNOWN', up: 0, down: 0, total: 0,
      },
    }
  }
  return {
    id, type: 'device', position,
    data: {
      name: n.device_name ?? '?', label: n.label, iconData: n.icon_data ?? null,
      ip: n.device_ip ?? '', deviceType: n.device_type ?? 'other',
      deviceId: n.device_id ?? 0, enabled: n.device_enabled ?? true, state: 'UNKNOWN', rtt: null,
      snmpOk: n.device_snmp_ok, snmpCheckedAt: n.device_snmp_checked_at,
      lastPingOk: n.last_ping_ok, lastSnmpOk: n.last_snmp_ok, lastCheckedAt: n.last_checked_at,
    },
  }
}

function toEdge(l: MapLinkOut): Edge {
  return {
    id: `l${l.id}`,
    source: String(l.source_node_id),
    target: String(l.target_node_id),
    sourceHandle: l.source_handle,
    targetHandle: l.target_handle,
    label: l.label ?? undefined,
    type: 'straight',
  }
}

function linkColor(a?: NodeState, b?: NodeState): string {
  const s = [a, b]
  if (s.includes('DOWN')) return '#ef4444'
  if (s.includes('SNMP')) return '#3b82f6'
  if (s.includes('UNKNOWN') || s.includes('DISABLED')) return '#6b7280'
  return '#22c55e'
}

/** Estado agregado de un submapa: DOWN si alguno está caído; UP si hay alguno en línea; si no, UNKNOWN. */
function aggregate(ids: number[], statusMap: Map<number, DeviceStatus>) {
  let up = 0, down = 0, total = 0
  for (const id of ids) {
    const s = statusMap.get(id)
    if (!s) continue
    total++
    if (s.state === 'UP') up++
    else if (s.state === 'DOWN') down++
  }
  const state: NodeState = down > 0 ? 'DOWN' : up > 0 ? 'UP' : 'UNKNOWN'
  return { state, up, down, total }
}

interface Props {
  mapId: number
  statuses: DeviceStatus[]
  maps: MapSummary[]
  onOpenMap: (id: number) => void
}

export default function MapCanvas({ mapId, statuses, maps, onOpenMap }: Props) {
  const [nodes, setNodes] = useState<FlowNode[]>([])
  const [edges, setEdges] = useState<Edge[]>([])
  const [editing, setEditing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [probeMessage, setProbeMessage] = useState<string | null>(null)
  const [identityDraft, setIdentityDraft] = useState<IdentityDraft | null>(null)
  const [savingIdentity, setSavingIdentity] = useState(false)

  const reload = useCallback(async () => {
    try {
      const d = await apiGet<MapDetail>(`/maps/${mapId}`)
      setNodes(d.nodes.map(toFlowNode))
      setEdges(d.links.map(toEdge))
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [mapId])

  useEffect(() => {
    void reload()
  }, [reload])

  // Si otra persona edita el mapa (o cambia un submapa), se refleja sin recargar la página.
  useEffect(() => {
    if (editing) return
    const id = setInterval(() => void reload(), 60000)
    return () => clearInterval(id)
  }, [editing, reload])

  const statusMap = useMemo(() => new Map(statuses.map(s => [s.device_id, s])), [statuses])

  const displayNodes = useMemo<FlowNode[]>(
    () =>
      nodes.map(n => {
        if (n.type === 'device') {
          const s = statusMap.get(n.data.deviceId)
          const pingCheck = s?.last_check_at ? Date.parse(s.last_check_at) : 0
          const snmpCheck = n.data.snmpCheckedAt ? Date.parse(n.data.snmpCheckedAt) : 0
          const manualCheck = n.data.lastCheckedAt ? Date.parse(n.data.lastCheckedAt) : 0
          let state: NodeState
          if (n.data.lastSnmpOk === true && manualCheck > snmpCheck) {
            state = 'SNMP'
          } else if (n.data.snmpOk) {
            state = 'SNMP'
          } else if (manualCheck > pingCheck) {
            state = n.data.lastPingOk ? 'UP' : 'DOWN'
          } else if (s) {
            state = s.state === 'UP' ? 'UP' : s.state === 'DOWN' ? 'DOWN' : 'UNKNOWN'
          } else {
            state = n.data.enabled ? 'UNKNOWN' : 'DISABLED'
          }
          return { ...n, data: { ...n.data, state, rtt: s?.last_rtt_ms ?? null } }
        }
        if (n.type === 'ip') {
          let state: NodeState = 'UNKNOWN'
          if (n.data.lastSnmpOk === true) state = 'SNMP'
          else if (n.data.lastPingOk === true) state = 'UP'
          else if (n.data.lastPingOk === false && n.data.lastArpSeen !== true && n.data.lastCheckedAt) state = 'DOWN'
          return { ...n, data: { ...n.data, state } }
        }
        if (n.type === 'submap') {
          return { ...n, data: { ...n.data, ...aggregate(n.data.deviceIds, statusMap) } }
        }
        return n
      }),
    [nodes, statusMap],
  )

  const selectedNode = displayNodes.find(n => n.id === selectedNodeId)
  const canPingSelected = selectedNode?.type === 'device' || selectedNode?.type === 'ip'
  const canEditIdentity = selectedNode?.type === 'device' || selectedNode?.type === 'ip'

  function openIdentityEditor() {
    if (!selectedNode || (selectedNode.type !== 'device' && selectedNode.type !== 'ip')) return
    setIdentityDraft({
      nodeId: selectedNode.id,
      label: selectedNode.type === 'device' ? (selectedNode.data.label ?? selectedNode.data.name) : selectedNode.data.label,
      iconData: selectedNode.data.iconData ?? null,
    })
  }

  async function pingSelectedNode() {
    if (!selectedNode || !canPingSelected) return
    try {
      const result = await apiSend<NodeProbeResult>(
        'POST', '/maps/' + mapId + '/nodes/' + selectedNode.id + '/ping',
      )
      await reload()
      const pingText = result.ping_ok
        ? 'ping responde' + (result.rtt_ms != null ? ' (' + result.rtt_ms.toFixed(1) + ' ms)' : '')
        : 'sin respuesta ping'
      const snmpText = result.snmp_ok === true ? ' · SNMP responde'
        : result.snmp_checked ? ' · sin respuesta SNMP' : ' · SNMP no configurado'
      setProbeMessage(result.ip_address + ': ' + pingText + snmpText)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const displayEdges = useMemo<Edge[]>(() => {
    const stateById = new Map<string, NodeState>()
    for (const n of displayNodes) {
      if (n.type === 'device' || n.type === 'submap' || n.type === 'ip') stateById.set(n.id, n.data.state)
    }
    return edges.map(e => ({
      ...e,
      style: { stroke: linkColor(stateById.get(e.source), stateById.get(e.target)), strokeWidth: 2.5 },
    }))
  }, [edges, displayNodes])

  const { onMap, usedMaps } = useMemo(() => {
    const devs = new Set<number>()
    const subs = new Set<number>()
    for (const n of nodes) {
      if (n.type === 'device') devs.add(n.data.deviceId)
      if (n.type === 'submap') subs.add(n.data.mapId)
    }
    return { onMap: devs, usedMaps: subs }
  }, [nodes])
  const availableDevices = statuses.filter(d => !onMap.has(d.device_id))
  const availableMaps = maps.filter(m => m.id !== mapId && !usedMaps.has(m.id))

  const onNodesChange = useCallback(
    (changes: NodeChange<FlowNode>[]) => setNodes(ns => applyNodeChanges(changes, ns)),
    [],
  )
  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => setEdges(es => applyEdgeChanges(changes, es)),
    [],
  )

  async function saveIdentity() {
    if (!identityDraft) return
    setSavingIdentity(true)
    try {
      await apiSend('PATCH', '/maps/' + mapId + '/nodes/' + identityDraft.nodeId, {
        label: identityDraft.label.trim() || null,
        icon_data: identityDraft.iconData,
      })
      await reload()
      setIdentityDraft(null)
      setProbeMessage('Identidad e imagen guardadas correctamente.')
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSavingIdentity(false)
    }
  }

  function selectIcon(file: File | undefined) {
    if (!file || !identityDraft) return
    const extension = file.name.toLowerCase().split('.').pop()
    const mimeByExtension: Record<string, string> = {
      png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg',
      webp: 'image/webp', svg: 'image/svg+xml',
    }
    const mime = file.type === 'image/jpg' ? 'image/jpeg'
      : ['image/png', 'image/jpeg', 'image/webp', 'image/svg+xml'].includes(file.type)
        ? file.type : mimeByExtension[extension ?? '']
    if (!mime) {
      setError('Selecciona una imagen PNG, JPEG, WebP o SVG.')
      return
    }
    if (file.size > 512 * 1024) {
      setError('La imagen no puede superar 512 KB.')
      return
    }
    const reader = new FileReader()
    reader.onload = () => {
      if (typeof reader.result === 'string') {
        const base64 = reader.result.slice(reader.result.indexOf(',') + 1)
        setIdentityDraft(current => current ? { ...current, iconData: 'data:' + mime + ';base64,' + base64 } : current)
        setError(null)
      }
    }
    reader.onerror = () => setError('No se pudo leer la imagen seleccionada.')
    reader.readAsDataURL(file)
  }

  async function run(action: () => Promise<unknown>) {
    try {
      await action()
      await reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const spot = () => {
    const k = nodes.length % 8
    return { x: 80 + k * 40, y: 80 + k * 40 }
  }

  async function autoConnect() {
    try {
      const result = await apiSend<{ anchor_node_id: number; created: number }>(
        'POST', '/maps/' + mapId + '/auto-connect',
      )
      await reload()
      setProbeMessage('Conexión automática: ' + result.created + ' enlace(s) creados')
      setError(null)
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
  }

  const addDevice = (deviceId: number) =>
    run(() => apiSend('POST', `/maps/${mapId}/nodes`, { device_id: deviceId, ...spot() }))

  const addSubmap = (childId: number) =>
    run(() => apiSend('POST', `/maps/${mapId}/nodes`, { child_map_id: childId, ...spot() }))

  const addLabel = () => {
    const text = window.prompt('Texto de la etiqueta')
    if (!text?.trim()) return
    void run(() => apiSend('POST', `/maps/${mapId}/nodes`, { label: text.trim(), ...spot() }))
  }

  const addIp = () => {
    const ip = window.prompt('Dirección IP (IPv4 o IPv6)')
    if (!ip?.trim()) return
    const label = window.prompt('Nombre opcional para este nodo', '')
    void run(() => apiSend('POST', '/maps/' + mapId + '/nodes', {
      ip_address: ip.trim(),
      ...(label?.trim() ? { label: label.trim() } : {}),
      ...spot(),
    }))
  }

  const onConnect = (c: Connection) => {
    if (!c.source || !c.target) return
    void run(() =>
      apiSend('POST', `/maps/${mapId}/links`, {
        source_node_id: Number(c.source),
        target_node_id: Number(c.target),
        source_handle: c.sourceHandle ?? null,
        target_handle: c.targetHandle ?? null,
      }),
    )
  }

  return (
    <div>
      <div className="map-toolbar">
        <button className={editing ? 'active' : ''} onClick={() => { setEditing(v => !v); setIdentityDraft(null) }}>
          {editing ? 'Terminar edición' : 'Editar mapa'}
        </button>
        <button onClick={() => void pingSelectedNode()} disabled={!canPingSelected}>
          Ping seleccionado
        </button>
        <button onClick={openIdentityEditor} disabled={!canEditIdentity}>
          Editar identidad
        </button>
        {probeMessage && <span className="muted">{probeMessage}</span>}
        <span className="muted">Verde: ping · Azul: SNMP · Rojo: sin respuesta</span>
        {editing && (
          <>
            <select value="" onChange={e => { const id = Number(e.target.value); if (id) void addDevice(id) }}>
              <option value="">Agregar dispositivo…</option>
              {availableDevices.map(d => (
                <option key={d.device_id} value={d.device_id}>{d.name} ({d.ip_address})</option>
              ))}
            </select>
            <select value="" onChange={e => { const id = Number(e.target.value); if (id) void addSubmap(id) }}>
              <option value="">Agregar submapa…</option>
              {availableMaps.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
            <button onClick={() => void autoConnect()}>Conectar desde router</button>
            <button onClick={addLabel}>Agregar etiqueta</button>
            <button onClick={addIp}>Agregar IP manual</button>
            <span className="muted">
              Arrastra entre nodos para enlazar · usa «Editar identidad» para cambiar nombre e imagen · Supr elimina
              lo seleccionado (quitar un submapa no borra el mapa)
            </span>
          </>
        )}
        {error && <span className="error">{error}</span>}
      </div>
      {identityDraft && selectedNode && (selectedNode.type === 'device' || selectedNode.type === 'ip') && (
        <section className="node-identity-editor">
          <div className="node-identity-title">
            <div><span className="eyebrow">IDENTIDAD DEL NODO</span><strong>{selectedNode.type === 'device' ? selectedNode.data.ip : selectedNode.data.ip}</strong></div>
            {identityDraft.iconData && <img className="node-icon-preview" src={identityDraft.iconData} alt="Vista previa del icono" />}
          </div>
          <label>Nombre visible
            <input maxLength={200} value={identityDraft.label}
              onChange={e => setIdentityDraft({ ...identityDraft, label: e.target.value })}
              placeholder={selectedNode.type === 'device' ? selectedNode.data.name : selectedNode.data.ip} />
          </label>
          <label>Icono del equipo
            <input type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml"
              onChange={e => { selectIcon(e.currentTarget.files?.[0]); e.currentTarget.value = '' }} />
            <small>PNG, JPEG, WebP o SVG · máximo 512 KB</small>
          </label>
          {identityDraft.iconData && <button className="btn secondary" onClick={() => setIdentityDraft({ ...identityDraft, iconData: null })}>Quitar imagen</button>}
          <button className="btn" disabled={savingIdentity} onClick={() => void saveIdentity()}>{savingIdentity ? 'Guardando…' : 'Guardar identidad'}</button>
        </section>
      )}
      {nodes.length === 0 && !editing && (
        <p className="muted">Mapa vacío. Pulsa «Editar mapa» para agregar dispositivos o submapas.</p>
      )}
      <div className={`canvas${editing ? ' editing' : ''}`}>
        <ReactFlow
          nodes={displayNodes}
          edges={displayEdges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={(_e, node) => {
            setSelectedNodeId(node.id)
            setProbeMessage(null)
            if (editing && (node.type === 'device' || node.type === 'ip')) {
              setIdentityDraft({
                nodeId: node.id,
                label: node.type === 'device' ? (node.data.label ?? node.data.name) : node.data.label,
                iconData: node.data.iconData ?? null,
              })
            } else {
              setIdentityDraft(null)
            }
            if (!editing && node.type === 'submap') onOpenMap(node.data.mapId)
          }}
          onPaneClick={() => { setSelectedNodeId(null); setProbeMessage(null); setIdentityDraft(null) }}
          onNodeDragStop={(_e, _n, dragged) => {
            void apiSend('PUT', `/maps/${mapId}/layout`, {
              positions: dragged.map(d => ({ node_id: Number(d.id), x: d.position.x, y: d.position.y })),
            }).catch(err => setError(err instanceof Error ? err.message : String(err)))
          }}
          onNodesDelete={deleted =>
            void run(() =>
              Promise.all(deleted.map(n => apiSend('DELETE', `/maps/${mapId}/nodes/${n.id}`))),
            )
          }
          onEdgesDelete={deleted =>
            void run(() =>
              Promise.all(
                deleted.map(e =>
                  apiSend('DELETE', `/maps/${mapId}/links/${e.id.slice(1)}`).catch(() => undefined),
                ),
              ),
            )
          }
          onNodeDoubleClick={(_e, node) => {
            if (node.type === 'submap') {
              onOpenMap(node.data.mapId)
              return
            }
            if (!editing) return
            if (node.type === 'label') {
              const text = window.prompt('Texto de la etiqueta', node.data.text)
              if (!text?.trim()) return
              void run(() => apiSend('PATCH', '/maps/' + mapId + '/nodes/' + node.id, { label: text.trim() }))
            } else if (node.type === 'ip' || node.type === 'device') {
              setSelectedNodeId(node.id)
              setIdentityDraft({
                nodeId: node.id,
                label: node.type === 'device' ? (node.data.label ?? node.data.name) : node.data.label,
                iconData: node.data.iconData ?? null,
              })
            }
          }}
          nodesDraggable={editing}
          nodesConnectable={editing}
          elementsSelectable={true}
          deleteKeyCode={editing ? ['Backspace', 'Delete'] : null}
          connectionMode={ConnectionMode.Loose}
          colorMode="dark"
          minZoom={0.2}
          fitView
        >
          <Background />
          <Controls showInteractive={false} />
          <MiniMap pannable zoomable />
        </ReactFlow>
      </div>
    </div>
  )
}
