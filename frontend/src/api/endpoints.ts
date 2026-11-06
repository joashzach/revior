// One function per endpoint (contract §5). Mock or real is decided inside http.request().
import { env } from '@/config/env'
import { get, patch, post } from './http'
import type * as T from './types'

const scenario = env.scenario

// ---- public (contract §5.1, §5.3, §5.4)
export const publicApi = {
  health: () => get<T.Health>('public', '/health'),
  activeScenario: () => get<T.ActiveScenario>('public', '/scenarios/active'),
  personas: () => get<{ items: T.Persona[] }>('public', '/demo/personas', { scenario }),
  hubsNearby: (lat?: number, lng?: number) => post<T.HubsNearby>('public', '/hubs/nearby', { scenario, lat, lng }),
  destinations: (hub?: number, q?: string) => get<{ items: T.NodeRef[] }>('public', '/destinations', { scenario, hub, q }),
}

// ---- auth (§5.2, §5.3)
export const authApi = {
  demoClaim: (body: { persona_id?: number; surprise?: boolean }) => post<T.DemoClaimResult>('public', '/auth/demo-claim', { scenario, ...body }),
  register: (body: T.RegisterBody) => post<T.RegisterResult>('public', '/auth/register', { scenario, ...body }),
  login: (email: string, password: string) => post<T.AuthResult>('public', '/auth/login', { scenario, email, password }),
  qrLogin: (token: string) => post<T.AuthResult>('public', '/auth/qr-login', { token }),
  opsLogin: (password: string) => post<{ token: string }>('public', '/auth/ops-login', { password }),
  logout: () => post<void>('passenger', '/auth/logout'),
}

// ---- passenger (§5.5)
export const meApi = {
  me: () => get<T.Passenger>('passenger', '/me'),
  patch: (body: Partial<{ destination_node_id: number; hub_node_id: number; needs: T.Needs; party_size: number; allow_auto: boolean }>) =>
    patch<T.Passenger>('passenger', '/me', body),
  trip: () => get<T.TripOut>('passenger', '/me/trip'),
  options: () => get<{ items: T.Option[]; batch: T.Batch | null }>('passenger', '/me/options'),
  request: (body: { choice1_service_id?: number | null; choice2_service_id?: number | null; any_fastest: boolean }) =>
    post<T.RequestOut>('passenger', '/me/request', body),
  status: () => get<T.MyStatus>('passenger', '/me/status'),
  accept: (key: string, allocation_id?: number) => post<T.MyStatus>('passenger', '/me/allocation/accept', allocation_id ? { allocation_id } : {}, key),
  decline: (key: string, allocation_id?: number) => post<T.MyStatus>('passenger', '/me/allocation/decline', allocation_id ? { allocation_id } : {}, key),
  swap: (key: string, service_id: number) => post<T.MyStatus>('passenger', '/me/swap', { service_id }, key),
  claim: (key: string, service_id: number) => post<T.MyStatus>('passenger', '/me/claim', { service_id }, key),
  why: () => get<T.Why>('passenger', '/me/why'),
  alternatives: () => get<{ items: T.Alternative[] }>('passenger', '/me/alternatives'),
  acceptAlternative: (type: T.AlternativeType, ref: string) => post<T.MyStatus>('passenger', '/me/alternatives/accept', { type, ref }),
  podsSuggested: () => get<{ items: T.Pod[] }>('passenger', '/me/pods/suggested'),
  createPod: (destination_node_id: number, mode: 'cab' | 'auto') => post<T.Pod>('passenger', '/me/pods', { destination_node_id, mode }),
  joinPod: (id: number, key: string) => post<T.Pod>('passenger', `/pods/${id}/join`, {}, key),
  leavePod: (id: number) => post<void>('passenger', `/pods/${id}/leave`),
  confirmPod: (id: number) => post<T.Pod>('passenger', `/pods/${id}/confirm`),
  loginQr: () => get<{ url: string; expires_at: string }>('passenger', '/me/login-qr'),
  notifications: () => get<{ items: T.NotificationItem[] }>('passenger', '/me/notifications'),
  markRead: (ids: number[]) => post<void>('passenger', '/me/notifications/read', { ids }),
  demoSwitch: (mode: 'next' | 'pick', persona_id?: number) => post<T.DemoClaimResult>('passenger', '/me/demo-switch', { mode, persona_id }),
}

// ---- operator (§5.6)
export const opsApi = {
  scenarios: () => get<{ items: { slug: string; name: string; is_active: boolean }[] }>('ops', '/ops/scenarios'),
  activate: (slug: string) => post<{ slug: string }>('ops', `/ops/scenarios/${slug}/activate`),
  reset: (slug: string) => post<{ duration_ms: number; counts: { passengers: number; services: number; personas: number } }>('ops', `/ops/scenarios/${slug}/reset`),
  config: (slug: string) => get<T.ScenarioConfig>('ops', `/ops/scenarios/${slug}/config`),
  patchConfig: (slug: string, body: Partial<T.ScenarioConfig>) => patch<T.ScenarioConfig>('ops', `/ops/scenarios/${slug}/config`, body),
  network: () => get<{ nodes: T.NodeRef[]; edges: T.NetworkEdge[] }>('ops', '/ops/network'),
  services: (q?: { status?: string; mode?: string }) => get<{ items: T.OpsService[] }>('ops', '/ops/services', q),
  addService: (body: T.AddServiceBody) => post<T.ServiceSummary>('ops', '/ops/services', body),
  disruptionPreview: (q: { type: T.DisruptionType; service_id?: number; edge_id?: number; delay_minutes?: number }) =>
    get<T.DisruptionPreview>('ops', '/ops/disruptions/preview', q),
  createDisruption: (body: T.DisruptionIn) =>
    post<{ disruption: any; affected_count: number; batch: T.Batch | null }>('ops', '/ops/disruptions', body),
  disruptions: () => get<{ items: T.DisruptionRow[] }>('ops', '/ops/disruptions'),
  resolveDisruption: (id: number) => post<{ id: number; resolved_at: string }>('ops', `/ops/disruptions/${id}/resolve`),
  batchCurrent: () => get<{ batch: T.Batch | null; request_count: number }>('ops', '/ops/batches/current'),
  closeBatch: () => post<T.Batch>('ops', '/ops/batches/current/close'),
  runAllocation: (mode: 'greedy' | 'ortools') => post<{ run_id: number; stats: T.RunStats }>('ops', '/ops/allocation/run', { mode }),
  kpis: () => get<T.Kpis>('ops', '/ops/kpis'),
  invariants: () => get<T.Invariants>('ops', '/ops/invariants'),
  clusters: () => get<{ items: T.ClusterRow[] }>('ops', '/ops/clusters'),
  capacity: () => get<{ items: T.CapacityRow[] }>('ops', '/ops/capacity'),
  allocations: (q: { status?: string; destination?: string; needs?: string; q?: string; page?: number; page_size?: number }) =>
    get<T.Paginated<T.AllocationRow>>('ops', '/ops/allocations', q),
  unresolved: () => get<{ items: T.UnresolvedRow[] }>('ops', '/ops/unresolved'),
  fairness: () => get<T.Fairness>('ops', '/ops/fairness'),
  map: () => get<T.OpsMap>('ops', '/ops/map'),
  passenger: (id: number) => get<T.PassengerDetail>('ops', `/ops/passengers/${id}`),
  passengerQr: (id: number) => get<{ url: string; expires_at: string }>('ops', `/ops/passengers/${id}/login-qr`),
  rules: () => get<T.RulesOut>('ops', '/ops/rules'),
  rulesPreview: (weights: Record<string, number>) => post<T.RulesPreview>('ops', '/ops/rules/preview', { weights }),
  rulesApply: (weights: Record<string, number>) => post<{ version: number }>('ops', '/ops/rules/apply', { weights }),
  audit: (q: { passenger_id?: number; entity?: string; page?: number }) => get<T.Paginated<T.AuditRow>>('ops', '/ops/audit', q),
  messages: (page = 1) => get<T.Paginated<T.MessageRow>>('ops', '/ops/notifications', { page }),
  openBooking: (enabled: boolean) => post<{ enabled: boolean }>('ops', '/ops/open-booking', { enabled }),
  demoPersonas: () => get<{ items: T.OpsPersona[] }>('ops', '/ops/demo/personas'),
  releasePersona: (id: number) => post<void>('ops', `/ops/demo/personas/${id}/release`),
  releaseAll: () => post<void>('ops', '/ops/demo/personas/release-all'),
  stressRun: (requests: number, seats: number) => post<{ run_id: string }>('ops', '/ops/stress/run', { requests, seats }),
}
