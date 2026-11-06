// Mock backend: routes every API call (contract §5) to in-memory handlers. Same shapes as backend/contracts/examples.
import { ApiError } from '@/api/http'
import type * as T from '@/api/types'
import { CHAIN, lineOf, nodeByCode, nodeById, NODES, PERSONAS, SERVICES } from './world'
import { mock as M, type MAlloc, type MPax } from './state'

const MIN = 60_000
const delay = (ms = 120) => new Promise((r) => setTimeout(r, ms + Math.random() * 80))
const err = (status: number, code: string, message: string, details = {}) => new ApiError(status, code, message, details)

// ---------------------------------------------------------------- serializers
function svcStatus(id: number): T.ServiceStatus {
  if (id === 1 && M.cancelled) return 'cancelled'
  if (M.reroute[id]) return 'rerouted'
  if (id === 1 && M.delayMin > 0) return 'delayed'
  return 'scheduled'
}
function svcSummary(s: any): T.ServiceSummary {
  const first = nodeByCode(s.stops[0])
  const last = nodeByCode(s.stops[s.stops.length - 1])
  const dep = M.t0 + s.departMin * MIN
  return {
    id: s.id, code: s.code, label: s.label, mode: s.mode, status: svcStatus(s.id), delay_minutes: s.id === 1 ? M.delayMin : 0,
    depart_at: M.iso(dep), arrive_at: M.iso(dep + (s.durationMin + (M.reroute[s.id]?.extraMin ?? 0)) * MIN), origin: first, destination: last, accessible: s.inventory && s.accessibleSeats > 0,
  }
}
const allServices = () => [...SERVICES, ...M.extraServices]
function legOf(s: any, a: string, b: string): T.Leg {
  const ia = s.stops.indexOf(a)
  const ib = s.stops.indexOf(b)
  const dep = M.t0 + s.departMin * MIN
  const f = (i: number) => dep + (s.durationMin * i * MIN) / Math.max(1, s.stops.length - 1)
  return { service: svcSummary(s), from: nodeByCode(a), to: nodeByCode(b), depart_at: M.iso(f(ia)), arrive_at: M.iso(f(ib) + (M.reroute[s.id]?.extraMin ?? 0) * MIN), has_seats: s.inventory }
}
function optionsFor(p: MPax): T.Option[] {
  const out: T.Option[] = []
  const dl = p.needs.connection_deadline_at ? Date.parse(p.needs.connection_deadline_at) : null
  for (const s of allServices()) {
    if (!s.inventory || svcStatus(s.id) === 'cancelled') continue
    const ia = s.stops.indexOf('POT')
    const ib = s.stops.indexOf(p.destCode)
    if (ia < 0 || ib <= ia) continue
    if (p.needs.wheelchair && !(s.accessibleSeats > 0)) continue
    const leg = legOf(s, 'POT', p.destCode)
    const left = M.free[s.id] ?? 0
    out.push({
      option_id: `S${s.id}`, request_service_id: s.id, label: s.label, mode: s.mode, legs: [leg], depart_at: leg.depart_at, eta_at: leg.arrive_at, transfers: 0,
      is_multi_leg: false, seats_left: left, accessible_seats_left: M.accFree[s.id] ?? 0, is_full: left < p.party || (p.needs.wheelchair && (M.accFree[s.id] ?? 0) < 1),
      meets_deadline: dl === null || Date.parse(leg.arrive_at) <= dl, accessible: s.accessibleSeats > 0,
    })
  }
  if (['BCH', 'EGM'].includes(p.destCode)) {
    const bus = SERVICES[3]
    const l1 = legOf(bus, 'POT', 'TAM')
    const train = { ...SERVICES[7], id: 8 }
    const dep2 = Date.parse(l1.arrive_at) + 25 * MIN
    const l2: T.Leg = { service: svcSummary(train), from: nodeByCode('TAM'), to: nodeByCode(p.destCode), depart_at: M.iso(dep2), arrive_at: M.iso(dep2 + 38 * MIN), has_seats: true }
    out.push({
      option_id: 'S4+S8', request_service_id: bus.id, label: `${bus.label} + onward local (change at Tambaram)`, mode: 'bus', legs: [l1, l2], depart_at: l1.depart_at, eta_at: l2.arrive_at, transfers: 1,
      is_multi_leg: true, seats_left: M.free[bus.id] ?? 0, accessible_seats_left: 1, is_full: (M.free[bus.id] ?? 0) < p.party, meets_deadline: dl === null || Date.parse(l2.arrive_at) <= dl, accessible: true,
    })
  }
  return out.sort((a, b) => Date.parse(a.eta_at) - Date.parse(b.eta_at))
}

function score(p: MPax) {
  const w = M.rules.weights
  const waited = p.affectedAt ? Math.min(1, (Date.now() - p.affectedAt) / (120 * MIN)) : 0
  const dl = p.needs.connection_deadline_at ? Math.max(0, 1 - (Date.parse(p.needs.connection_deadline_at) - Date.now()) / (180 * MIN)) : 0
  const breakdown = {
    medical: p.needs.medical ? w.medical : 0, wheelchair: p.needs.wheelchair ? w.wheelchair : 0, elderly: p.needs.elderly ? w.elderly : 0,
    with_children: p.needs.with_children ? w.with_children : 0, deadline_urgency: +(dl * w.deadline_urgency).toFixed(1), wait_time: +(waited * w.wait_time).toFixed(1),
  }
  const total = +Object.values(breakdown).reduce((a, b) => a + b, 0).toFixed(1)
  const parts = Object.entries(breakdown).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${k.replace('_', ' ')} +${v}`)
  return { total, breakdown, explanation: `Priority ${total} = ${parts.join(', ') || 'no priority factors'}` }
}

function passengerOut(p: MPax): T.Passenger {
  return {
    id: p.id, name: p.name, email: p.email, phone: null, is_seeded: false, is_demo_persona: !!p.persona, hub: nodeByCode('POT'), destination: nodeByCode(p.destCode), party_size: p.party,
    needs: p.needs, allow_auto: p.allowAuto, state: p.state, ticket_id: p.ticketId, affected_at: p.affectedAt ? M.iso(p.affectedAt) : null,
  }
}
function allocOut(p: MPax, a: MAlloc): T.Allocation {
  const s = M.svc(a.serviceId)
  return { id: a.id, service: svcSummary(s), seat_count: p.party, seats: a.seats, choice_rank: a.rank, status: a.status, is_primary: a.status !== 'swap_held', hold_expires_at: a.holdExpires ? M.iso(a.holdExpires) : null, score: a.score, explanation: a.explanation }
}
function positions(p: MPax): T.WaitlistPosition[] {
  return p.waitlist.map((sid) => {
    const queue = [...M.pax.values()].filter((q) => q.waitlist.includes(sid)).sort((a, b) => score(b).total - score(a).total)
    const total = queue.length + 4 // plus background waitlist
    const pos = queue.findIndex((q) => q.id === p.id) + 1 + (sid === p.c1 ? 1 : 0)
    return { service_id: sid, label: M.svc(sid).label, position: Math.max(1, pos), total: Math.max(total, pos), is_swap: false }
  })
}
function headline(p: MPax): string {
  const a = p.alloc
  switch (p.state) {
    case 'HELD': return a?.rank === '1' ? 'Placed on your 1st choice ✓' : a?.rank === '2' ? 'Placed on your 2nd choice ✓' : a?.rank === 'cascade' ? 'A seat opened up for you!' : `Moved to ${M.svc(a!.serviceId).label} - see why`
    case 'CONFIRMED': return `You're confirmed ✓ - ${M.svc(a!.serviceId).label}`
    case 'REQUESTED': return "Request received - we'll allocate when the window closes"
    case 'WAITLISTED': { const w = positions(p)[0]; return w ? `Waitlisted #${w.position} for ${w.label}` : "You're on the waitlist" }
    case 'UNRESOLVED': return 'No seat yet - see your alternatives'
    case 'RESOLVED_ALT': return `Alternative chosen: ${p.resolvedAlt?.title ?? ''}`
    case 'AFFECTED': return 'Your trip was disrupted - choose an alternative'
    case 'REOFFER': return 'Your bus was re-routed - please choose again (you keep your seat until then)'
    default: return "On time - we'll alert you if anything changes."
  }
}
function statusOut(p: MPax): T.MyStatus {
  return {
    state: p.state, batch: p.state === 'REQUESTED' && M.batch ? batchOut() : null, allocation: p.alloc ? allocOut(p, p.alloc) : null, swap_offer: p.swap ? allocOut(p, p.swap) : null,
    waitlist: positions(p), resolved_alternative: p.resolvedAlt, headline: headline(p), server_time: M.iso(),
  }
}
function batchOut(): T.Batch {
  return { id: M.batch!.id, status: M.batch!.status, opens_at: M.iso(M.batch!.opens), closes_at: M.iso(M.batch!.closes) }
}
function notify(p: MPax, template: string, title: string, body: string) {
  const n = { id: M.id(), template, title, body, created_at: M.iso(), read: false }
  p.notifications.unshift(n)
  M.messages.unshift({ passenger_name: p.name, channel: 'email_sim', template, body, created_at: n.created_at })
  M.emit({ type: 'notification.created', data: n, aud: 'passengers', pax: [p.id] })
}
function audit(action: string, entity: string, explanation: string, actor: 'system' | 'operator' | 'passenger' = 'system') {
  M.audit.unshift({ id: M.id(), actor, action, entity_type: entity, entity_id: null, explanation, created_at: M.iso() })
}
function passengerOf(token: string | null): MPax {
  const p = [...M.pax.values()].find((x) => x.token === token)
  if (!p) throw err(401, 'UNAUTHORIZED', 'Session ended')
  return p
}

// ---------------------------------------------------------------- domain actions
function newPassenger(base: Partial<MPax> & { name: string; email: string; destCode: string }): MPax {
  const id = M.id()
  const p: MPax = {
    id, persona: null, party: 1, needs: { wheelchair: false, elderly: false, with_children: false, medical: false, connection_deadline_at: null }, allowAuto: true,
    state: M.cancelled ? 'AFFECTED' : 'BOOKED', affectedAt: M.cancelled ? Date.now() : null, ticketId: 'VT-' + Math.random().toString(16).slice(2, 8).toUpperCase(),
    c1: null, c2: null, any: false, alloc: null, swap: null, waitlist: [], resolvedAlt: null, notifications: [], podId: null, token: 'mock-p-' + id, ...base,
  }
  M.pax.set(id, p)
  return p
}
function claimPersona(pd: typeof PERSONAS[number]): MPax {
  const needs = { wheelchair: false, elderly: false, with_children: false, medical: false, connection_deadline_at: pd.deadlineMin ? M.iso(M.t0 + pd.deadlineMin * MIN) : null, ...pd.needs }
  const p = newPassenger({ name: pd.name, email: pd.email, destCode: pd.dest, party: pd.party, needs, persona: pd })
  M.claimed.set(pd.id, p.id)
  M.emit({ type: 'persona.claimed', data: { persona_id: pd.id }, aud: 'ops' })
  M.emit({ type: 'passenger.registered', data: { passenger: passengerOut(p), is_demo_persona: true }, aud: 'ops' })
  return p
}
const personaOut = (pd: typeof PERSONAS[number]): T.Persona => ({
  id: pd.id, title: pd.title, emoji: pd.emoji, summary: pd.summary, destination: nodeByCode(pd.dest), party_size: pd.party,
  needs: { wheelchair: false, elderly: false, with_children: false, medical: false, connection_deadline_at: pd.deadlineMin ? M.iso(M.t0 + pd.deadlineMin * MIN) : null, ...pd.needs }, is_taken: M.claimed.has(pd.id),
})

function refreshKpis(extra?: Partial<T.Kpis>) {
  const k = M.kpis
  Object.assign(k, extra)
  k.batch = M.batch && M.batch.status === 'open' ? batchOut() : null
  const judges = [...M.pax.values()]
  const c = (s: T.PassengerState) => judges.filter((p) => p.state === s).length
  k.not_checked_in = judges.filter((p) => p.state === 'AFFECTED').length + (M.cancelled ? 3 : 0)
  M.emit({ type: 'kpi.updated', data: { ...k }, aud: 'ops' })
  return c
}

function openBatch() {
  if (M.batch?.status === 'open') return M.batch
  const now = Date.now()
  M.batch = { id: M.id(), opens: now, closes: now + M.config.batch_window_seconds * 1000, status: 'open' }
  M.emit({ type: 'batch.opened', data: { batch_id: M.batch.id, closes_at: M.iso(M.batch.closes) }, aud: 'all' })
  if (M.batchTimer) clearTimeout(M.batchTimer)
  M.batchTimer = setTimeout(() => {
    if (M.batch?.status === 'open' && M.config.auto_run_on_batch_close) runAllocation()
    else if (M.batch?.status === 'open') closeBatch()
  }, M.config.batch_window_seconds * 1000)
  return M.batch
}
function closeBatch() {
  if (!M.batch || M.batch.status !== 'open') throw err(409, 'INVALID_STATE', 'There is no open batch')
  M.batch.status = 'closed'
  M.emit({ type: 'batch.closed', data: { batch_id: M.batch.id, closes_at: M.iso() }, aud: 'all' })
  return batchOut()
}

function scheduleHold(p: MPax, a: MAlloc) {
  if (!a.holdExpires) return
  const left = a.holdExpires - Date.now()
  if (left > 31_000) {
    M.later(left - 30_000, () => {
      if (p.alloc === a && a.status === 'held') M.emit({ type: 'hold.expiring', data: { allocation_id: a.id, seconds_left: 30 }, aud: 'passengers', pax: [p.id] })
    })
  }
  M.later(left, () => {
    if (p.alloc === a && a.status === 'held') {
      M.free[a.serviceId] += p.party
      p.alloc = null
      p.state = 'UNRESOLVED'
      M.emit({ type: 'hold.expired', data: { allocation_id: a.id }, aud: 'passengers', pax: [p.id] })
      M.emit({ type: 'seat.released', data: { service_id: a.serviceId, count: p.party }, aud: 'ops' })
      notify(p, 'expired', 'Your hold expired', `Your hold on ${M.svc(a.serviceId).label} expired and the seat was released.`)
      cascade(a.serviceId)
    }
  })
}

function place(p: MPax, serviceId: number, rank: MAlloc['rank'], why: string) {
  const n = p.party
  M.free[serviceId] -= n
  const seats = Array.from({ length: n }, (_, i) => (p.needs.wheelchair && i === 0 ? 'W01' : String(40 - M.free[serviceId] + i).padStart(3, '0')))
  const sc = score(p)
  const a: MAlloc = { id: M.id(), serviceId, seats, rank, status: 'held', holdExpires: Date.now() + M.config.hold_seconds * 1000, explanation: `${why} ${sc.explanation}; rules v${M.rules.version}.`, score: sc.total }
  p.alloc = a
  p.state = 'HELD'
  p.waitlist = []
  scheduleHold(p, a)
  return a
}

function runAllocation() {
  if (M.batch?.status === 'open') closeBatch()
  const started = Date.now()
  const runId = M.id()
  M.emit({ type: 'allocation.run_started', data: { run_id: runId }, aud: 'ops' })
  const units = [...M.pax.values()].filter((p) => p.state === 'REQUESTED').sort((a, b) => score(b).total - score(a).total)
  const stats = { units: 380 + units.length, placed_choice1: 231, placed_choice2: 24, placed_auto: 113, waitlisted: 6, unresolved: 2, duration_ms: 0, fill_rate_by_service: [] as any[] }
  for (const p of units) {
    const opts = optionsFor(p).filter((o) => o.meets_deadline)
    const order = [p.c1, p.c2].filter((x): x is number => !!x && opts.some((o) => o.request_service_id === x))
    if (p.any || (p.allowAuto && order.length < 2)) for (const o of opts) if (!order.includes(o.request_service_id)) order.push(o.request_service_id)
    let placed = false
    const reasons: string[] = []
    for (const sid of order) {
      const opt = opts.find((o) => o.request_service_id === sid)!
      if (!opt.is_full) {
        const rank = sid === p.c1 ? '1' : sid === p.c2 ? '2' : 'auto'
        const why = rank === '1' ? `Placed on your choice 1: ${M.svc(sid).label}.` : `${reasons.join(' ')} Placed on ${rank === '2' ? 'choice 2' : 'the best available option'}: ${M.svc(sid).label}.`
        const a = place(p, sid, rank, why)
        stats[rank === '1' ? 'placed_choice1' : rank === '2' ? 'placed_choice2' : 'placed_auto']++
        M.emit({ type: 'allocation.result', data: { state: 'HELD', allocation: allocOut(p, a), explanation: a.explanation }, aud: 'passengers', pax: [p.id] })
        notify(p, rank === 'auto' ? 'moved' : 'placed', rank === 'auto' ? 'You were moved' : 'You have a seat', `${M.svc(sid).label}: ${a.seats.join(', ')}. Accept within ${Math.round(M.config.hold_seconds / 60)} min.`)
        placed = true
        break
      }
      reasons.push(`Choice ${sid === p.c1 ? 1 : 2} ${M.svc(sid).label} full: last seats went to scores 31, 30, 30 (yours ${score(p).total}).`)
    }
    if (!placed) {
      const wl = [p.c1, p.c2].filter((x): x is number => !!x && !p.any)
      p.waitlist = wl
      p.state = wl.length ? 'WAITLISTED' : 'UNRESOLVED'
      stats.waitlisted += wl.length ? 1 : 0
      stats.unresolved += wl.length ? 0 : 1
      M.emit({ type: 'allocation.result', data: { state: p.state, allocation: null, explanation: reasons.join(' ') }, aud: 'passengers', pax: [p.id] })
      notify(p, wl.length ? 'waitlisted' : 'unresolved', wl.length ? "You're on the waitlist" : 'No seat yet', wl.length ? 'We will offer you a seat the moment one frees up.' : 'See your alternatives.')
    }
  }
  stats.duration_ms = Date.now() - started + 310
  stats.fill_rate_by_service = [...allServices()].filter((s) => s.inventory).map((s) => ({ service_id: s.id, label: s.label, fill_rate: s.seats ? Math.min(1, 1 - (M.free[s.id] ?? 0) / s.seats) : 0 }))
  if (M.batch) M.batch.status = 'allocated'
  M.runStats = { run_id: runId, stats }
  refreshKpis({ affected: 386, checked_in: 383, requested: 0, held: stats.placed_choice1 + stats.placed_choice2 + stats.placed_auto - 40, confirmed: 40, waitlisted: stats.waitlisted, unresolved: stats.unresolved, fill_rate: 0.97, avg_wait_min: 1.4, median_time_to_placement_min: 0.9 })
  audit('allocation.run', 'run', `Run #${runId}: ${stats.units} units, ${stats.placed_choice1} on 1st choice, ${stats.waitlisted} waitlisted.`)
  M.emit({ type: 'allocation.run_completed', data: { run_id: runId, stats }, aud: 'ops' })
  return M.runStats as { run_id: number; stats: T.RunStats }
}

function cascade(serviceId: number) {
  const next = [...M.pax.values()].filter((q) => q.state === 'WAITLISTED' && q.waitlist.includes(serviceId)).sort((a, b) => score(b).total - score(a).total)[0]
  if (!next || M.free[serviceId] < next.party) return
  const a = place(next, serviceId, 'cascade', `Seat freed on ${M.svc(serviceId).label}: you were the highest-priority feasible waitlisted unit.`)
  M.emit({ type: 'offer.created', data: { allocation: allocOut(next, a) }, aud: 'passengers', pax: [next.id] })
  notify(next, 'offer_cascade', 'A seat opened up for you!', `${M.svc(serviceId).label}: ${a.seats.join(', ')}.`)
  for (const q of M.pax.values()) if (q.waitlist.includes(serviceId)) M.emit({ type: 'waitlist.position_changed', data: { service_id: serviceId, position: 1, total: 5 }, aud: 'passengers', pax: [q.id] })
}

function createDisruption(b: T.DisruptionIn) {
  const id = M.id()
  let affected = 0
  let label = ''
  if (b.type === 'closure') {
    const e = M.edges.find((x) => x.id === b.edge_id)
    if (!e) throw err(404, 'NOT_FOUND', 'Unknown edge')
    e.is_closed = true
    const a = nodeById(e.from_node_id).code
    const c = nodeById(e.to_node_id).code
    label = `${e.road_name ?? e.mode}: ${nodeById(e.from_node_id).name} – ${nodeById(e.to_node_id).name}`
    if (e.mode === 'road') {
      for (const s of allServices().filter((x) => x.mode !== 'local_train' && x.stops.includes('URP') && x.stops.includes('VAN') && [a, c].includes('URP'))) {
        const detour = ['URP', 'NED', 'MUD', 'PER'].map((k) => [nodeByCode(k).lng, nodeByCode(k).lat] as [number, number])
        const stops = s.stops.filter((k: string) => k !== 'VAN')
        const coords: [number, number][] = []
        for (const k of stops) {
          if (k === 'PER' && stops.includes('URP')) coords.push(...detour.slice(1))
          else coords.push([nodeByCode(k).lng, nodeByCode(k).lat])
        }
        M.reroute[s.id] = { polyline: { type: 'LineString', coordinates: coords }, skipped: ['VAN'], extraMin: 12 }
        M.emit({ type: 'service.rerouted', data: { service_id: s.id, polyline: M.reroute[s.id].polyline, skipped_stops: [nodeByCode('VAN')] }, aud: 'all' })
        M.emit({ type: 'eta.updated', data: { service_id: s.id, eta_at: svcSummary(s).arrive_at }, aud: 'all' })
        M.emit({ type: 'service.status_changed', data: { service_id: s.id, status: 'rerouted', delay_minutes: 0 }, aud: 'all' })
        for (const p of M.pax.values()) {
          if (p.alloc?.serviceId === s.id) {
            affected++
            if (p.destCode === 'VAN') { p.state = 'REOFFER'; notify(p, 'reoffer', 'Please choose again', `${s.label} was re-routed and may miss your deadline.`) }
          }
        }
      }
      affected += 12
    }
  } else {
    const s = b.service_id != null ? M.svc(b.service_id) : undefined
    if (!s) throw err(404, 'NOT_FOUND', 'Unknown service')
    label = b.type === 'delay' ? `${s.label} (+${b.delay_minutes} min)` : s.label
    if (b.type === 'cancellation') M.cancelled = true
    else M.delayMin = b.delay_minutes ?? 25
    const crowd = b.type === 'cancellation' || (b.delay_minutes ?? 0) >= M.config.delay_threshold_minutes ? 383 : 41
    affected = crowd
    M.emit({ type: 'service.status_changed', data: { service_id: s.id, status: b.type === 'cancellation' ? 'cancelled' : 'delayed', delay_minutes: M.delayMin }, aud: 'all' })
    for (const p of M.pax.values()) {
      if (p.state === 'BOOKED' || p.state === 'REGISTERED') {
        p.state = 'AFFECTED'
        p.affectedAt = Date.now()
        affected++
        notify(p, 'disruption_alert', b.type === 'cancellation' ? 'Your train is cancelled' : 'Your train is delayed', `${b.reason || 'Service disruption'}. Choose an alternative now.`)
      }
    }
  }
  const d = { id, type: b.type, service_id: b.service_id ?? null, edge_id: b.edge_id ?? null, delay_minutes: b.delay_minutes ?? null, reason: b.reason, created_at: M.iso(), resolved_at: null }
  M.disruptions.unshift({ ...d, target_label: label, affected_count: affected })
  let batch: T.Batch | null = null
  if (b.type !== 'closure' || affected > 12) {
    openBatch()
    batch = batchOut()
  }
  M.emit({ type: 'disruption.created', data: { disruption: d }, aud: 'all' })
  const k = M.kpis
  refreshKpis(b.type === 'closure' ? {} : { affected: 386, checked_in: 12, not_checked_in: 374, requested: 380 })
  void k
  audit(`disruption.${b.type}`, 'disruption', `Operator created ${b.type} on ${label}: ${affected} passengers affected. ${b.reason}`, 'operator')
  return { disruption: d, affected_count: affected, batch }
}

function podOut(pod: any): T.Pod {
  return { ...pod, members: pod.members, seats_taken: pod.seats_taken }
}

// ---------------------------------------------------------------- router
type H = (ctx: { m: RegExpMatchArray; body: any; q: URLSearchParams; token: string | null; key?: string }) => any
const routes: { method: string; re: RegExp; h: H; auth: 'public' | 'passenger' | 'ops' }[] = []
const r = (method: string, path: string, auth: 'public' | 'passenger' | 'ops', h: H) => routes.push({ method, re: new RegExp(`^${path}$`), h, auth })

// public
r('GET', '/health', 'public', () => ({ status: 'ok', db: 'ok', version: '1.0.0-mock', server_time: M.iso() }))
r('GET', '/scenarios/active', 'public', () => ({ slug: M.scenarioSlug, name: M.scenarioSlug === 'potheri-demo' ? 'Potheri - Chengalpattu to Chennai Beach corridor' : 'Mumbai CSMT - Central line', default_hub: nodeByCode('POT'), join_url: `${location.origin}/demo-join?scenario=${M.scenarioSlug}`, demo_mode: true }))
r('GET', '/demo/personas', 'public', () => ({ items: PERSONAS.map(personaOut) }))
r('POST', '/hubs/nearby', 'public', ({ body }) => {
  const hubs = NODES.filter((n) => n.is_hub)
  if (typeof body.lat !== 'number') return { hubs: [{ hub: hubs[0], distance_km: null, is_default: true }], selected_hub_id: hubs[0].id, reason: 'default' }
  const d = (n: T.NodeRef) => Math.hypot((n.lat - body.lat) * 111, (n.lng - body.lng) * 108)
  const list = hubs.map((h) => ({ hub: h, distance_km: +d(h).toFixed(1), is_default: h.is_default_hub })).filter((x) => x.distance_km! <= 10).sort((a, b) => a.distance_km! - b.distance_km!)
  if (!list.length) return { hubs: [{ hub: hubs[0], distance_km: null, is_default: true }], selected_hub_id: hubs[0].id, reason: 'default' }
  return { hubs: list, selected_hub_id: (list.find((x) => x.is_default) ?? list[0]).hub.id, reason: 'nearest' }
})
r('GET', '/destinations', 'public', ({ q }) => {
  const s = (q.get('q') ?? '').toLowerCase()
  return { items: NODES.filter((n) => n.kind === 'rail_station' && n.code !== 'POT' && n.name.toLowerCase().includes(s)) }
})

// auth
r('POST', '/auth/demo-claim', 'public', ({ body }) => {
  let pd = PERSONAS.find((p) => p.id === body.persona_id)
  if (body.persona_id && (!pd || M.claimed.has(pd.id))) throw err(409, 'PERSONA_TAKEN', 'Someone just picked that one')
  if (!pd) pd = PERSONAS.filter((p) => !M.claimed.has(p.id))[0]
  if (!pd) {
    const p = newPassenger({ name: 'Surprise Traveller', email: `surprise-${M.id()}@demo.revior.test`, destCode: 'GND', persona: PERSONAS[0] })
    return { token: p.token, passenger: passengerOut(p), persona: personaOut(PERSONAS[0]) }
  }
  const p = claimPersona(pd)
  return { token: p.token, passenger: passengerOut(p), persona: personaOut(pd) }
})
r('POST', '/auth/register', 'public', ({ body }) => {
  if ([...M.pax.values()].some((p) => p.email === body.email)) throw err(409, 'EMAIL_TAKEN', 'That email is already registered')
  const dest = nodeById(body.destination_node_id)
  const p = newPassenger({ name: body.name, email: body.email, destCode: dest.code, party: body.party_size, needs: body.needs, allowAuto: body.allow_auto ?? true })
  M.emit({ type: 'passenger.registered', data: { passenger: passengerOut(p), is_demo_persona: false }, aud: 'ops' })
  return { token: p.token, passenger: passengerOut(p), ticket: { ticket_id: p.ticketId, service: svcSummary(SERVICES[0]) } }
})
r('POST', '/auth/login', 'public', ({ body }) => {
  const p = [...M.pax.values()].find((x) => x.email === body.email)
  const pd = PERSONAS.find((x) => x.email === body.email)
  if (p && body.password.length >= 6) return { token: p.token, passenger: passengerOut(p) }
  if (pd && body.password === 'revior-demo') { const q = claimPersona(pd); return { token: q.token, passenger: passengerOut(q) } }
  throw err(401, 'INVALID_CREDENTIALS', 'Wrong email or password')
})
r('POST', '/auth/qr-login', 'public', ({ body }) => {
  const p = [...M.pax.values()].find((x) => body.token === 'qr-' + x.id)
  if (!p) throw err(401, 'QR_TOKEN_INVALID', 'QR expired')
  return { token: p.token, passenger: passengerOut(p) }
})
r('POST', '/auth/ops-login', 'public', ({ body }) => {
  if (!body.password || body.password === 'wrong') throw err(401, 'INVALID_CREDENTIALS', 'Wrong operator password')
  return { token: 'mock-ops' }
})
r('POST', '/auth/logout', 'passenger', () => undefined)

// passenger
r('GET', '/me', 'passenger', ({ token }) => passengerOut(passengerOf(token)))
r('PATCH', '/me', 'passenger', ({ token, body }) => {
  const p = passengerOf(token)
  if (!['REGISTERED', 'BOOKED', 'AFFECTED'].includes(p.state)) throw err(409, 'INVALID_STATE', `Profile can't be changed while ${p.state}`)
  if (body.allow_auto !== undefined) p.allowAuto = body.allow_auto
  if (body.needs) p.needs = body.needs
  if (body.party_size) p.party = body.party_size
  if (body.destination_node_id) p.destCode = nodeById(body.destination_node_id).code
  return passengerOut(p)
})
r('GET', '/me/trip', 'passenger', ({ token }) => {
  const p = passengerOf(token)
  const t = svcSummary(SERVICES[0])
  const d = M.cancelled ? M.disruptions.find((x) => x.type !== 'closure') : null
  const mins = Math.round((Date.parse(t.depart_at) - Date.now()) / MIN)
  return {
    ticket: { ticket_id: p.ticketId, service: t },
    disruption: d ? { id: d.id, type: d.type, reason: d.reason, created_at: d.created_at } : null,
    headline: M.cancelled ? `Your train is cancelled${d?.reason ? ' - ' + d.reason : ''}` : M.delayMin ? `Your train is delayed by ${M.delayMin} min` : `On time — departs Potheri in ${Math.max(0, mins)} min. We'll alert you if anything changes.`,
  }
})
r('GET', '/me/options', 'passenger', ({ token }) => ({ items: optionsFor(passengerOf(token)), batch: M.batch?.status === 'open' ? batchOut() : null }))
r('POST', '/me/request', 'passenger', ({ token, body }) => {
  const p = passengerOf(token)
  if (!['AFFECTED', 'REQUESTED', 'REOFFER', 'WAITLISTED', 'UNRESOLVED'].includes(p.state)) throw err(409, 'INVALID_STATE', `You can't send a request while ${p.state}`)
  if (!body.choice1_service_id && !body.any_fastest) throw err(422, 'VALIDATION_ERROR', 'Pick at least one option', { fields: { choice1_service_id: 'required unless any_fastest' } })
  const batch = openBatch()
  p.c1 = body.choice1_service_id ?? null
  p.c2 = body.choice2_service_id ?? null
  p.any = !!body.any_fastest
  p.state = 'REQUESTED'
  p.waitlist = []
  refreshKpis()
  return { id: p.id, batch: { id: batch.id, status: batch.status, opens_at: M.iso(batch.opens), closes_at: M.iso(batch.closes) }, choice1_service_id: p.c1, choice2_service_id: p.c2, any_fastest: p.any }
})
r('GET', '/me/status', 'passenger', ({ token }) => statusOut(passengerOf(token)))
r('POST', '/me/allocation/accept', 'passenger', ({ token, body, key }) => {
  if (!key) throw err(422, 'VALIDATION_ERROR', 'Idempotency-Key header is required', { fields: { 'Idempotency-Key': 'required' } })
  const p = passengerOf(token)
  if (body.allocation_id && p.swap && p.swap.id === body.allocation_id) {
    const old = p.alloc
    if (old) { M.free[old.serviceId] += p.party; cascade(old.serviceId) }
    p.alloc = { ...p.swap, status: 'confirmed', holdExpires: null, rank: 'swap' }
    p.swap = null
    p.state = 'CONFIRMED'
  } else {
    if (!p.alloc || p.alloc.status !== 'held') throw err(409, 'INVALID_STATE', 'You have no held seat to act on')
    if (p.alloc.holdExpires && p.alloc.holdExpires < Date.now()) throw err(409, 'HOLD_EXPIRED', 'Your hold expired')
    p.alloc.status = 'confirmed'
    p.alloc.holdExpires = null
    p.state = 'CONFIRMED'
  }
  M.emit({ type: 'allocation.confirmed', data: { allocation_id: p.alloc!.id, passenger_id: p.id, service_id: p.alloc!.serviceId }, aud: 'ops' })
  M.kpis.confirmed++
  M.kpis.held = Math.max(0, M.kpis.held - 1)
  refreshKpis()
  audit('allocation.confirmed', 'allocation', `${p.name} accepted the hold on ${M.svc(p.alloc!.serviceId).label}.`, 'passenger')
  return statusOut(p)
})
r('POST', '/me/allocation/decline', 'passenger', ({ token, body, key }) => {
  if (!key) throw err(422, 'VALIDATION_ERROR', 'Idempotency-Key header is required', { fields: { 'Idempotency-Key': 'required' } })
  const p = passengerOf(token)
  const sw = p.swap
  if (body.allocation_id && sw && sw.id === body.allocation_id) {
    M.free[sw.serviceId] += p.party
    p.swap = null
    return statusOut(p)
  }
  if (!p.alloc) throw err(409, 'INVALID_STATE', 'You have no held seat to act on')
  if (p.alloc.status === 'confirmed') throw err(409, 'INVALID_STATE', "A confirmed seat can't be declined")
  const sid = p.alloc.serviceId
  M.free[sid] += p.party
  M.emit({ type: 'allocation.declined', data: { allocation_id: p.alloc.id, passenger_id: p.id, service_id: sid }, aud: 'ops' })
  M.emit({ type: 'seat.released', data: { service_id: sid, count: p.party }, aud: 'ops' })
  p.alloc = null
  p.state = 'UNRESOLVED'
  audit('allocation.declined', 'allocation', `${p.name} declined; seat released and cascaded.`, 'passenger')
  M.later(1200, () => cascade(sid))
  refreshKpis()
  return statusOut(p)
})
r('POST', '/me/swap', 'passenger', ({ token, body, key }) => {
  if (!key) throw err(422, 'VALIDATION_ERROR', 'Idempotency-Key header is required', { fields: { 'Idempotency-Key': 'required' } })
  const p = passengerOf(token)
  if (!p.alloc) throw err(409, 'INVALID_STATE', 'You can only request a swap while you hold a seat')
  M.later(5000, () => {
    if (!p.alloc || p.swap || (M.free[body.service_id] ?? 0) < p.party) return
    M.free[body.service_id] -= p.party
    p.swap = { id: M.id(), serviceId: body.service_id, seats: ['012'], rank: 'swap', status: 'swap_held', holdExpires: Date.now() + M.config.hold_seconds * 1000, explanation: `Swap seat on ${M.svc(body.service_id).label}.`, score: score(p).total }
    M.emit({ type: 'swap.offer_created', data: { allocation: allocOut(p, p.swap) }, aud: 'passengers', pax: [p.id] })
    notify(p, 'swap_offer', 'Your preferred option has a seat', `${M.svc(body.service_id).label} has a seat for you.`)
  })
  const st = statusOut(p)
  st.waitlist = [...st.waitlist, { service_id: body.service_id, label: M.svc(body.service_id).label, position: 1, total: 3, is_swap: true }]
  return st
})
r('POST', '/me/claim', 'passenger', ({ token, body, key }) => {
  if (!key) throw err(422, 'VALIDATION_ERROR', 'Idempotency-Key header is required', { fields: { 'Idempotency-Key': 'required' } })
  const p = passengerOf(token)
  if (!M.config.open_booking_enabled) throw err(409, 'INVALID_STATE', 'Open booking is not enabled')
  if ((M.free[body.service_id] ?? 0) < p.party) throw err(409, 'SEAT_UNAVAILABLE', 'That seat was just taken.')
  place(p, body.service_id, 'claim', `Open booking: claimed ${p.party} seat(s) on ${M.svc(body.service_id).label} instantly.`)
  return statusOut(p)
})
r('GET', '/me/why', 'passenger', ({ token }) => {
  const p = passengerOf(token)
  const sc = score(p)
  return { score: sc.total, breakdown: sc.breakdown, explanation: sc.explanation, decision_explanation: p.alloc?.explanation ?? (p.state === 'WAITLISTED' ? "Your choices are full. You're waitlisted." : null), rule_version: M.rules.version, weights: M.rules.weights, waitlist: positions(p) }
})
r('GET', '/me/alternatives', 'passenger', ({ token }) => {
  const p = passengerOf(token)
  const items: T.Alternative[] = []
  for (const o of optionsFor(p).filter((x) => !x.is_full && x.meets_deadline).slice(0, 3)) {
    items.push({ type: o.is_multi_leg ? 'MULTI_LEG' : 'LATER_SERVICE', ref: o.is_multi_leg ? `MULTI:${o.option_id}` : `SVC:${o.request_service_id}`, title: o.is_multi_leg ? 'Bus to Tambaram, then local onward' : `Service: ${o.label}`, description: `${o.seats_left} seats left.`, eta_at: o.eta_at, legs: o.legs, pod: null, requires_allocation: true })
  }
  for (const pod of M.pods.filter((x) => x.status === 'forming' && !x.memberIds.includes(p.id))) {
    items.push({ type: 'POD', ref: `POD:${pod.id}`, title: `Share a ${pod.mode} to ${pod.destination.name}`, description: `${pod.seats_taken}/${pod.capacity} seats taken.`, eta_at: M.iso(Date.now() + 40 * MIN), legs: [], pod: podOut(pod), requires_allocation: false })
  }
  items.push({ type: 'POD', ref: 'POD:NEW', title: `Start a shared cab to ${nodeByCode(p.destCode).name}`, description: 'Be the first in a new pod, split equally.', eta_at: M.iso(Date.now() + 50 * MIN), legs: [], pod: null, requires_allocation: false })
  if (M.delayMin) items.push({ type: 'WAIT_DELAYED', ref: 'WAIT:1', title: 'Wait for your delayed train', description: `Your train is ${M.delayMin} min late.`, eta_at: M.iso(M.t0 + (20 + 52 + M.delayMin) * MIN), legs: [legOf(SERVICES[0], 'POT', p.destCode)], pod: null, requires_allocation: false })
  items.push({ type: 'ALT_HUB', ref: 'HUB:2:3', title: 'Go to Kattankulathur (28 min away)', description: 'A later local leaves there at 19:12.', eta_at: M.iso(Date.now() + 70 * MIN), legs: [legOf(SERVICES[7], 'POT', p.destCode)], pod: null, requires_allocation: false })
  return { items: items.sort((a, b) => Date.parse(a.eta_at ?? '9999') - Date.parse(b.eta_at ?? '9999')) }
})
r('POST', '/me/alternatives/accept', 'passenger', ({ token, body }) => {
  const p = passengerOf(token)
  if (body.type === 'POD') {
    const found = body.ref === 'POD:NEW' ? undefined : M.pods.find((x) => `POD:${x.id}` === body.ref)
    if (found) joinPod(p, found)
    const pod = found ?? makePod(p, p.destCode, 'cab')!
    p.resolvedAlt = { type: 'POD', ref: `POD:${pod.id}`, title: `Shared ${pod.mode} to ${pod.destination.name}`, description: `${pod.seats_taken}/${pod.capacity} seats`, eta_at: null, legs: [], pod: podOut(pod), requires_allocation: false }
  } else {
    p.resolvedAlt = { type: body.type, ref: body.ref, title: body.type === 'WAIT_DELAYED' ? 'Wait for the delayed train' : 'Nearby hub', description: '', eta_at: null, legs: [], pod: null, requires_allocation: false }
  }
  p.state = 'RESOLVED_ALT'
  refreshKpis()
  return statusOut(p)
})
function makePod(p: MPax, destCode: string, mode: 'cab' | 'auto') {
  const cap = mode === 'cab' ? 4 : 3
  const km = 24.6
  const pod: any = { id: M.id(), origin: nodeByCode('POT'), destination: nodeByCode(destCode), mode, capacity: cap, seats_taken: 0, status: 'forming', members: [], memberIds: [], route_km: km, fare_total: 0, fare_per_seat: 0 }
  M.pods.push(pod)
  joinPod(p, pod)
  return pod
}
function joinPod(p: MPax, pod: any) {
  if (pod.seats_taken + p.party > pod.capacity) throw err(409, 'POD_FULL', 'That pod is full')
  pod.memberIds.push(p.id)
  pod.members.push({ passenger_id: p.id, name: p.name, seat_count: p.party })
  pod.seats_taken += p.party
  pod.fare_total = +((mode(pod) === 'cab' ? 100 : 30) + (mode(pod) === 'cab' ? 18 : 15) * pod.route_km).toFixed(2)
  pod.fare_per_seat = +(pod.fare_total / pod.seats_taken).toFixed(2)
  if (pod.seats_taken >= pod.capacity) pod.status = 'confirmed'
  p.podId = pod.id
  M.emit({ type: 'pod.updated', data: { pod: podOut(pod) }, aud: 'all' })
}
const mode = (pod: any) => pod.mode as 'cab' | 'auto'
r('GET', '/me/pods/suggested', 'passenger', ({ token }) => {
  const p = passengerOf(token)
  if (!M.pods.length) {
    const seed: any = { id: M.id(), origin: nodeByCode('POT'), destination: nodeByCode(p.destCode), mode: 'cab', capacity: 4, seats_taken: 2, status: 'forming', route_km: 24.6, fare_total: 542.8, fare_per_seat: 271.4, members: [{ passenger_id: 9001, name: 'Priya Iyer', seat_count: 1 }, { passenger_id: 9002, name: 'Dev Kumar', seat_count: 1 }], memberIds: [9001, 9002] }
    M.pods.push(seed)
  }
  return { items: M.pods.filter((x) => x.status === 'forming' && !x.memberIds.includes(p.id)).map(podOut) }
})
r('POST', '/me/pods', 'passenger', ({ token, body }) => podOut(makePod(passengerOf(token), nodeById(body.destination_node_id).code, body.mode)))
r('POST', '/pods/(\\d+)/join', 'passenger', ({ token, m, key }) => {
  if (!key) throw err(422, 'VALIDATION_ERROR', 'Idempotency-Key header is required', { fields: { 'Idempotency-Key': 'required' } })
  const pod = M.pods.find((x) => x.id === +m[1])
  if (!pod) throw err(404, 'NOT_FOUND', 'Unknown pod')
  joinPod(passengerOf(token), pod)
  return podOut(pod)
})
r('POST', '/pods/(\\d+)/leave', 'passenger', ({ token, m }) => {
  const p = passengerOf(token)
  const pod = M.pods.find((x) => x.id === +m[1])
  if (pod) {
    pod.memberIds = pod.memberIds.filter((i: number) => i !== p.id)
    pod.members = pod.members.filter((x: any) => x.passenger_id !== p.id)
    pod.seats_taken = pod.members.reduce((a: number, x: any) => a + x.seat_count, 0)
    pod.fare_per_seat = pod.seats_taken ? +(pod.fare_total / pod.seats_taken).toFixed(2) : pod.fare_total
    M.emit({ type: 'pod.updated', data: { pod: podOut(pod) }, aud: 'all' })
  }
  p.podId = null
  p.resolvedAlt = null
  p.state = 'UNRESOLVED'
  return undefined
})
r('POST', '/pods/(\\d+)/confirm', 'passenger', ({ m }) => {
  const pod = M.pods.find((x) => x.id === +m[1])
  if (!pod) throw err(404, 'NOT_FOUND', 'Unknown pod')
  if (pod.members.length < 2) throw err(409, 'INVALID_STATE', 'A pod needs at least 2 members to be confirmed')
  pod.status = 'confirmed'
  M.emit({ type: 'pod.updated', data: { pod: podOut(pod) }, aud: 'all' })
  return podOut(pod)
})
r('GET', '/me/login-qr', 'passenger', ({ token }) => ({ url: `${location.origin}/qr-login?t=qr-${passengerOf(token).id}`, expires_at: M.iso(Date.now() + 24 * 60 * MIN) }))
r('GET', '/me/notifications', 'passenger', ({ token }) => ({ items: passengerOf(token).notifications.slice(0, 50) }))
r('POST', '/me/notifications/read', 'passenger', ({ token, body }) => {
  passengerOf(token).notifications.forEach((n) => { if (body.ids.includes(n.id)) n.read = true })
  return undefined
})
r('POST', '/me/demo-switch', 'passenger', ({ token, body }) => {
  const p = passengerOf(token)
  const free = PERSONAS.filter((x) => !M.claimed.has(x.id))
  const pd = body.mode === 'pick' ? PERSONAS.find((x) => x.id === body.persona_id) : free[0]
  if (!pd || M.claimed.has(pd.id)) throw err(409, 'PERSONA_TAKEN', 'Someone just picked that one')
  if (p.persona) { M.claimed.delete(p.persona.id); M.emit({ type: 'persona.released', data: { persona_id: p.persona.id }, aud: 'ops' }) }
  p.token = 'revoked-' + p.token
  const q = claimPersona(pd)
  return { token: q.token, passenger: passengerOut(q), persona: personaOut(pd) }
})

// ops
r('GET', '/ops/scenarios', 'ops', () => ({ items: [{ slug: 'potheri-demo', name: 'Potheri - Chengalpattu to Chennai Beach corridor', is_active: M.scenarioSlug === 'potheri-demo' }, { slug: 'secondary-demo', name: 'Mumbai CSMT - Central line', is_active: M.scenarioSlug === 'secondary-demo' }] }))
r('POST', '/ops/scenarios/([\\w-]+)/activate', 'ops', ({ m }) => { M.scenarioSlug = m[1]; return { slug: m[1] } })
r('POST', '/ops/scenarios/([\\w-]+)/reset', 'ops', () => { M.reset(); return { duration_ms: 1210, counts: { passengers: 410, services: 25, personas: 10 } } })
r('GET', '/ops/scenarios/([\\w-]+)/config', 'ops', () => ({ ...M.config }))
r('PATCH', '/ops/scenarios/([\\w-]+)/config', 'ops', ({ body }) => { Object.assign(M.config, body); return { ...M.config } })
r('GET', '/ops/network', 'ops', () => ({ nodes: NODES, edges: M.edges }))
const opsServices = (): T.OpsService[] => allServices().map((s) => {
  const total = s.seats
  const free = M.free[s.id] ?? 0
  const held = [...M.pax.values()].filter((p) => p.alloc?.serviceId === s.id && p.alloc?.status === 'held').reduce((a, p) => a + p.party, 0)
  const conf = [...M.pax.values()].filter((p) => p.alloc?.serviceId === s.id && p.alloc?.status === 'confirmed').reduce((a, p) => a + p.party, 0)
  const base = Math.max(0, total - free - held - conf)
  const poly = M.reroute[s.id]?.polyline ?? lineOf(s.stops)
  return { ...svcSummary(s), total_seats: total, held: held + Math.round(base * 0.2), confirmed: conf + Math.round(base * 0.8), free, accessible_free: M.accFree[s.id] ?? 0, waitlist_len: [...M.pax.values()].filter((p) => p.waitlist.includes(s.id)).length, polyline: poly }
})
r('GET', '/ops/services', 'ops', () => ({ items: opsServices() }))
r('POST', '/ops/services', 'ops', ({ body }) => {
  const id = M.id()
  const s = { id, code: `OPS-${id}`, label: body.label, mode: body.mode, stops: body.stop_node_ids.map((i: number) => nodeById(i).code), departMin: (Date.now() - M.t0) / MIN + body.depart_in_minutes, durationMin: 50, seats: body.total_seats, accessibleSeats: body.accessible_seats, heldInit: 0, inventory: true }
  M.extraServices.push(s)
  M.free[id] = body.total_seats
  M.accFree[id] = body.accessible_seats
  M.emit({ type: 'service.status_changed', data: { service_id: id, status: 'scheduled', delay_minutes: 0 }, aud: 'ops' })
  M.later(1500, () => {
    for (const p of [...M.pax.values()].filter((x) => ['WAITLISTED', 'UNRESOLVED'].includes(x.state))) {
      if (M.free[id] >= p.party && nodeByCode(p.destCode) && s.stops.includes(p.destCode)) {
        const a = place(p, id, 'auto', `Placed on the new capacity ${s.label}.`)
        M.emit({ type: 'allocation.result', data: { state: 'HELD', allocation: allocOut(p, a), explanation: a.explanation }, aud: 'passengers', pax: [p.id] })
      }
    }
    refreshKpis({ waitlisted: Math.max(0, M.kpis.waitlisted - 3), unresolved: Math.max(0, M.kpis.unresolved - 2) })
  })
  return svcSummary(s)
})
r('GET', '/ops/disruptions/preview', 'ops', ({ q }) => {
  const type = q.get('type')
  const n = type === 'closure' ? 12 : type === 'delay' && +(q.get('delay_minutes') ?? 0) < 20 ? 41 : 386
  const dests = [['TAM', 0.26], ['GND', 0.2], ['TIR', 0.15], ['BCH', 0.16], ['CHR', 0.12], ['EGM', 0.11]] as const
  return { affected_count: n, by_destination: dests.map(([c, f]) => ({ destination: nodeByCode(c), count: Math.round(n * f) })) }
})
r('POST', '/ops/disruptions', 'ops', ({ body }) => createDisruption(body))
r('GET', '/ops/disruptions', 'ops', () => ({ items: M.disruptions.map((d) => ({ id: d.id, type: d.type, target_label: d.target_label, reason: d.reason, created_at: d.created_at, resolved_at: d.resolved_at, affected_count: d.affected_count })) }))
r('POST', '/ops/disruptions/(\\d+)/resolve', 'ops', ({ m }) => {
  const d = M.disruptions.find((x) => x.id === +m[1])
  if (!d) throw err(404, 'NOT_FOUND', 'Unknown disruption')
  d.resolved_at = M.iso()
  if (d.edge_id) { const e = M.edges.find((x) => x.id === d.edge_id); if (e) e.is_closed = false }
  if (d.type === 'cancellation') M.cancelled = false
  if (d.type === 'delay') M.delayMin = 0
  M.emit({ type: 'disruption.resolved', data: { disruption: d }, aud: 'all' })
  return { id: d.id, resolved_at: d.resolved_at }
})
r('GET', '/ops/batches/current', 'ops', () => ({ batch: M.batch && M.batch.status !== 'allocated' ? batchOut() : null, request_count: 380 + [...M.pax.values()].filter((p) => p.state === 'REQUESTED').length }))
r('POST', '/ops/batches/current/close', 'ops', () => closeBatch())
r('POST', '/ops/allocation/run', 'ops', () => runAllocation())
r('GET', '/ops/kpis', 'ops', () => { M.kpis.batch = M.batch?.status === 'open' ? batchOut() : null; return { ...M.kpis } })
r('GET', '/ops/invariants', 'ops', () => ({ over_allocated_services: 0, multi_primary_passengers: 0, negative_free_seats: 0, ok: true }))
r('GET', '/ops/map', 'ops', () => ({
  nodes: NODES, edges: M.edges, services: opsServices().map((s) => ({ id: s.id, label: s.label, mode: s.mode, status: s.status, polyline: s.polyline })),
  vehicles: mockVehicles(), clusters: [['TAM', 98], ['GND', 77], ['TIR', 58], ['BCH', 61], ['CHR', 45], ['EGM', 41]].map(([c, n]) => ({ node_id: nodeByCode(c as string).id, size: M.cancelled ? (n as number) : 0 })).filter((c) => c.size),
}))
export function mockVehicles(): T.VehiclePos[] {
  const out: T.VehiclePos[] = []
  const el = (Date.now() - M.t0) / MIN
  for (const s of allServices()) {
    const f = Math.min(1, Math.max(0, ((el - s.departMin) * M.config.sim_speed) / s.durationMin))
    if (f <= 0 || f >= 1 || svcStatus(s.id) === 'cancelled') continue
    const pts = (M.reroute[s.id]?.polyline ?? lineOf(s.stops)).coordinates
    const seg = f * (pts.length - 1)
    const i = Math.min(pts.length - 2, Math.floor(seg))
    const t = seg - i
    out.push({ service_id: s.id, lat: pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t, lng: pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t, progress: +f.toFixed(4) })
  }
  return out
}
r('GET', '/ops/capacity', 'ops', () => ({ items: opsServices().filter((s) => s.total_seats > 0).map((s) => ({ service: { ...s, polyline: undefined } as any, total_seats: s.total_seats, held: s.held, confirmed: s.confirmed, free: s.free, accessible_free: s.accessible_free, waitlist_len: s.waitlist_len })) }))
r('GET', '/ops/clusters', 'ops', () => ({ items: M.cancelled ? [['TAM', 98, 'general'], ['GND', 77, 'general'], ['TIR', 58, 'priority'], ['BCH', 61, 'general'], ['CHR', 45, 'priority'], ['EGM', 41, 'accessible']].map(([c, n, k], i) => ({ id: `${c}-${k}`, destination: nodeByCode(c as string), time_bucket_start: M.iso(M.t0 + 30 * MIN), needs_class: k as T.NeedsClass, size: n as number, demand_seats: Math.round((n as number) * 1.3), capacity_seats: i % 3 === 2 ? 60 : 160 })) : [] }))
r('GET', '/ops/allocations', 'ops', ({ q }) => {
  const names = ['Arun Kumar', 'Priya Iyer', 'Karthik Raj', 'Divya Nair', 'Suresh Pillai', 'Meena Rao', 'Ravi Menon', 'Lakshmi Babu', 'Vijay Gopal', 'Kavitha Balan']
  const rows: T.AllocationRow[] = [...M.pax.values()].filter((p) => p.alloc).map((p) => ({ passenger: { id: p.id, name: p.name, party_size: p.party, needs: p.needs }, score: p.alloc!.score, choice_rank: p.alloc!.rank, service_label: M.svc(p.alloc!.serviceId).label, status: p.alloc!.status as T.AllocationStatus, hold_expires_at: p.alloc!.holdExpires ? M.iso(p.alloc!.holdExpires) : null, explanation: p.alloc!.explanation }))
  if (M.runStats) for (let i = 0; i < 38; i++) rows.push({ passenger: { id: 5000 + i, name: names[i % 10] + ' ' + (i + 1), party_size: i % 7 === 0 ? 3 : 1, needs: { wheelchair: i % 13 === 0, elderly: i % 9 === 0, with_children: i % 8 === 0, medical: i % 17 === 0, connection_deadline_at: null } }, score: +(31 - i * 0.7).toFixed(1), choice_rank: i % 5 === 0 ? '2' : '1', service_label: SERVICES[1 + (i % 6)].label, status: i % 4 === 0 ? 'confirmed' : 'held', hold_expires_at: i % 4 === 0 ? null : M.iso(Date.now() + 90_000), explanation: 'Placed on your choice 1. Priority from need, waiting time and connection deadline; ticket price is never used.' })
  const status = q.get('status')
  const flt = rows.filter((x) => (!status || status === 'all' || x.status === status) && (!q.get('q') || x.passenger.name.toLowerCase().includes(q.get('q')!.toLowerCase())))
  const page = +(q.get('page') ?? 1)
  const size = +(q.get('page_size') ?? 25)
  return { items: flt.slice((page - 1) * size, page * size), page, page_size: size, total: flt.length }
})
r('GET', '/ops/unresolved', 'ops', () => ({
  items: [...M.pax.values()].filter((p) => p.state === 'UNRESOLVED').map((p) => ({ passenger: passengerOut(p), waited_min: p.affectedAt ? +((Date.now() - p.affectedAt) / MIN).toFixed(1) : 0, alternatives: [] })),
}))
r('GET', '/ops/fairness', 'ops', () => ({
  by_needs_class: [{ needs_class: 'accessible', placement_rate: 1, wait_p50: 1.1, wait_p90: 2.3 }, { needs_class: 'priority', placement_rate: 0.98, wait_p50: 1.2, wait_p90: 3 }, { needs_class: 'general', placement_rate: 0.93, wait_p50: 1.8, wait_p90: 5.6 }],
  by_destination: ['TAM', 'CHR', 'TIR', 'GND', 'EGM', 'BCH'].map((c, i) => ({ destination: nodeByCode(c), placement_rate: [0.97, 0.96, 0.94, 0.95, 0.92, 0.81][i], unresolved: i === 5 ? 3 : 0 })), wait_gini: 0.18,
}))
r('GET', '/ops/passengers/(\\d+)', 'ops', ({ m }) => {
  const p = M.pax.get(+m[1])
  if (!p) throw err(404, 'NOT_FOUND', 'Unknown passenger')
  const sc = score(p)
  return { passenger: passengerOut(p), status: statusOut(p), why: { score: sc.total, breakdown: sc.breakdown, explanation: sc.explanation, decision_explanation: p.alloc?.explanation ?? null, rule_version: M.rules.version, weights: M.rules.weights, waitlist: positions(p) } }
})
r('GET', '/ops/passengers/(\\d+)/login-qr', 'ops', ({ m }) => ({ url: `${location.origin}/qr-login?t=qr-${m[1]}`, expires_at: M.iso(Date.now() + 24 * 60 * MIN) }))
r('GET', '/ops/rules', 'ops', () => ({ active: { version: M.rules.version, weights: M.rules.weights }, history: [{ version: 1, weights: { medical: 30, wheelchair: 30, elderly: 15, with_children: 10, deadline_urgency: 20, wait_time: 20 }, created_at: M.iso(M.t0) }, ...M.rules.history].sort((a, b) => b.version - a.version) }))
r('POST', '/ops/rules/preview', 'ops', ({ body }) => {
  const d = (body.weights.medical ?? 30) - M.rules.weights.medical
  return { placed_delta: d > 0 ? 2 : d < 0 ? -1 : 0, by_needs_class: [{ needs_class: 'accessible', placement_rate_before: 1, placement_rate_after: 1 }, { needs_class: 'priority', placement_rate_before: 0.9, placement_rate_after: d > 0 ? 0.96 : 0.9 }, { needs_class: 'general', placement_rate_before: 0.93, placement_rate_after: d > 0 ? 0.91 : 0.93 }], movers: d === 0 ? [] : [{ passenger_id: 5001, name: 'Meena Rao', service_label: SERVICES[1].label, position_before: 4, position_after: 2 }, { passenger_id: 5002, name: 'Ravi Menon', service_label: SERVICES[1].label, position_before: 2, position_after: 3 }, { passenger_id: 5003, name: 'Divya Nair', service_label: SERVICES[2].label, position_before: 5, position_after: 3 }] }
})
r('POST', '/ops/rules/apply', 'ops', ({ body }) => {
  M.rules.version += 1
  M.rules.weights = { ...M.rules.weights, ...body.weights }
  M.rules.history.push({ version: M.rules.version, weights: M.rules.weights, created_at: M.iso() })
  M.emit({ type: 'rules.updated', data: { version: M.rules.version }, aud: 'all' })
  for (const p of M.pax.values()) if (p.waitlist.length) M.emit({ type: 'waitlist.position_changed', data: { service_id: p.waitlist[0], position: Math.max(1, positions(p)[0].position - 1), total: 6 }, aud: 'passengers', pax: [p.id] })
  audit('rules.applied', 'rules', `Operator applied priority rules v${M.rules.version}.`, 'operator')
  return { version: M.rules.version }
})
r('GET', '/ops/audit', 'ops', () => { const items = M.audit.slice(); return { items: items.slice(0, 50), page: 1, page_size: 50, total: items.length } })
r('GET', '/ops/notifications', 'ops', () => ({ items: M.messages.slice(0, 50), page: 1, page_size: 50, total: M.messages.length }))
r('POST', '/ops/open-booking', 'ops', ({ body }) => { M.config.open_booking_enabled = body.enabled; return { enabled: body.enabled } })
r('GET', '/ops/demo/personas', 'ops', () => ({ items: PERSONAS.map((pd) => { const pid = M.claimed.get(pd.id); const p = pid ? M.pax.get(pid) : null; return { ...personaOut(pd), claimed_at: pid ? M.iso(Date.now() - 60_000) : null, state: (p?.state ?? 'BOOKED') as T.PassengerState } }) }))
r('POST', '/ops/demo/personas/(\\d+)/release', 'ops', ({ m }) => { const pid = M.claimed.get(+m[1]); if (pid) { const p = M.pax.get(pid); if (p) p.token = 'revoked-' + p.token; M.claimed.delete(+m[1]); M.emit({ type: 'persona.released', data: { persona_id: +m[1] }, aud: 'ops' }) } return undefined })
r('POST', '/ops/demo/personas/release-all', 'ops', () => { for (const id of [...M.claimed.keys()]) { const p = M.pax.get(M.claimed.get(id)!); if (p) p.token = 'revoked-' + p.token; M.claimed.delete(id); M.emit({ type: 'persona.released', data: { persona_id: id }, aud: 'ops' }) } return undefined })
r('POST', '/ops/stress/run', 'ops', ({ body }) => {
  const total = body.requests
  let sent = 0
  const tick = () => {
    sent = Math.min(total, sent + Math.ceil(total / 10))
    M.emit({ type: 'stress.progress', data: { sent, ok: Math.min(sent, body.seats + 5), conflicts: Math.max(0, sent - body.seats - 5), errors: 0 }, aud: 'ops' })
    if (sent < total) M.later(350, tick)
    else M.emit({ type: 'stress.result', data: { total, confirmed: body.seats, capacity: body.seats, over_allocations: 0, five_xx: 0, passed: true }, aud: 'ops' })
  }
  M.later(300, tick)
  return { run_id: 'stress-mock' }
})

export async function mockRequest<TRes>(_kind: string, method: string, pathWithQuery: string, body: unknown, token: string | null, key?: string): Promise<TRes> {
  await delay()
  const [path, query = ''] = pathWithQuery.split('?')
  const q = new URLSearchParams(query)
  for (const rt of routes) {
    if (rt.method !== method) continue
    const m = path.match(rt.re)
    if (!m) continue
    if (rt.auth === 'ops' && token !== 'mock-ops') throw err(token ? 403 : 401, token ? 'FORBIDDEN' : 'UNAUTHORIZED', 'Operator token required')
    if (rt.auth === 'passenger' && !token) throw err(401, 'UNAUTHORIZED', 'Missing bearer token')
    return (await rt.h({ m, body: body ?? {}, q, token, key })) as TRes
  }
  throw err(404, 'NOT_FOUND', `No mock for ${method} ${path}`)
}
export { CHAIN }
