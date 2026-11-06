import { qk } from '@/api/queryKeys'
import type { QueryKey } from '@tanstack/react-query'

export type EventType =
  | 'service.status_changed' | 'disruption.created' | 'disruption.resolved' | 'batch.opened' | 'batch.closed'
  | 'allocation.run_started' | 'allocation.run_completed' | 'allocation.result' | 'offer.created'
  | 'swap.offer_created' | 'hold.expiring' | 'hold.expired' | 'allocation.confirmed' | 'allocation.declined'
  | 'seat.released' | 'waitlist.position_changed' | 'eta.updated' | 'service.rerouted' | 'vehicle.positions'
  | 'kpi.updated' | 'rules.updated' | 'pod.updated' | 'passenger.registered' | 'persona.claimed'
  | 'persona.released' | 'notification.created' | 'stress.progress' | 'stress.result'

export const ALL_EVENT_TYPES: EventType[] = [
  'service.status_changed', 'disruption.created', 'disruption.resolved', 'batch.opened', 'batch.closed',
  'allocation.run_started', 'allocation.run_completed', 'allocation.result', 'offer.created', 'swap.offer_created',
  'hold.expiring', 'hold.expired', 'allocation.confirmed', 'allocation.declined', 'seat.released',
  'waitlist.position_changed', 'eta.updated', 'service.rerouted', 'vehicle.positions', 'kpi.updated', 'rules.updated',
  'pod.updated', 'passenger.registered', 'persona.claimed', 'persona.released', 'notification.created',
  'stress.progress', 'stress.result',
]

export type Audience = 'passenger' | 'ops'

/** PRD §6.3: which cached queries an event invalidates, per audience. Pure, so it is unit-tested. */
export function invalidationFor(type: string, audience: Audience): QueryKey[] {
  const o = qk.ops
  if (audience === 'passenger') {
    switch (type) {
      case 'service.status_changed': return [qk.trip, qk.options, qk.status]
      case 'disruption.created':
      case 'disruption.resolved': return [qk.trip, qk.options, qk.status, qk.me]
      case 'batch.opened':
      case 'batch.closed': return [qk.status, qk.options]
      case 'allocation.result': return [qk.status, qk.why, qk.me]
      case 'offer.created':
      case 'swap.offer_created':
      case 'hold.expired':
      case 'waitlist.position_changed': return [qk.status, qk.me]
      case 'eta.updated':
      case 'service.rerouted': return [qk.status, qk.trip]
      case 'rules.updated': return [qk.why, qk.status]
      case 'pod.updated': return [qk.pods, qk.alternatives, qk.status]
      case 'notification.created': return [qk.notifications]
      default: return []
    }
  }
  switch (type) {
    case 'service.status_changed': return [o.services, o.map, o.capacity]
    case 'disruption.created':
    case 'disruption.resolved': return [o.disruptions, o.kpis, o.map, o.services, o.batch, o.clusters]
    case 'batch.opened':
    case 'batch.closed': return [o.batch, o.kpis]
    case 'allocation.run_completed': return [o.capacity, o.allocations, o.kpis, o.clusters, o.unresolved, o.fairness, o.batch]
    case 'allocation.confirmed':
    case 'allocation.declined':
    case 'seat.released': return [o.capacity, o.allocations, o.kpis]
    case 'eta.updated': return [o.map, o.services]
    case 'service.rerouted': return [o.map, o.services, o.capacity]
    case 'rules.updated': return [o.rules, o.allocations]
    case 'pod.updated': return [o.unresolved]
    case 'persona.claimed':
    case 'persona.released':
    case 'passenger.registered': return [o.personas, o.kpis]
    default: return []
  }
}
