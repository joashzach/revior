import { useQuery } from '@tanstack/react-query'
import { meApi, opsApi, publicApi } from '@/api/endpoints'
import { qk } from '@/api/queryKeys'
import { syncServerTime } from '@/lib/clock'
import { useSession } from '@/app/session'

export const useHealthSync = () =>
  useQuery({ queryKey: qk.health, queryFn: async () => { const h = await publicApi.health(); syncServerTime(h.server_time); return h }, staleTime: 60_000, retry: 1 })

export const useScenario = () => useQuery({ queryKey: qk.scenario, queryFn: publicApi.activeScenario, staleTime: 30_000 })

export function useMe() {
  const t = useSession((s) => s.passenger)
  return useQuery({ queryKey: qk.me, queryFn: meApi.me, enabled: !!t, staleTime: 5_000 })
}
export function useStatus() {
  const t = useSession((s) => s.passenger)
  return useQuery({
    queryKey: qk.status,
    queryFn: async () => { const s = await meApi.status(); syncServerTime(s.server_time); return s },
    enabled: !!t,
    staleTime: 5_000,
  })
}
export function useTrip() {
  const t = useSession((s) => s.passenger)
  return useQuery({ queryKey: qk.trip, queryFn: meApi.trip, enabled: !!t, staleTime: 5_000 })
}
export function useOptions() {
  const t = useSession((s) => s.passenger)
  return useQuery({ queryKey: qk.options, queryFn: meApi.options, enabled: !!t, staleTime: 5_000 })
}
export function useWhy() {
  const t = useSession((s) => s.passenger)
  return useQuery({ queryKey: qk.why, queryFn: meApi.why, enabled: !!t, staleTime: 5_000 })
}
export function useNotifications() {
  const t = useSession((s) => s.passenger)
  return useQuery({ queryKey: qk.notifications, queryFn: meApi.notifications, enabled: !!t, staleTime: 5_000 })
}
export const usePersonas = (refetchMs?: number | false) => useQuery({ queryKey: qk.personas, queryFn: publicApi.personas, refetchInterval: refetchMs ?? false, staleTime: 2_000 })

export const useKpis = () => useQuery({ queryKey: qk.ops.kpis, queryFn: opsApi.kpis, staleTime: 2_000, refetchOnWindowFocus: true })
