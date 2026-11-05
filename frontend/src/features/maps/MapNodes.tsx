import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'

export type NodeState = 'UP' | 'SNMP' | 'DOWN' | 'UNKNOWN' | 'DISABLED'

export type DeviceNodeData = {
  name: string
  label: string | null
  iconData: string | null
  ip: string
  deviceType: string
  deviceId: number
  enabled: boolean
  state: NodeState
  rtt: number | null
  snmpOk: boolean
  snmpCheckedAt: string | null
  lastPingOk: boolean | null
  lastSnmpOk: boolean | null
  lastCheckedAt: string | null
}
export type LabelNodeData = { text: string }
export type IpNodeData = {
  label: string
  ip: string
  source: string
  state: NodeState
  lastPingOk: boolean | null
  lastSnmpOk: boolean | null
  lastArpSeen: boolean | null
  lastCheckedAt: string | null
  iconData: string | null
}
export type SubmapNodeData = {
  name: string
  mapId: number
  deviceIds: number[]
  state: NodeState
  up: number
  down: number
  total: number
}

export type DeviceFlowNode = Node<DeviceNodeData, 'device'>
export type LabelFlowNode = Node<LabelNodeData, 'label'>
export type IpFlowNode = Node<IpNodeData, 'ip'>
export type SubmapFlowNode = Node<SubmapNodeData, 'submap'>
export type FlowNode = DeviceFlowNode | LabelFlowNode | IpFlowNode | SubmapFlowNode

const ICONS: Record<string, string> = {
  router: '🌐',
  switch: '🔀',
  firewall: '🧱',
  server: '🖥️',
  ap: '📡',
  other: '▫️',
}

function stateLabel(state: NodeState): string {
  if (state === 'SNMP') return 'SNMP responde'
  if (state === 'UP') return 'Ping responde'
  if (state === 'DOWN') return 'Caído'
  if (state === 'DISABLED') return 'Deshabilitado'
  return 'Sin confirmar'
}

const HANDLES = [
  { id: 't', position: Position.Top },
  { id: 'r', position: Position.Right },
  { id: 'b', position: Position.Bottom },
  { id: 'l', position: Position.Left },
]

function Handles() {
  return (
    <>
      {HANDLES.map(h => (
        <Handle key={h.id} id={h.id} type="source" position={h.position} />
      ))}
    </>
  )
}

function DeviceNode({ data, selected }: NodeProps<DeviceFlowNode>) {
  return (
    <div className={'map-node ' + data.state + (selected ? ' selected' : '')}>
      <Handles />
      <div className="icon">{data.iconData ? <img src={data.iconData} alt="" /> : (ICONS[data.deviceType] ?? ICONS.other)}</div>
      <div className="info">
        <strong>{data.label?.trim() || data.name}</strong>
        <span>{data.ip}</span>
        <span className="state">
          {stateLabel(data.state)}
          {data.state === 'UP' && data.rtt != null ? ' · ' + data.rtt.toFixed(0) + ' ms' : ''}
        </span>
      </div>
    </div>
  )
}

function SubmapNode({ data, selected }: NodeProps<SubmapFlowNode>) {
  return (
    <div className={`map-node submap ${data.state}${selected ? ' selected' : ''}`} title="Abrir submapa">
      <Handles />
      <div className="icon">🗂️</div>
      <div className="info">
        <strong>{data.name}</strong>
        <span>{data.total} dispositivos</span>
        <span className="state">
          {data.down > 0 ? `${data.down} caídos` : data.state === 'UP' ? 'Todo en línea' : 'Sin datos'}
        </span>
      </div>
    </div>
  )
}

function IpNode({ data, selected }: NodeProps<IpFlowNode>) {
  const source = data.source === 'manual' ? 'Manual' : 'Detectado: ' + data.source.toUpperCase()
  return (
    <div className={'map-node ' + data.state + (selected ? ' selected' : '')}>
      <Handles />
      <div className="icon">{data.iconData ? <img src={data.iconData} alt="" /> : '🔌'}</div>
      <div className="info">
        <strong>{data.label || 'Equipo IP'}</strong>
        <span>{data.ip}</span>
        <span className="state">{stateLabel(data.state)} · {source}</span>
      </div>
    </div>
  )
}

function LabelNode({ data, selected }: NodeProps<LabelFlowNode>) {
  return <div className={'map-label' + (selected ? ' selected' : '')}>{data.text}</div>
}

export const nodeTypes = { device: DeviceNode, submap: SubmapNode, label: LabelNode, ip: IpNode }
