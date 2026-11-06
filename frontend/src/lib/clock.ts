import { create } from 'zustand'

/**
 * Server clock offset (PRD §4.3): offset = server_time - Date.now(). Every countdown uses serverNow() so two phones
 * with different clocks show the same timer. Updated from /health, /me/status and every WebSocket `ts`.
 */
interface ClockState {
  offset: number
  synced: boolean
  sync: (serverIso: string | null | undefined) => void
}

export const useClockStore = create<ClockState>((set, get) => ({
  offset: 0,
  synced: false,
  sync: (iso) => {
    if (!iso) return
    const t = Date.parse(iso)
    if (Number.isNaN(t)) return
    const next = t - Date.now()
    // smooth: ignore sub-250ms jitter once synced so timers don't twitch on every WS tick
    if (!get().synced || Math.abs(next - get().offset) > 250) set({ offset: next, synced: true })
  },
}))

export const syncServerTime = (iso: string | null | undefined) => useClockStore.getState().sync(iso)
export const serverNow = () => Date.now() + useClockStore.getState().offset

/** Seconds remaining until an ISO timestamp, by the server clock (never negative). */
export function secondsUntil(iso: string | null | undefined, now: number = serverNow()): number {
  if (!iso) return 0
  return Math.max(0, Math.ceil((Date.parse(iso) - now) / 1000))
}

export function formatMmSs(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds))
  const m = Math.floor(s / 60)
  return `${m}:${String(s % 60).padStart(2, '0')}`
}
