import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import type { Passenger } from '@/api/types'
import { qk } from '@/api/queryKeys'
import { useSession } from '@/app/session'
import { routeForState } from '@/app/stateRouter'

/** Store the token, seed the caches, go to where this passenger's state belongs (or `next`). */
export function useCompleteLogin() {
  const qc = useQueryClient()
  const nav = useNavigate()
  const setPassenger = useSession((s) => s.setPassenger)
  return (token: string, passenger: Passenger, next?: string | null) => {
    setPassenger(token)
    for (const k of [qk.status, qk.trip, qk.options, qk.why, qk.alternatives, qk.notifications, qk.pods]) qc.removeQueries({ queryKey: k })
    qc.setQueryData(qk.me, passenger)
    const safeNext = next && next.startsWith('/') && !next.startsWith('//') ? next : null
    nav(safeNext ?? routeForState(passenger.state), { replace: true })
  }
}
