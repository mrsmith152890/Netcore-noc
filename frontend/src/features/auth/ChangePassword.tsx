import { useState } from 'react'
import { apiSend } from '../../services/api'

interface Props {
  forced: boolean
  onDone: () => void
  onLogout?: () => void
}

export default function ChangePassword({ forced, onDone, onLogout }: Props) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [repeat, setRepeat] = useState('')
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  async function submit() {
    if (next !== repeat) return setMsg({ ok: false, text: 'Las contraseñas nuevas no coinciden' })
    try {
      await apiSend('POST', '/auth/password', { current_password: current, new_password: next })
      setCurrent(''); setNext(''); setRepeat('')
      setMsg({ ok: true, text: 'Contraseña actualizada' })
      onDone()
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) })
    }
  }

  const content = (
    <form className="panel login-box" onSubmit={e => { e.preventDefault(); void submit() }}>
      <h2>{forced ? 'Debes cambiar tu contraseña' : 'Cambiar contraseña'}</h2>
      {forced && <p className="muted">Un administrador definió una contraseña temporal. Elige una nueva para continuar.</p>}
      <input type="password" autoComplete="current-password" placeholder="Contraseña actual" value={current} onChange={e => setCurrent(e.target.value)} />
      <input type="password" autoComplete="new-password" placeholder="Nueva contraseña (mín. 10)" value={next} onChange={e => setNext(e.target.value)} />
      <input type="password" autoComplete="new-password" placeholder="Repite la nueva contraseña" value={repeat} onChange={e => setRepeat(e.target.value)} />
      {msg && <p className={msg.ok ? 'muted' : 'error'}>{msg.text}</p>}
      <button className="btn" type="submit" disabled={!current || next.length < 10}>Guardar</button>
      {forced && onLogout && <button className="btn" type="button" onClick={onLogout}>Salir</button>}
    </form>
  )
  return forced ? <div className="login">{content}</div> : <main>{content}</main>
}
