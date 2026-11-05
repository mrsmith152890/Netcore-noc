import { useState } from 'react'
import { apiSend } from '../../services/api'
import type { AppBranding } from '../../types/api'

type ImageKey = "logo_data" | "favicon_data" | "login_art_data"
const IMAGE_FIELDS: { key: ImageKey; title: string; description: string }[] = [
  { key: 'logo_data', title: 'Logo principal', description: 'Se muestra en la barra lateral, el encabezado y el acceso.' },
  { key: 'favicon_data', title: 'Icono de pestaña', description: 'Identifica NetCore NOC en la pestaña del navegador.' },
  { key: 'login_art_data', title: 'Fondo del panel de acceso', description: 'Ocupa solo el panel visual lateral; el formulario permanece separado.' },
]

function readImage(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const extension = file.name.toLowerCase().split('.').pop()
    const byExtension: Record<string, string> = {
      png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg',
      webp: 'image/webp', svg: 'image/svg+xml',
    }
    const mime = file.type === 'image/jpg' ? 'image/jpeg'
      : ['image/png', 'image/jpeg', 'image/webp', 'image/svg+xml'].includes(file.type)
        ? file.type : byExtension[extension ?? '']
    if (!mime) { reject(new Error('Usa una imagen PNG, JPEG, WebP o SVG.')); return }
    if (file.size > 5 * 1024 * 1024) { reject(new Error('La imagen no puede superar 5 MB.')); return }
    const reader = new FileReader()
    reader.onload = () => {
      if (typeof reader.result === 'string') {
        resolve('data:' + mime + ';base64,' + reader.result.slice(reader.result.indexOf(',') + 1))
      } else reject(new Error('No se pudo leer la imagen.'))
    }
    reader.onerror = () => reject(new Error('No se pudo leer la imagen.'))
    reader.readAsDataURL(file)
  })
}

export default function BrandingView({ branding, onChange }: {
  branding: AppBranding; onChange: (value: AppBranding) => void
}) {
  const [draft, setDraft] = useState<AppBranding>(branding)
  const [busyKey, setBusyKey] = useState<ImageKey | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState<string | null>(null)
  const [statusEnabled, setStatusEnabled] = useState(branding.login_status_enabled)
  const [savingStatus, setSavingStatus] = useState(false)

  function update(key: ImageKey, value: string | null) {
    setDraft(current => ({ ...current, [key]: value }))
    setSaved(null)
    setError(null)
  }

  async function save(key: ImageKey) {
    setBusyKey(key)
    setError(null)
    setSaved(null)
    try {
      const result = await apiSend<AppBranding>('PATCH', '/branding', { [key]: draft[key] })
      onChange(result)
      setDraft(current => ({ ...current, [key]: result[key] }))
      setSaved(key)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusyKey(null)
    }
  }

  async function toggleStatusPanel() {
    const next = !statusEnabled
    setSavingStatus(true)
    setError(null)
    try {
      const result = await apiSend<AppBranding>('PATCH', '/branding', { login_status_enabled: next })
      onChange(result)
      setStatusEnabled(result.login_status_enabled)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSavingStatus(false)
    }
  }

  return (
    <main className="branding-page">
      <section className="branding-hero">
        <div className="branding-hero-orbit" aria-hidden="true"><span/><i/><b/></div>
        <div><span className="panel-index">PERSONALIZACIÓN DE LA PLATAFORMA</span>
          <h2>Identidad visual</h2>
          <p>Actualiza el logo y el arte del acceso sin alterar el formulario de inicio de sesión.</p></div>
      </section>
      {error && <p className="error">{error}</p>}
      <section className="panel branding-status-setting">
        <div className="branding-status-setting-copy">
          <span className="branding-card-number">04</span>
          <div><h3>Resumen de red en el login</h3>
            <p>Muestra los equipos en línea y caídos, además de las alertas activas y críticas.</p>
            <small>Solo publica cantidades agregadas; nunca nombres de equipos ni direcciones IP.</small>
          </div>
        </div>
        <button type="button" className={'branding-status-toggle ' + (statusEnabled ? 'enabled' : 'disabled')}
          aria-pressed={statusEnabled} onClick={() => void toggleStatusPanel()} disabled={savingStatus}>
          <span className="branding-status-toggle-led" aria-hidden="true" />
          <span>{savingStatus ? 'Guardando…' : statusEnabled ? 'Desactivar panel en el login' : 'Activar panel en el login'}</span>
          <b>{statusEnabled ? 'ACTIVO' : 'INACTIVO'}</b>
        </button>
      </section>
      <div className="branding-grid">
        {IMAGE_FIELDS.map(field => (
          <section className={'panel branding-card ' + field.key} key={field.key}>
            <header><span className="branding-card-number">{field.key === 'logo_data' ? '01' : field.key === 'favicon_data' ? '02' : '03'}</span>
              <div><h3>{field.title}</h3><p>{field.description}</p></div></header>
            <div className={'branding-preview ' + (field.key === 'login_art_data' ? 'wide' : '')}>
              {draft[field.key] ? <img src={draft[field.key] ?? ''} alt={'Vista previa: ' + field.title} />
                : <div className="branding-placeholder"><span>{field.key === 'favicon_data' ? 'N' : '✦'}</span><small>Vista previa</small></div>}
            </div>
            <label className="branding-file-label">Selecciona una imagen
              <input type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml"
                onChange={async event => {
                  const file = event.currentTarget.files?.[0]
                  event.currentTarget.value = ''
                  if (!file) return
                  try { update(field.key, await readImage(file)) }
                  catch (e) { setError(e instanceof Error ? e.message : String(e)) }
                }} />
            </label>
            <small className="branding-help">PNG, JPEG, WebP o SVG · máximo 5 MB</small>
            <div className="branding-actions">
              <button className="btn" disabled={busyKey === field.key} onClick={() => void save(field.key)}>
                {busyKey === field.key ? 'Guardando…' : saved === field.key ? 'Guardado ✓' : 'Guardar'}
              </button>
              <button className="btn secondary" disabled={!draft[field.key] || busyKey === field.key}
                onClick={() => update(field.key, null)}>Quitar imagen</button>
            </div>
          </section>
        ))}
      </div>
      <p className="muted branding-footer">Los cambios se guardan en el servidor y se aplican a todos los usuarios al actualizar la página.</p>
    </main>
  )
}

