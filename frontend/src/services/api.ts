async function fail(r: Response): Promise<never> {
  if (r.status === 401) window.dispatchEvent(new Event('noc-unauthorized'))
  let detail = `${r.status} ${r.statusText}`
  try {
    const j = await r.json()
    if (typeof j.detail === 'string') detail = j.detail
    else if (Array.isArray(j.detail))
      detail = j.detail.map((d: { msg?: string }) => d.msg ?? '').filter(Boolean).join('; ') || detail
  } catch {
    // respuesta sin cuerpo JSON
  }
  throw new Error(detail)
}

export async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(`/api/v1${path}`)
  if (!r.ok) return fail(r)
  return (await r.json()) as T
}

export async function apiSend<T = void>(
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE',
  path: string,
  body?: unknown,
): Promise<T> {
  const r = await fetch(`/api/v1${path}`, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!r.ok) return fail(r)
  if (r.status === 204) return undefined as T
  return (await r.json()) as T
}
