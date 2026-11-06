import { useEffect, useState } from 'react'
import { secondsUntil, serverNow } from '@/lib/clock'

/** Seconds left until `iso`, by the server clock; re-renders once a second. */
export function useCountdown(iso: string | null | undefined): number {
  const [secs, setSecs] = useState(() => secondsUntil(iso))
  useEffect(() => {
    setSecs(secondsUntil(iso))
    if (!iso) return
    const id = setInterval(() => setSecs(secondsUntil(iso, serverNow())), 250)
    return () => clearInterval(id)
  }, [iso])
  return secs
}

/** Fraction elapsed (0..1) between opens_at and closes_at, by the server clock. */
export function useProgress(openIso: string | null | undefined, closeIso: string | null | undefined): number {
  const secs = useCountdown(closeIso)
  if (!openIso || !closeIso) return 0
  const total = (Date.parse(closeIso) - Date.parse(openIso)) / 1000
  return total <= 0 ? 1 : Math.min(1, Math.max(0, 1 - secs / total))
}
