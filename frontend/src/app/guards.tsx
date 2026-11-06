import { useEffect, type ReactNode } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { UNAUTHORIZED_EVENT } from '@/api/http'
import { S } from '@/config/strings'
import { useSession } from './session'

export function RequirePassenger({ children }: { children: ReactNode }) {
  const token = useSession((s) => s.passenger)
  const loc = useLocation()
  if (!token) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />
  return <>{children}</>
}

export function RequireOps({ children }: { children: ReactNode }) {
  const token = useSession((s) => s.ops)
  if (!token) return <Navigate to="/ops/login" replace />
  return <>{children}</>
}

/** 401 anywhere → clear THAT token, toast, go to the matching login (PRD §3.2). */
export function AuthWatcher() {
  const nav = useNavigate()
  const loc = useLocation()
  const refresh = useSession((s) => s.refresh)
  useEffect(() => {
    const on = (e: Event) => {
      const kind = (e as CustomEvent).detail?.kind as 'passenger' | 'ops'
      refresh()
      toast.error(S.errors.sessionEnded)
      if (kind === 'ops') nav('/ops/login', { replace: true })
      else nav(`/login?next=${encodeURIComponent(loc.pathname)}`, { replace: true })
    }
    window.addEventListener(UNAUTHORIZED_EVENT, on)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, on)
  }, [nav, loc.pathname, refresh])
  return null
}
