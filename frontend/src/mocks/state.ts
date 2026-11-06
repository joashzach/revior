// In-memory mock backend state + event emitter. Mirrors backend behaviour closely enough for the whole demo flow.
import type { Alternative, Kpis, NetworkEdge, Needs, PassengerState, Pod } from '@/api/types'
import { buildEdges, NODES, PERSONAS, SERVICES, type PersonaDef } from './world'

export interface MAlloc {
  id: number
  serviceId: number
  seats: string[]
  rank: '1' | '2' | 'auto' | 'cascade' | 'claim' | 'swap'
  status: 'held' | 'swap_held' | 'confirmed'
  holdExpires: number | null
  explanation: string
  score: number
}
export interface MPax {
  id: number
  persona: PersonaDef | null
  name: string
  email: string
  destCode: string
  party: number
  needs: Needs
  allowAuto: boolean
  state: PassengerState
  affectedAt: number | null
  ticketId: string
  c1: number | null
  c2: number | null
  any: boolean
  alloc: MAlloc | null
  swap: MAlloc | null
  waitlist: number[]
  resolvedAlt: Alternative | null
  notifications: { id: number; template: string; title: string; body: string; created_at: string; read: boolean }[]
  podId: number | null
  token: string
}

export interface MEvent {
  type: string
  data: any
  aud: 'ops' | 'passengers' | 'all'
  pax?: number[]
}

export class MockState {
  t0 = Date.now()
  nextId = 1000
  pax = new Map<number, MPax>()
  claimed = new Map<number, number>() // persona id -> pax id
  edges: NetworkEdge[] = buildEdges()
  cancelled = false
  delayMin = 0
  reroute: Record<number, { polyline: any; skipped: string[]; extraMin: number }> = {}
  free: Record<number, number> = {}
  accFree: Record<number, number> = {}
  batch: { id: number; opens: number; closes: number; status: 'open' | 'closed' | 'allocated' } | null = null
  batchTimer: ReturnType<typeof setTimeout> | null = null
  disruptions: any[] = []
  rules = { version: 1, weights: { medical: 30, wheelchair: 30, elderly: 15, with_children: 10, deadline_urgency: 20, wait_time: 20 } as Record<string, number>, history: [] as any[] }
  config = { batch_window_seconds: 30, hold_seconds: 120, auto_run_on_batch_close: true, delay_threshold_minutes: 20, hub_radius_km: 10, open_booking_enabled: false, sim_speed: 10, demo_mode: true, join_qr_mode: 'corner' as 'corner' | 'fullscreen' | 'hidden' }
  audit: any[] = []
  messages: any[] = []
  pods: (Pod & { memberIds: number[] })[] = []
  extraServices: any[] = []
  runStats: any = null
  scenarioSlug = 'potheri-demo'
  kpis: Kpis
  listeners = new Set<(e: MEvent) => void>()
  timers = new Set<ReturnType<typeof setTimeout>>()

  constructor() {
    this.resetSeats()
    this.kpis = this.baseKpis()
  }

  baseKpis(): Kpis {
    return { affected: 0, checked_in: 0, not_checked_in: 0, requested: 0, held: 0, confirmed: 0, waitlisted: 0, unresolved: 0, resolved_alt: 0, avg_wait_min: 0, median_time_to_placement_min: 0, fill_rate: 0.9, batch: null }
  }

  resetSeats() {
    for (const s of SERVICES) {
      this.free[s.id] = Math.max(0, s.seats - s.heldInit)
      this.accFree[s.id] = s.inventory ? Math.min(s.accessibleSeats, this.free[s.id] || 1) : 0
    }
  }

  reset() {
    this.timers.forEach(clearTimeout)
    this.timers.clear()
    if (this.batchTimer) clearTimeout(this.batchTimer)
    Object.assign(this, {
      t0: Date.now(), pax: new Map(), claimed: new Map(), edges: buildEdges(), cancelled: false, delayMin: 0, reroute: {}, batch: null,
      disruptions: [], audit: [], messages: [], pods: [], extraServices: [], runStats: null,
    })
    this.rules = { version: 1, weights: { medical: 30, wheelchair: 30, elderly: 15, with_children: 10, deadline_urgency: 20, wait_time: 20 }, history: [] }
    this.config = { ...this.config, open_booking_enabled: false, join_qr_mode: 'corner', batch_window_seconds: this.config.batch_window_seconds }
    this.resetSeats()
    this.kpis = this.baseKpis()
    this.emit({ type: 'kpi.updated', data: this.kpis, aud: 'ops' })
  }

  on(fn: (e: MEvent) => void) {
    this.listeners.add(fn)
    return () => this.listeners.delete(fn)
  }
  emit(e: MEvent) {
    this.listeners.forEach((l) => l(e))
  }
  later(ms: number, fn: () => void) {
    const t = setTimeout(() => {
      this.timers.delete(t)
      fn()
    }, ms)
    this.timers.add(t)
  }
  id() {
    return this.nextId++
  }
  iso(ms: number = Date.now()) {
    return new Date(ms).toISOString()
  }

  persona(id: number) {
    return PERSONAS.find((p) => p.id === id)
  }
  svc(id: number) {
    return SERVICES.find((s) => s.id === id) ?? this.extraServices.find((s) => s.id === id)
  }
  nodes = NODES
}

export const mock = new MockState()
