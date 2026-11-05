import { useCallback, useEffect, useState } from 'react'
import AlertsConfig from './features/alerts/AlertsConfig'
import AlertsView from './features/alerts/AlertsView'
import Dashboard from './features/dashboard/Dashboard'
import ChangePassword from './features/auth/ChangePassword'
import LoginPage from './features/auth/LoginPage'
import UsersView from './features/auth/UsersView'
import DeviceDetail from './features/devices/DeviceDetail'
import DeviceEditor from './features/devices/DeviceEditor'
import DeviceTable from './features/devices/DeviceTable'
import DiscoveryView from './features/discovery/DiscoveryView'
import MapsView from './features/maps/MapsView'
import MapsOrganizationView from './features/maps/MapsOrganizationView'
import BrandingView from './features/system/BrandingView'
import ReportsView from './features/reports/ReportsView'
import SystemView from './features/system/SystemView'
import SitesView from './features/system/SitesView'
import MaintenanceView from './features/system/MaintenanceView'
import AuditView from './features/system/AuditView'
import ServicesView from './features/services/ServicesView'
import { usePolling } from './hooks/usePolling'
import { apiGet, apiSend } from './services/api'
import type { AlertOut, AppBranding, DeviceStatus, SystemStatus, User } from './types/api'

type View = 'dashboard' | 'maps' | 'organization' | 'branding' | 'devices' | 'services' | 'discovery' | 'alerts' | 'reports' | 'system' | 'sites' | 'users' | 'maintenance' | 'audit' | 'account'
type AuthState = { status: 'loading' } | { status: 'anon' } | { status: 'ok'; user: User }
type Theme = 'dark' | 'light'
function getInitialTheme(): Theme {
  try { const saved = localStorage.getItem('noc-theme'); if (saved === 'light' || saved === 'dark') return saved } catch {}
  return 'dark'
}
function ThemeToggle({ theme, onToggle, floating = false }: { theme: Theme; onToggle: () => void; floating?: boolean }) {
  const next = theme === 'dark' ? 'claro' : 'oscuro'
  return <button className={'theme-toggle' + (floating ? ' theme-toggle-floating' : '')} type="button" onClick={onToggle}
    aria-label={'Cambiar al modo ' + next} title={'Cambiar al modo ' + next}>
    <span className="theme-toggle-icon" aria-hidden="true">{theme === 'dark' ? '☾' : '☀'}</span>
    <span className="theme-toggle-copy"><small>APARIENCIA</small><strong>{theme === 'dark' ? 'Oscuro' : 'Claro'}</strong></span>
    <span className={'theme-toggle-switch ' + theme} aria-hidden="true"><i /></span>
  </button>
}
const RANK = { viewer: 1, operator: 2, admin: 3 }

function Shell({ user, onLogout, theme, onThemeToggle, branding, onBrandingChange }: { user: User; onLogout: () => void; theme: Theme; onThemeToggle: () => void; branding: AppBranding; onBrandingChange: (value: AppBranding) => void }) {
  const { data, error } = usePolling(() => apiGet<DeviceStatus[]>('/status'), 5000)
  const activeAlerts = usePolling(() => apiGet<AlertOut[]>('/alerts?state=active&limit=200'), 10000)
  const system = usePolling(() => apiGet<SystemStatus>('/system/status'), 15000)
  const [view, setView] = useState<View>('dashboard')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [deletedDeviceIds, setDeletedDeviceIds] = useState<Set<number>>(new Set())
  const [deviceDeleteError, setDeviceDeleteError] = useState<string | null>(null)

  const isAdmin = user.role === 'admin'
  const canOperate = RANK[user.role] >= RANK.operator
  const devices = (data ?? []).filter(d => !deletedDeviceIds.has(d.device_id))
  const selected = devices.find(d => d.device_id === selectedId) ?? null
  const count = (s: string) => devices.filter(d => d.state === s).length
  const alertCount = activeAlerts.data?.filter(a => a.state === 'firing').length ?? 0

  async function deleteDevice(deviceId: number) {
    const device = devices.find(d => d.device_id === deviceId)
    if (!device || !isAdmin) return
    const confirmed = window.confirm(
      '¿Eliminar ' + device.name + ' (' + device.ip_address + ')? Se borrarán también su historial de ping, SNMP, servicios y alertas. ' +
      'Las notificaciones ya generadas y los resultados de descubrimiento se conservarán.'
    )
    if (!confirmed) return

    setDeviceDeleteError(null)
    try {
      await apiSend('DELETE', '/devices/' + deviceId)
      setDeletedDeviceIds(current => new Set(current).add(deviceId))
      setSelectedId(current => current === deviceId ? null : current)
    } catch (e) {
      setDeviceDeleteError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <div className="app">
      <header>
        <h1 className={'app-brand-title' + (branding.logo_data ? ' has-logo' : '')}>{branding.logo_data && <img src={branding.logo_data} alt="" />}<span>NetCore NOC</span></h1>
        <div className="summary">
          <span className={`badge ${alertCount > 0 ? 'DOWN' : 'UP'}`}>
            {alertCount > 0 ? `${alertCount} alertas` : 'Sin alertas'}
          </span>
          <span className={`badge ${system.data && !system.data.overall_ok ? 'DOWN' : 'UP'}`}>
            {system.data && !system.data.overall_ok ? `Sistema: ${system.data.problems} fallos` : 'Sistema OK'}
          </span>
          <span className="badge UP">{count('UP')} UP</span>
          <span className="badge DOWN">{count('DOWN')} DOWN</span>
          <span className="badge UNKNOWN">{count('UNKNOWN')} UNKNOWN</span>
          <span className="muted">{user.full_name || user.username} ({user.role})</span>
          <ThemeToggle theme={theme} onToggle={onThemeToggle} />
          <button className="btn" onClick={onLogout}>Salir</button>
        </div>
      </header>
      <nav className="tabs">
        <div className="sidebar-brand">
          {branding.logo_data ? <img src={branding.logo_data} alt="" /> : <span className="sidebar-brand-mark">N</span>}
          <div><strong>NetCore NOC</strong><small>Network Operations Center</small></div>
        </div>
        <button className={view === 'dashboard' ? 'active' : ''} onClick={() => setView('dashboard')}><span className="nav-icon">◫</span>Resumen</button>
        <button className={view === 'maps' ? 'active' : ''} onClick={() => setView('maps')}><span className="nav-icon">⌘</span>Mapas</button>
        <button className={view === 'organization' ? 'active' : ''} onClick={() => setView('organization')}><span className="nav-icon">▤</span>Dominios</button>
        <button className={view === 'devices' ? 'active' : ''} onClick={() => setView('devices')}><span className="nav-icon">▣</span>Dispositivos</button>
        <button className={view === 'services' ? 'active' : ''} onClick={() => setView('services')}><span className="nav-icon">◉</span>Servicios</button>
        {canOperate && <button className={view === 'discovery' ? 'active' : ''} onClick={() => setView('discovery')}><span className="nav-icon">⌕</span>Descubrimiento</button>}
        <button className={view === 'alerts' ? 'active' : ''} onClick={() => setView('alerts')}><span className="nav-icon">♢</span>Alertas</button>
        <button className={view === 'reports' ? 'active' : ''} onClick={() => setView('reports')}><span className="nav-icon">▤</span>Reportes</button>
        <button className={view === 'system' ? 'active' : ''} onClick={() => setView('system')}><span className="nav-icon">⚙</span>Sistema</button>
        {isAdmin && <button className={view === 'maintenance' ? 'active' : ''} onClick={() => setView('maintenance')}><span className="nav-icon">◷</span>Mantenimiento</button>}
        {isAdmin && <button className={view === 'audit' ? 'active' : ''} onClick={() => setView('audit')}><span className="nav-icon">≋</span>Historial</button>}
        {isAdmin && <button className={view === 'sites' ? 'active' : ''} onClick={() => setView('sites')}><span className="nav-icon">⌖</span>Sedes</button>}
        {isAdmin && <button className={view === 'branding' ? 'active' : ''} onClick={() => setView('branding')}><span className="nav-icon">✦</span>Identidad visual</button>}
        {isAdmin && <button className={view === 'users' ? 'active' : ''} onClick={() => setView('users')}><span className="nav-icon">♙</span>Usuarios</button>}
        <button className={view === 'account' ? 'active' : ''} onClick={() => setView('account')}><span className="nav-icon">◎</span>Mi cuenta</button>
      </nav>
      {error && <p className="error">Backend no responde: {error}</p>}
      {view === 'dashboard' && <Dashboard devices={devices} alerts={activeAlerts.data ?? []} system={system.data ?? null} onNavigate={setView} canOperate={canOperate} />}
      {view === 'maps' && <main><MapsView statuses={devices} /></main>}
      {view === 'organization' && <MapsOrganizationView statuses={devices} />}
      {view === 'branding' && isAdmin && <BrandingView branding={branding} onChange={onBrandingChange} />}
      {view === 'devices' && (
        <main>
          <section className="panel">
            {deviceDeleteError && <p className="error">{deviceDeleteError}</p>}
            <DeviceTable
              devices={devices}
              selectedId={selectedId}
              onSelect={setSelectedId}
              canDelete={isAdmin}
              onDelete={id => void deleteDevice(id)}
            />
          </section>
          {selected && <DeviceDetail key={selected.device_id} device={selected} />}
          {isAdmin && selected && <DeviceEditor key={`editor-${selected.device_id}`} deviceId={selected.device_id} />}
        </main>
      )}
      {view === 'services' && <ServicesView devices={devices} isAdmin={isAdmin} canOperate={canOperate} />}
      {view === 'reports' && <ReportsView />}
      {view === 'system' && <SystemView />}
      {view === 'sites' && isAdmin && <SitesView />}
      {view === 'maintenance' && isAdmin && <MaintenanceView devices={devices} />}
      {view === 'audit' && isAdmin && <AuditView />}
      {view === 'discovery' && canOperate && <DiscoveryView />}
      {view === 'alerts' && (
        <main>
          <AlertsView devices={devices} />
          {isAdmin && <AlertsConfig devices={devices} />}
        </main>
      )}
      {view === 'users' && isAdmin && <UsersView me={user} />}
      {view === 'account' && <ChangePassword forced={false} onDone={() => undefined} />}
    </div>
  )
}

export default function App() {
  const [auth, setAuth] = useState<AuthState>({ status: 'loading' })
  const [theme, setTheme] = useState<Theme>(getInitialTheme)
  const [branding, setBranding] = useState<AppBranding>({ logo_data: null, favicon_data: null, login_art_data: null, login_status_enabled: false })
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try { localStorage.setItem('noc-theme', theme) } catch {}
  }, [theme])
  const toggleTheme = () => setTheme(current => current === 'dark' ? 'light' : 'dark')
  useEffect(() => { void apiGet<AppBranding>('/branding').then(setBranding).catch(() => undefined) }, [])
  useEffect(() => {
    const link = document.querySelector<HTMLLinkElement>('link[rel~="icon"]')
    if (link) link.href = branding.favicon_data || branding.logo_data || '/favicon.svg?v=3'
  }, [branding])

  const loadMe = useCallback(async () => {
    try {
      setAuth({ status: 'ok', user: await apiGet<User>('/auth/me') })
    } catch {
      setAuth({ status: 'anon' })
    }
  }, [])

  useEffect(() => {
    void loadMe()
  }, [loadMe])

  useEffect(() => {
    const onExpired = () => setAuth({ status: 'anon' })
    window.addEventListener('noc-unauthorized', onExpired)
    return () => window.removeEventListener('noc-unauthorized', onExpired)
  }, [])

  const logout = async () => {
    await apiSend('POST', '/auth/logout').catch(() => undefined)
    setAuth({ status: 'anon' })
  }

  if (auth.status === 'loading') return <p className="muted" style={{ padding: 24 }}>Cargando…</p>
  if (auth.status === 'anon') return <><ThemeToggle theme={theme} onToggle={toggleTheme} floating /><LoginPage branding={branding} onLogin={user => setAuth({ status: 'ok', user })} /></>
  if (auth.user.must_change_password)
    return <ChangePassword forced onDone={() => void loadMe()} onLogout={() => void logout()} />
  return <Shell user={auth.user} onLogout={() => void logout()} theme={theme} onThemeToggle={toggleTheme} branding={branding} onBrandingChange={setBranding} />
}
