import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiGet, apiSend } from '../../services/api'
import type { SiteInfo } from '../../types/api'

interface SiteDeviceRef { id: number; site_id: number; enabled: boolean }
type SiteRow = SiteInfo & { deviceCount: number }

const message = (error: unknown) => error instanceof Error ? error.message : String(error)

export default function SitesView() {
  const [sites, setSites] = useState<SiteInfo[]>([])
  const [devices, setDevices] = useState<SiteDeviceRef[]>([])
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [creating, setCreating] = useState(false)
  const [deleteSiteId, setDeleteSiteId] = useState<number | null>(null)
  const [deleteTargetId, setDeleteTargetId] = useState('')

  const load = useCallback(async () => {
    try {
      const [siteRows, deviceRows] = await Promise.all([
        apiGet<SiteInfo[]>('/sites?include_disabled=true'),
        apiGet<SiteDeviceRef[]>('/devices?include_disabled=true'),
      ])
      setSites(siteRows)
      setDevices(deviceRows)
      setError(null)
    } catch (e) { setError(message(e)) }
  }, [])

  useEffect(() => { void load() }, [load])

  const rows = useMemo<SiteRow[]>(() => sites.map(site => ({
    ...site,
    deviceCount: site.device_count ?? devices.filter(device => device.site_id === site.id).length,
  })), [sites, devices])
  const siteToDelete = rows.find(site => site.id === deleteSiteId)
  const deleteNeedsTransfer = !!siteToDelete && !!(siteToDelete.device_count + siteToDelete.scope_count + siteToDelete.rule_count + siteToDelete.silence_count)

  async function createSite() {
    if (!name.trim()) return
    setCreating(true)
    try {
      await apiSend('POST', '/sites', { name: name.trim(), description: description.trim() || null })
      setName('')
      setDescription('')
      await load()
    } catch (e) { setError(message(e)) }
    finally { setCreating(false) }
  }

  async function renameSite(site: SiteInfo) {
    const value = window.prompt('Nuevo nombre para la sede', site.name)
    if (!value?.trim() || value.trim() === site.name) return
    setBusyId(site.id)
    try {
      await apiSend('PATCH', '/sites/' + site.id, { name: value.trim() })
      await load()
    } catch (e) { setError(message(e)) }
    finally { setBusyId(null) }
  }

  async function toggleSite(site: SiteInfo) {
    setBusyId(site.id)
    try {
      await apiSend('PATCH', '/sites/' + site.id, { enabled: !site.enabled })
      await load()
    } catch (e) { setError(message(e)) }
    finally { setBusyId(null) }
  }

  async function confirmDeleteSite() {
    if (!siteToDelete) return
    if (deleteNeedsTransfer && !deleteTargetId) return
    setBusyId(siteToDelete.id)
    try {
      await apiSend('DELETE', '/sites/' + siteToDelete.id, {
        target_site_id: deleteTargetId ? Number(deleteTargetId) : null,
      })
      setDeleteSiteId(null)
      setDeleteTargetId('')
      await load()
    } catch (e) { setError(message(e)) }
    finally { setBusyId(null) }
  }

  return (
    <main className="sites-page">
      <section className="sites-hero">
        <div className="sites-hero-icon" aria-hidden="true">⌖</div>
        <div><span className="panel-index">INVENTARIO · UBICACIONES</span><h2>Administración de sedes</h2>
          <p>Crea y organiza ubicaciones. Deshabilitar una sede pausa su operación sin borrar sus datos.</p></div>
        <div className="sites-summary"><b>{sites.length}<small>sedes</small></b><b>{sites.filter(site => site.enabled).length}<small>activas</small></b></div>
      </section>

      {error && <div className="error sites-error" role="alert">{error}<button type="button" onClick={() => setError(null)}>Cerrar</button></div>}

      <section className="panel sites-create-card">
        <div className="sites-section-heading"><span>＋</span><div><h3>Nueva sede</h3><p>Asigna un nombre claro para identificar sus dispositivos y rangos.</p></div></div>
        <div className="sites-create-form">
          <label>Nombre<input value={name} maxLength={100} placeholder="Ej.: Centro comercial norte"
            onChange={event => setName(event.target.value)} /></label>
          <label>Descripción <small>opcional</small><input value={description} maxLength={255} placeholder="Ciudad, ubicación o referencia"
            onChange={event => setDescription(event.target.value)} /></label>
          <button type="button" onClick={() => void createSite()} disabled={!name.trim() || creating}>
            {creating ? 'Creando…' : 'Crear sede'}
          </button>
        </div>
      </section>

      <section className="panel sites-list-card">
        <div className="sites-section-heading"><span>⌖</span><div><h3>Sedes registradas</h3><p>Renombra, pausa, reactiva o elimina las ubicaciones.</p></div></div>
        {!rows.length ? <div className="sites-empty"><b>Aún no hay sedes</b><span>Crea una sede para organizar tus dispositivos.</span></div> :
          <div className="sites-list">
            {rows.map(site => <article className={'site-admin-row' + (!site.enabled ? ' disabled' : '')} key={site.id}>
              <span className={'site-admin-indicator ' + (site.enabled ? 'enabled' : 'disabled')} />
              <div className="site-admin-copy"><strong>{site.name}</strong>
                <span>{site.description || 'Sin descripción'}</span></div>
              <span className="site-device-count"><b>{site.device_count}</b> dispositivos · {site.scope_count} rangos</span>
              <span className={'site-enabled-badge ' + (site.enabled ? 'enabled' : 'disabled')}>{site.enabled ? 'Activa' : 'Pausada'}</span>
              <div className="site-admin-actions">
                <button type="button" onClick={() => void renameSite(site)} disabled={busyId === site.id}>Renombrar</button>
                <button type="button" onClick={() => void toggleSite(site)} disabled={busyId === site.id}>
                  {site.enabled ? 'Deshabilitar' : 'Reactivar'}
                </button>
                <button type="button" className="danger" onClick={() => { setDeleteSiteId(site.id); setDeleteTargetId('') }} disabled={busyId === site.id}>Eliminar</button>
              </div>
            </article>)}
          </div>}
      </section>

      {siteToDelete && <div className="site-delete-backdrop" role="presentation" onMouseDown={event => {
        if (event.target === event.currentTarget && busyId !== siteToDelete.id) setDeleteSiteId(null)
      }}>
        <section className="site-delete-dialog" role="dialog" aria-modal="true" aria-labelledby="site-delete-title">
          <div className="site-delete-mark" aria-hidden="true">!</div>
          <h3 id="site-delete-title">Eliminar sede</h3>
          <p>Vas a eliminar <strong>{siteToDelete.name}</strong>. Las configuraciones y dispositivos asociados se trasladarán completos a otra sede para conservar su historial.</p>
          {deleteNeedsTransfer ? <>
            <div className="site-transfer-summary">
              <span>{siteToDelete.device_count} dispositivos</span><span>{siteToDelete.scope_count} rangos</span>
              <span>{siteToDelete.rule_count} reglas</span><span>{siteToDelete.silence_count} silencios</span>
            </div>
            <label>Sede destino
              <select value={deleteTargetId} onChange={event => setDeleteTargetId(event.target.value)}>
                <option value="">Selecciona una sede activa…</option>
                {sites.filter(site => site.id !== siteToDelete.id && site.enabled).map(site =>
                  <option value={site.id} key={site.id}>{site.name}</option>)}
              </select>
            </label>
            <small>Si hay una IP o un rango duplicado en el destino, el traslado se cancela completo y podrás elegir otra sede.</small>
          </> : <p className="site-delete-safe">Esta sede no tiene dispositivos ni configuraciones asociadas.</p>}
          {error && <p className="error">{error}</p>}
          <div className="site-delete-actions">
            <button type="button" onClick={() => { setDeleteSiteId(null); setError(null) }} disabled={busyId === siteToDelete.id}>Cancelar</button>
            <button type="button" className="danger" onClick={() => void confirmDeleteSite()}
              disabled={(deleteNeedsTransfer && !deleteTargetId) || busyId === siteToDelete.id}>
              {busyId === siteToDelete.id ? 'Procesando…' : deleteNeedsTransfer ? 'Trasladar y eliminar' : 'Eliminar sede'}
            </button>
          </div>
        </section>
      </div>}
    </main>
  )
}
