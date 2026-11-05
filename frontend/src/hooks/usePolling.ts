import { useEffect, useState } from 'react'

export function usePolling<T>(fetcher: () => Promise<T>, intervalMs: number, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const run = () =>
      fetcher()
        .then(d => {
          if (!cancelled) {
            setData(d)
            setError(null)
          }
        })
        .catch(e => {
          if (!cancelled) setError(String(e))
        })
    run()
    const id = setInterval(run, intervalMs)
    return () => {
      cancelled = true
      clearInterval(id)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return { data, error }
}
