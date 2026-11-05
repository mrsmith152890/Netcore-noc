import { useEffect, useState } from 'react'
import { apiGet, apiSend } from '../../services/api'

type DeviceConfig = {
  id: number
  site_id: number
  name: string
  ip_address: string
  device_type: 'router' | 'switch' | 'firewall' | 'server' | 'ap' | 'other'
  vendor: string | null
  model: string | null
  enabled: boolean
  wan_gateway_ip: string | null
  wan_probe_ip: string | null
}

type SnmpConfig = {
  device_id: number
  version: string
  port: number
  enabled: boolean
  has_community: boolean
}

const deviceTypes = [
  ['router', 'Router'],
  ['switch', 'Switch'],
  ['firewall', 'Firewall'],
  ['server', 'Servidor'],
  ['ap', 'Punto de acceso'],
  ['other', 'Otro'],
] as const

export default function DeviceEditor({ deviceId }: { deviceId: number }) {
  const [device, setDevice] = useState<DeviceConfig | null>(null)
  const [community, setCommunity] = useState('')
  const [port, setPort] = useState(161)
  const [snmpEnabled, setSnmpEnabled] = useState(true)
  const [snmpConfigured, setSnmpConfigured] = useState(false)
  const [loading, setLoading] = useState(true)
  const [savingDevice, setSavingDevice] = useState(false)
  const [savingSnmp, setSavingSnmp] = useState(false)
  const [testing, setTesting] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [testResult, setTestResult] = useState('')

  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoading(true)
      setError('')
      setMessage('')
      setTestResult('')

      try {
        const d = await apiGet<DeviceConfig>(`/devices/${deviceId}`)
        if (cancelled) return
        setDevice(d)

        try {
          const s = await apiGet<SnmpConfig>(`/devices/${deviceId}/snmp`)
          if (cancelled) return
          setPort(s.port)
          setSnmpEnabled(s.enabled)
          setSnmpConfigured(true)
        } catch {
          if (cancelled) return
          setPort(161)
          setSnmpEnabled(true)
          setSnmpConfigured(false)
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void load()
    return () => { cancelled = true }
  }, [deviceId])

  async function saveDevice(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!device) return

    setSavingDevice(true)
    setError('')
    setMessage('')

    try {
      const updated = await apiSend<DeviceConfig>(
        'PATCH',
        `/devices/${deviceId}`,
        {
          site_id: device.site_id,
          name: device.name.trim(),
          ip_address: device.ip_address.trim(),
          device_type: device.device_type,
          vendor: device.vendor?.trim() || null,
          model: device.model?.trim() || null,
          wan_gateway_ip: ['router', 'firewall'].includes(device.device_type) ? device.wan_gateway_ip?.trim() || null : null,
          wan_probe_ip: ['router', 'firewall'].includes(device.device_type) ? device.wan_probe_ip?.trim() || null : null,
          enabled: device.enabled,
        },
      )
      setDevice(updated)
      setMessage('Datos del dispositivo guardados correctamente.')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSavingDevice(false)
    }
  }

  async function saveSnmp(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()

    if (!community.trim()) {
      setError('Escribe la comunidad SNMP. Por seguridad no se muestra la comunidad almacenada.')
      return
    }

    setSavingSnmp(true)
    setError('')
    setMessage('')
    setTestResult('')

    try {
      await apiSend<SnmpConfig>('PUT', `/devices/${deviceId}/snmp`, {
        community: community.trim(),
        port,
        enabled: snmpEnabled,
      })
      setCommunity('')
      setSnmpConfigured(true)
      setMessage('Configuración SNMP guardada. La comunidad se ha enviado al backend para su almacenamiento cifrado.')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSavingSnmp(false)
    }
  }

  async function testSnmp() {
    setTesting(true)
    setError('')
    setMessage('')
    setTestResult('')

    try {
      const result = await apiSend<Record<string, unknown>>(
        'POST',
        `/devices/${deviceId}/snmp/test`,
      )
      setTestResult(JSON.stringify(result, null, 2))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setTesting(false)
    }
  }

  if (loading) return <section className="panel"><p>Cargando configuración…</p></section>
  if (!device) return <section className="panel"><p className="error">{error || 'No se pudo cargar el dispositivo.'}</p></section>

  return (
    <section className="panel">
      <h2>Administrar dispositivo</h2>

      <form onSubmit={saveDevice}>
        <h3>Datos generales</h3>

        <label>
          Nombre
          <input
            required
            maxLength={100}
            value={device.name}
            onChange={e => setDevice({ ...device, name: e.target.value })}
          />
        </label>

        <label>
          Dirección IP
          <input
            required
            maxLength={45}
            value={device.ip_address}
            onChange={e => setDevice({ ...device, ip_address: e.target.value })}
          />
        </label>

        <label>
          Tipo de dispositivo
          <select
            value={device.device_type}
            onChange={e => setDevice({
              ...device,
              device_type: e.target.value as DeviceConfig['device_type'],
            })}
          >
            {deviceTypes.map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </label>

        <label>
          Fabricante
          <input
            maxLength={50}
            value={device.vendor ?? ''}
            onChange={e => setDevice({ ...device, vendor: e.target.value })}
          />
        </label>

        <label>
          Modelo
          <input
            maxLength={80}
            value={device.model ?? ''}
            onChange={e => setDevice({ ...device, model: e.target.value })}
          />
        </label>

        {['router', 'firewall'].includes(device.device_type) && (
          <>
            <h3 className="wan-config-heading">Comprobaciones WAN opcionales (router o firewall)</h3>
            <p className="muted wan-config-help">
              NetCore probará estas direcciones desde el servidor NOC. Deja la IP externa vacía si la WAN usa DHCP
              y no tienes un destino estable. El destino externo es una referencia de conectividad, no la IP pública del router.
            </p>
            <label>
              Gateway WAN
              <input
                inputMode="decimal"
                placeholder="Ejemplo: 192.0.2.1"
                value={device.wan_gateway_ip ?? ''}
                onChange={e => setDevice({ ...device, wan_gateway_ip: e.target.value })}
              />
            </label>
            <label>
              IP externa de prueba
              <input
                inputMode="decimal"
                placeholder="Ejemplo: 1.1.1.1"
                value={device.wan_probe_ip ?? ''}
                onChange={e => setDevice({ ...device, wan_probe_ip: e.target.value })}
              />
            </label>
          </>
        )}

        <label>
          <input
            type="checkbox"
            checked={device.enabled}
            onChange={e => setDevice({ ...device, enabled: e.target.checked })}
          />
          Dispositivo habilitado
        </label>

        <button type="submit" disabled={savingDevice}>
          {savingDevice ? 'Guardando…' : 'Guardar datos'}
        </button>
      </form>

      <hr />

      <form onSubmit={saveSnmp}>
        <h3>Configuración SNMP v2c</h3>
        <p className="muted">
          La comunidad almacenada nunca se muestra. Para cambiarla, introduce una nueva.
        </p>

        <label>
          Comunidad SNMP
          <input
            type="password"
            autoComplete="new-password"
            maxLength={128}
            value={community}
            onChange={e => setCommunity(e.target.value)}
            placeholder={snmpConfigured ? 'Configurada; introduce para cambiarla' : 'Introduce la comunidad'}
          />
        </label>

        <label>
          Puerto UDP
          <input
            type="number"
            required
            min={1}
            max={65535}
            value={port}
            onChange={e => setPort(Number(e.target.value))}
          />
        </label>

        <label>
          <input
            type="checkbox"
            checked={snmpEnabled}
            onChange={e => setSnmpEnabled(e.target.checked)}
          />
          Habilitar consultas SNMP
        </label>

        <button type="submit" disabled={savingSnmp}>
          {savingSnmp ? 'Guardando…' : 'Guardar SNMP'}
        </button>

        <button type="button" onClick={() => void testSnmp()} disabled={testing || !snmpConfigured || !snmpEnabled}>
          {testing ? 'Probando…' : 'Probar SNMP'}
        </button>
      </form>

      {message && <p>{message}</p>}
      {error && <p className="error">{error}</p>}
      {testResult && (
        <>
          <h3>Respuesta de la prueba SNMP</h3>
          <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{testResult}</pre>
        </>
      )}
    </section>
  )
}
