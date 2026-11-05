import { useState } from 'react'
import { usePolling } from '../../hooks/usePolling'
import { apiGet, apiSend } from '../../services/api'
import { fmtDateTime } from '../../services/format'
import type { AuditEntry, User } from '../../types/api'

const ROLES: [string, string][] = [['viewer', 'Solo lectura'], ['operator', 'Operador'], ['admin', 'Administrador']]
const errMsg = (e: unknown) => (e instanceof Error ? e.message : String(e))

export default function UsersView({ me }: { me: User }) {
  const [tick, setTick] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const users = usePolling(() => apiGet<User[]>('/auth/users'), 15000, [tick])
  const audit = usePolling(() => apiGet<AuditEntry[]>('/audit?limit=50'), 10000, [tick])
  const [form, setForm] = useState({ username: '', full_name: '', role: 'viewer', password: '' })

  async function act(fn: () => Promise<unknown>) {
    try {
      await fn()
      setError(null)
      setTick(t => t + 1)
    } catch (e) {
      setError(errMsg(e))
    }
  }

  const deleteUser = (u: User) => {
    if (u.id === me.id) return
    const confirmed = window.confirm(
      '¿Eliminar definitivamente al usuario «' + u.username + '»? Se cerrarán sus sesiones y esta acción no se puede deshacer.'
    )
    if (confirmed) void act(() => apiSend('DELETE', '/auth/users/' + u.id))
  }

  const resetPassword = (u: User) => {
    const pw = window.prompt(`Contraseña temporal para ${u.username} (mínimo 10 caracteres)`)
    if (!pw) return
    void act(() => apiSend('POST', `/auth/users/${u.id}/reset-password`, { new_password: pw }))
  }
  const isLocked = (u: User) => !!u.locked_until && new Date(u.locked_until) > new Date()

  return (
    <main>
      <section className="panel">
        <h3 style={{ marginTop: 0 }}>Usuarios</h3>
        <div className="form-row">
          <input placeholder="usuario" value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} />
          <input placeholder="Nombre completo" value={form.full_name} onChange={e => setForm({ ...form, full_name: e.target.value })} />
          <select value={form.role} onChange={e => setForm({ ...form, role: e.target.value })}>
            {ROLES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <input type="password" placeholder="Contraseña temporal (mín. 10)" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} />
          <button
            disabled={!form.username.trim() || form.password.length < 10}
            onClick={() => void act(async () => {
              await apiSend('POST', '/auth/users', { ...form, full_name: form.full_name.trim() || null })
              setForm({ username: '', full_name: '', role: 'viewer', password: '' })
            })}
          >
            Crear usuario
          </button>
        </div>
        {error && <p className="error">{error}</p>}
        <table className="grid">
          <thead><tr><th>Usuario</th><th>Nombre</th><th>Rol</th><th>Estado</th><th>Último acceso</th><th></th></tr></thead>
          <tbody>
            {(users.data ?? []).map(u => (
              <tr key={u.id}>
                <td>{u.username}{u.id === me.id && <span className="muted"> (tú)</span>}</td>
                <td>{u.full_name ?? '—'}</td>
                <td>
                  <select disabled={u.id === me.id} value={u.role}
                    onChange={e => void act(() => apiSend('PATCH', `/auth/users/${u.id}`, { role: e.target.value }))}>
                    {ROLES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </td>
                <td>
                  {!u.enabled ? <span className="badge UNKNOWN">Desactivado</span>
                    : isLocked(u) ? <span className="badge DOWN">Bloqueado</span>
                    : <span className="badge UP">Activo</span>}
                  {u.must_change_password && <span className="muted"> · clave temporal</span>}
                </td>
                <td>{fmtDateTime(u.last_login_at)}</td>
                <td>
                  <button className="btn" onClick={() => resetPassword(u)}>Restablecer clave</button>{' '}
                  {isLocked(u) && <><button className="btn" onClick={() => void act(() => apiSend('POST', `/auth/users/${u.id}/unlock`))}>Desbloquear</button>{' '}</>}
                  {u.id !== me.id && (
                    <button className="btn" onClick={() => void act(() => apiSend('PATCH', `/auth/users/${u.id}`, { enabled: !u.enabled }))}>
                      {u.enabled ? 'Desactivar' : 'Activar'}
                    </button>
                  )}
                  {u.id !== me.id && (
                    <button className="btn danger" onClick={() => deleteUser(u)}>Eliminar</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="panel">
        <h3 style={{ marginTop: 0 }}>Auditoría (últimos 50 eventos)</h3>
        <table className="grid">
          <thead><tr><th>Hora</th><th>Usuario</th><th>IP</th><th>Acción</th><th>Resultado</th><th>Detalle</th></tr></thead>
          <tbody>
            {(audit.data ?? []).map(a => (
              <tr key={a.id}>
                <td>{fmtDateTime(a.at)}</td>
                <td>{a.username ?? '—'}</td>
                <td>{a.ip ?? '—'}</td>
                <td>{a.method} {a.path}</td>
                <td><span className={`badge ${a.status_code < 400 ? 'UP' : 'DOWN'}`}>{a.status_code}</span></td>
                <td className="muted">{a.detail ?? ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  )
}
