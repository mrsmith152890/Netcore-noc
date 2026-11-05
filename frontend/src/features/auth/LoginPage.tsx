import { useState } from 'react'
import { usePolling } from '../../hooks/usePolling'
import { apiGet, apiSend } from '../../services/api'
import type { AppBranding, LoginNetworkSummary, User } from '../../types/api'

export default function LoginPage({ onLogin, branding = { logo_data: null, favicon_data: null, login_art_data: null, login_status_enabled: false } }: { onLogin: (u: User) => void; branding?: AppBranding }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const networkSummary = usePolling<LoginNetworkSummary>(
    () => branding.login_status_enabled
      ? apiGet<LoginNetworkSummary>('/branding/login-summary')
      : Promise.resolve({ enabled: false, devices_total: 0, devices_up: 0, devices_down: 0, alerts_active: 0, alerts_critical: 0 }),
    30000, [branding.login_status_enabled],
  )

  async function submit() {
    setBusy(true)
    try {
      onLogin(await apiSend<User>('POST', '/auth/login', { username, password }))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setPassword('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login">
      <div className="login-shell">
        <aside className="login-atmosphere" aria-label="Panel visual de acceso"
          style={branding.login_art_data ? { backgroundImage: 'linear-gradient(180deg, rgba(4,12,28,.12), rgba(4,12,28,.82)), url("' + branding.login_art_data + '")' } : undefined}>
          <div className="login-art-grid" aria-hidden="true" />
          <div className="login-art-brand">{branding.logo_data ? <img src={branding.logo_data} alt="" /> : <span>N</span>}
            <small>NETCORE · INFRASTRUCTURE</small></div>
          <div className="login-art-copy"><span className="live-kicker"><i /> NETWORK OPERATIONS</span>
            <h2>Visibilidad clara.<br /><em>Red bajo control.</em></h2>
            <p>Supervisa el estado de tu infraestructura desde un solo lugar.</p></div>
          {branding.login_status_enabled && networkSummary.data?.enabled && (
            <section className="login-network-status" aria-label="Resumen público del estado de la red">
              <header><span><i /> ESTADO DE INFRAESTRUCTURA</span><small>ACTUALIZACIÓN EN VIVO</small></header>
              <div className="login-network-metrics">
                <div className="login-network-metric online"><small>EQUIPOS EN LÍNEA</small><strong>{networkSummary.data.devices_up}<em> / {networkSummary.data.devices_total}</em></strong></div>
                <div className="login-network-metric offline"><small>EQUIPOS CAÍDOS</small><strong>{networkSummary.data.devices_down}</strong></div>
                <div className="login-network-metric alerts"><small>ALERTAS ACTIVAS</small><strong>{networkSummary.data.alerts_active}</strong></div>
                <div className="login-network-metric critical"><small>CRÍTICAS</small><strong>{networkSummary.data.alerts_critical}</strong></div>
              </div>
              <small className="login-network-privacy">Resumen agregado · no muestra nombres ni direcciones IP</small>
            </section>
          )}
          <div className="login-art-foot"><span>NETCORE NOC</span><span>SECURE ACCESS · 24/7</span></div>
        </aside>
      <form className="panel login-box" onSubmit={e => { e.preventDefault(); void submit() }}>
        <div className="login-brand">{branding.logo_data ? <img className="login-mark-image" src={branding.logo_data} alt="" /> : <span className="login-mark">N</span>}<div><h1>NetCore NOC</h1><p>Centro de operaciones de red</p></div></div>
        <label>Usuario<input autoFocus autoComplete="username" placeholder="Ingresa tu usuario" value={username} onChange={e => setUsername(e.target.value)} /></label>
        <label>Contraseña<input type="password" autoComplete="current-password" placeholder="Ingresa tu contraseña" value={password} onChange={e => setPassword(e.target.value)} /></label>
        {error && <p className="error">{error}</p>}
        <button className="btn login-submit" type="submit" disabled={busy || !username || !password}>{busy ? 'Ingresando…' : 'Iniciar sesión'}<span aria-hidden="true">→</span></button>
        <p className="login-footnote">Acceso seguro · Monitoreo de infraestructura</p>
      </form>
      </div>
    </div>
  )
}
