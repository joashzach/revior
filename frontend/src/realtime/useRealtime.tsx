import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { toast } from 'sonner'
import { create } from 'zustand'
import { qk } from '@/api/queryKeys'
import { meApi, opsApi } from '@/api/endpoints'
import type { Kpis, RunStats, StressProgress, StressResult } from '@/api/types'
import { useSession } from '@/app/session'
import { S } from '@/config/strings'
import { bus, useConnStore, useVehicleStore } from './bus'
import { invalidationFor } from './events'
import { SocketManager } from './ws'

/** Live ops-only state that is not a server query (stress counters, last reroute for map animation). */
interface LiveStore {
  stress: { running: boolean; progress: StressProgress | null; result: StressResult | null }
  rerouted: Record<number, { at: number; skipped: string[] }>
  judgesJoined: number
  lastRun: RunStats | null
  setLastRun: (r: RunStats) => void
  setStress: (p: Partial<LiveStore['stress']>) => void
  markRerouted: (id: number, skipped?: string[]) => void
  bumpJudges: (n?: number) => void
}
export const useLiveStore = create<LiveStore>((set, get) => ({
  stress: { running: false, progress: null, result: null },
  rerouted: {},
  judgesJoined: 0,
  lastRun: null,
  setLastRun: (r) => set({ lastRun: r }),
  setStress: (p) => set({ stress: { ...get().stress, ...p } }),
  markRerouted: (id, skipped = []) => set({ rerouted: { ...get().rerouted, [id]: { at: Date.now(), skipped } } }),
  bumpJudges: (n = 1) => set({ judgesJoined: n === 0 ? 0 : get().judgesJoined + n }),
}))

/** Coalesce bursts of events: each query refetches at most once per 400 ms window. */
const pending = new Map<string, readonly unknown[]>()
let flushTimer: ReturnType<typeof setTimeout> | null = null
function scheduleInvalidate(client: { invalidateQueries: (o: { queryKey: readonly unknown[] }) => unknown }, keys: readonly (readonly unknown[])[]) {
  for (const k of keys) pending.set(JSON.stringify(k), k)
  if (flushTimer || !pending.size) return
  flushTimer = setTimeout(() => {
    flushTimer = null
    const batch = [...pending.values()]
    pending.clear()
    for (const k of batch) client.invalidateQueries({ queryKey: k })
  }, 400)
}

const onStatus = () => typeof window !== 'undefined' && window.location.pathname.startsWith('/status')
let lastTyped = 0

/** Wires one socket per app (PRD §6.2) + event → cache invalidation / toasts (PRD §6.3) + polling fallback. */
export function useRealtime(kind: 'passenger' | 'ops') {
  const qc = useQueryClient()
  const token = useSession((s) => (kind === 'ops' ? s.ops : s.passenger))
  const conn = useConnStore((s) => s.state)
  const downSince = useConnStore((s) => s.downSince)
  const qcRef = useRef(qc)
  qcRef.current = qc

  // socket lifecycle: created after login, closed on logout or token swap (persona switch reconnects with the new token)
  useEffect(() => {
    if (!token) return
    const refetchAll = () => {
      if (kind === 'passenger') qcRef.current.invalidateQueries({ queryKey: qk.status })
      else {
        qcRef.current.invalidateQueries({ queryKey: qk.ops.kpis })
        qcRef.current.invalidateQueries({ queryKey: qk.ops.map })
      }
    }
    const sm = new SocketManager(kind, token, refetchAll)
    sm.start()
    return () => sm.stop()
  }, [kind, token])

  // event handling
  useEffect(() => {
    const client = qcRef.current
    return bus.on((m) => {
      scheduleInvalidate(client, invalidationFor(m.type, kind))
      const d = m.data
      switch (m.type) {
        case 'vehicle.positions':
          useVehicleStore.getState().put(d.items)
          break
        case 'kpi.updated':
          if (kind === 'ops') client.setQueryData<Kpis>(qk.ops.kpis, d)
          break
        case 'offer.created':
          lastTyped = Date.now()
          toast.success(S.status.cascadeToast, { id: 'offer', description: d.allocation?.service?.label })
          break
        case 'swap.offer_created':
          lastTyped = Date.now()
          if (!onStatus()) toast('Your preferred option has a seat', { id: 'swap', description: d.allocation?.service?.label })
          break
        case 'hold.expiring':
          try { navigator.vibrate?.(200) } catch { /* unsupported (iOS Safari): silent */ }
          if (!onStatus()) toast.warning('Your hold ends in 30 seconds', { id: 'expiring' })
          break
        case 'hold.expired':
          toast.error(S.errors.holdExpired, { id: 'expired' })
          break
        case 'service.rerouted':
          useLiveStore.getState().markRerouted(d.service_id, (d.skipped_stops ?? []).map((n: any) => n.name))
          lastTyped = Date.now()
          // rail short-termination arrives as the same event; the passenger banner on /status already says it
          if (kind === 'ops' || !onStatus()) toast(kind === 'ops' ? 'Service re-routed' : 'Your vehicle was re-routed', { id: 'rerouted', description: d.skipped_stops?.length ? `No longer stops at ${d.skipped_stops.map((n: any) => n.name).join(', ')}` : undefined })
          break
        case 'notification.created':
          // a typed event (offer, swap, re-route) already toasted, and /status shows the same facts inline
          if (kind === 'passenger' && !onStatus() && Date.now() - lastTyped > 3000) toast(d.title, { id: `n-${d.id}`, description: d.body })
          break
        case 'passenger.registered':
          if (kind === 'ops') toast(`Judge joined: ${d.passenger?.name} → ${d.passenger?.destination?.name}`)
          break
        case 'persona.claimed':
          useLiveStore.getState().bumpJudges()
          break
        case 'allocation.run_completed':
          if (kind === 'ops') useLiveStore.getState().setLastRun(d.stats)
          if (kind === 'ops') toast.success(`Allocation done in ${d.stats.duration_ms} ms`, { id: 'alloc', description: `${d.stats.placed_choice1} on 1st choice, ${d.stats.waitlisted} waitlisted, ${d.stats.unresolved} unresolved` })
          break
        case 'disruption.created':
          if (kind === 'ops') toast(`Disruption created`, { id: 'disruption', description: d.disruption?.reason || undefined })
          break
        case 'rules.updated':
          toast(`Priority rules updated to v${d.version}`, { id: 'rules' })
          break
        case 'stress.progress':
          useLiveStore.getState().setStress({ running: true, progress: d, result: null })
          break
        case 'stress.result':
          useLiveStore.getState().setStress({ running: false, result: d })
          break
      }
    })
  }, [kind])

  // polling fallback when the socket has been down > 5 s (PRD §6.2)
  useEffect(() => {
    if (!token || conn === 'connected') return
    const ms = kind === 'passenger' ? 3000 : 2000
    const id = setInterval(() => {
      if (downSince && Date.now() - downSince < 5000) return
      if (kind === 'passenger') qcRef.current.fetchQuery({ queryKey: qk.status, queryFn: meApi.status, staleTime: 0 }).catch(() => {})
      else qcRef.current.fetchQuery({ queryKey: qk.ops.kpis, queryFn: opsApi.kpis, staleTime: 0 }).then((k) => qcRef.current.setQueryData(qk.ops.kpis, k)).catch(() => {})
    }, ms)
    return () => clearInterval(id)
  }, [kind, token, conn, downSince])
}
