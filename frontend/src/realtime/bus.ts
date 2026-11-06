import { create } from 'zustand'
import type { VehiclePos, WsMessage } from '@/api/types'

/** Tiny pub/sub shared by the real socket and the mock emitter. */
type Listener = (m: WsMessage) => void
const listeners = new Set<Listener>()
export const bus = {
  on(fn: Listener) {
    listeners.add(fn)
    return () => { listeners.delete(fn) }
  },
  emit(m: WsMessage) {
    listeners.forEach((l) => l(m))
  },
}

export type ConnState = 'connecting' | 'connected' | 'reconnecting' | 'offline'

interface ConnStore {
  state: ConnState
  downSince: number | null
  set: (s: ConnState) => void
}
export const useConnStore = create<ConnStore>((set, get) => ({
  state: 'offline',
  downSince: null,
  set: (s) => {
    const cur = get()
    if (cur.state === s) return
    set({ state: s, downSince: s === 'connected' ? null : (cur.downSince ?? Date.now()) })
  },
}))

/** Latest vehicle positions (map markers read this imperatively; no React re-render per tick). */
interface VehicleStore {
  positions: Record<number, VehiclePos>
  version: number
  put: (items: VehiclePos[]) => void
  reset: () => void
}
export const useVehicleStore = create<VehicleStore>((set, get) => ({
  positions: {},
  version: 0,
  put: (items) => {
    const next = { ...get().positions }
    for (const v of items) next[v.service_id] = v
    set({ positions: next, version: get().version + 1 })
  },
  reset: () => set({ positions: {}, version: 0 }),
}))
