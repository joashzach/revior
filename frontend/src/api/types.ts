// Types copied from the API contract §4–§5 (single source). Shapes verified against backend/contracts/examples.

export type PassengerState =
  | 'REGISTERED' | 'BOOKED' | 'AFFECTED' | 'REQUESTED' | 'HELD' | 'CONFIRMED'
  | 'WAITLISTED' | 'UNRESOLVED' | 'RESOLVED_ALT' | 'REOFFER'
export type ServiceMode = 'local_train' | 'bus' | 'charter_bus' | 'shuttle'
export type ServiceStatus = 'scheduled' | 'delayed' | 'cancelled' | 'running' | 'completed' | 'rerouted'
export type AllocationStatus = 'held' | 'swap_held' | 'confirmed' | 'declined' | 'expired' | 'released'
export type ChoiceRank = '1' | '2' | 'auto' | 'cascade' | 'claim' | 'swap'
export type DisruptionType = 'cancellation' | 'delay' | 'closure'
export type BatchStatus = 'open' | 'closed' | 'allocated'
export type AlternativeType = 'LATER_SERVICE' | 'MULTI_LEG' | 'POD' | 'ALT_HUB' | 'WAIT_DELAYED'
export type PodStatus = 'forming' | 'full' | 'confirmed' | 'departed' | 'cancelled'
export type NeedsClass = 'accessible' | 'priority' | 'general'
export type NodeKind = 'rail_station' | 'bus_stop' | 'hub_only'

export interface Needs {
  wheelchair: boolean
  elderly: boolean
  with_children: boolean
  medical: boolean
  connection_deadline_at: string | null
}
export interface NodeRef {
  id: number
  code: string
  name: string
  lat: number
  lng: number
  kind: NodeKind
  is_hub: boolean
  is_default_hub: boolean
}
export interface ServiceSummary {
  id: number
  code: string
  label: string
  mode: ServiceMode
  status: ServiceStatus
  delay_minutes: number
  depart_at: string
  arrive_at: string
  origin: NodeRef
  destination: NodeRef
  accessible: boolean
}
export interface Passenger {
  id: number
  name: string
  email: string | null
  phone: string | null
  is_seeded: boolean
  is_demo_persona: boolean
  hub: NodeRef
  destination: NodeRef
  party_size: number
  needs: Needs
  allow_auto: boolean
  state: PassengerState
  ticket_id: string
  affected_at: string | null
}
export interface Ticket {
  ticket_id: string
  service: ServiceSummary
}
export interface Leg {
  service: ServiceSummary
  from: NodeRef
  to: NodeRef
  depart_at: string
  arrive_at: string
  has_seats: boolean
}
export interface Option {
  option_id: string
  request_service_id: number
  label: string
  mode: ServiceMode
  legs: Leg[]
  depart_at: string
  eta_at: string
  transfers: number
  is_multi_leg: boolean
  seats_left: number
  accessible_seats_left: number
  is_full: boolean
  meets_deadline: boolean
  accessible: boolean
}
export interface Batch {
  id: number
  status: BatchStatus
  opens_at: string
  closes_at: string
}
export interface RequestOut {
  id: number
  batch: Batch
  choice1_service_id: number | null
  choice2_service_id: number | null
  any_fastest: boolean
}
export interface Allocation {
  id: number
  service: ServiceSummary
  seat_count: number
  seats: string[]
  choice_rank: ChoiceRank
  status: AllocationStatus
  is_primary: boolean
  hold_expires_at: string | null
  score: number
  explanation: string
}
export interface WaitlistPosition {
  service_id: number
  label: string
  position: number
  total: number
  is_swap: boolean
}
export interface Pod {
  id: number
  origin: NodeRef
  destination: NodeRef
  mode: 'cab' | 'auto'
  capacity: number
  seats_taken: number
  status: PodStatus
  members: { passenger_id: number; name: string; seat_count: number }[]
  route_km: number
  fare_total: number
  fare_per_seat: number
}
export interface Alternative {
  type: AlternativeType
  ref: string
  title: string
  description: string
  eta_at: string | null
  legs: Leg[]
  pod: Pod | null
  requires_allocation: boolean
}
export interface MyStatus {
  state: PassengerState
  batch: Batch | null
  allocation: Allocation | null
  swap_offer: Allocation | null
  waitlist: WaitlistPosition[]
  resolved_alternative: Alternative | null
  headline: string
  server_time: string
}
export type WhyFeature = 'medical' | 'wheelchair' | 'elderly' | 'with_children' | 'deadline_urgency' | 'wait_time'
export interface Why {
  score: number
  breakdown: Record<WhyFeature, number>
  explanation: string
  decision_explanation: string | null
  rule_version: number
  weights: Record<string, number>
  waitlist: WaitlistPosition[]
}
export interface Persona {
  id: number
  title: string
  emoji: string
  summary: string
  destination: NodeRef
  party_size: number
  needs: Needs
  is_taken: boolean
}
export interface NotificationItem {
  id: number
  template: string
  title: string
  body: string
  created_at: string
  read: boolean
}

// ---- requests
export interface RegisterBody {
  scenario?: string
  name: string
  email: string
  password: string
  phone?: string
  hub_node_id?: number
  destination_node_id: number
  needs: Needs
  party_size: number
  allow_auto?: boolean
}
export interface AuthResult {
  token: string
  passenger: Passenger
}
export interface RegisterResult extends AuthResult {
  ticket: Ticket
}
export interface DemoClaimResult extends AuthResult {
  persona: Persona
}
export interface TripOut {
  ticket: Ticket
  disruption: { id: number; type: DisruptionType; reason: string; created_at: string } | null
  headline: string
}
export interface HubsNearby {
  hubs: { hub: NodeRef; distance_km: number | null; is_default: boolean }[]
  selected_hub_id: number
  reason: 'nearest' | 'default'
}
export interface ActiveScenario {
  slug: string
  name: string
  default_hub: NodeRef
  join_url: string
  demo_mode: boolean
}
export interface Health {
  status: string
  db: string
  version: string
  server_time: string
}

// ---- ops
export interface ScenarioConfig {
  batch_window_seconds: number
  hold_seconds: number
  auto_run_on_batch_close: boolean
  delay_threshold_minutes: number
  hub_radius_km: number
  open_booking_enabled: boolean
  sim_speed: number
  demo_mode: boolean
  join_qr_mode: 'corner' | 'fullscreen' | 'hidden'
}
export interface LineString {
  type: 'LineString'
  coordinates: [number, number][] // [lng, lat]
}
export interface NetworkEdge {
  id: number
  from_node_id: number
  to_node_id: number
  mode: 'rail' | 'road' | 'walk'
  road_name: string | null
  is_closed: boolean
  polyline: LineString
}
export interface OpsService extends ServiceSummary {
  total_seats: number
  held: number
  confirmed: number
  free: number
  accessible_free: number
  waitlist_len: number
  polyline: LineString
}
export interface DisruptionRow {
  id: number
  type: DisruptionType
  target_label: string
  reason: string
  created_at: string
  resolved_at: string | null
  affected_count: number
}
export interface DisruptionPreview {
  affected_count: number
  by_destination: { destination: NodeRef; count: number }[]
}
export interface DisruptionIn {
  type: DisruptionType
  service_id?: number
  edge_id?: number
  delay_minutes?: number
  reason: string
}
export interface RunStats {
  units: number
  placed_choice1: number
  placed_choice2: number
  placed_auto: number
  waitlisted: number
  unresolved: number
  duration_ms: number
  fill_rate_by_service: { service_id: number; label: string; fill_rate: number }[]
}
export interface Kpis {
  affected: number
  checked_in: number
  not_checked_in: number
  requested: number
  held: number
  confirmed: number
  waitlisted: number
  unresolved: number
  resolved_alt: number
  avg_wait_min: number
  median_time_to_placement_min: number
  fill_rate: number
  batch: Batch | null
}
export interface ClusterRow {
  id: string
  destination: NodeRef
  time_bucket_start: string
  needs_class: NeedsClass
  size: number
  demand_seats: number
  capacity_seats: number
}
export interface CapacityRow {
  service: ServiceSummary
  total_seats: number
  held: number
  confirmed: number
  free: number
  accessible_free: number
  waitlist_len: number
}
export interface Paginated<T> {
  items: T[]
  page: number
  page_size: number
  total: number
}
export interface AllocationRow {
  passenger: { id: number; name: string; party_size: number; needs: Needs }
  score: number
  choice_rank: ChoiceRank
  service_label: string
  status: AllocationStatus
  hold_expires_at: string | null
  explanation: string
}
export interface UnresolvedRow {
  passenger: Passenger
  waited_min: number
  alternatives: Alternative[]
}
export interface Fairness {
  by_needs_class: { needs_class: NeedsClass; placement_rate: number; wait_p50: number; wait_p90: number }[]
  by_destination: { destination: NodeRef; placement_rate: number; unresolved: number }[]
  wait_gini: number
}
export interface OpsMap {
  nodes: NodeRef[]
  edges: NetworkEdge[]
  services: { id: number; label: string; mode: ServiceMode; status: ServiceStatus; polyline: LineString }[]
  vehicles: VehiclePos[]
  clusters: { node_id: number; size: number }[]
}
export interface VehiclePos {
  service_id: number
  lat: number
  lng: number
  progress: number
}
export interface Invariants {
  over_allocated_services: number
  multi_primary_passengers: number
  negative_free_seats: number
  ok: boolean
}
export interface RulesOut {
  active: { version: number; weights: Record<string, number> }
  history: { version: number; weights: Record<string, number>; created_at: string }[]
}
export interface RulesPreview {
  placed_delta: number
  by_needs_class: { needs_class: NeedsClass; placement_rate_before: number; placement_rate_after: number }[]
  movers: { passenger_id: number; name: string; service_label: string; position_before: number; position_after: number }[]
}
export interface AuditRow {
  id: number
  actor: 'system' | 'operator' | 'passenger'
  action: string
  entity_type: string
  entity_id: number | null
  explanation: string
  created_at: string
}
export interface MessageRow {
  passenger_name: string
  channel: 'push' | 'email_sim' | 'sms_sim'
  template: string
  body: string
  created_at: string
}
export type OpsPersona = Persona & { claimed_at: string | null; state: PassengerState }
export interface AddServiceBody {
  label: string
  mode: 'charter_bus' | 'shuttle'
  stop_node_ids: number[]
  depart_in_minutes: number
  total_seats: number
  accessible_seats: number
}
export interface StressResult {
  total: number
  confirmed: number
  capacity: number
  over_allocations: number
  five_xx: number
  passed: boolean
}
export interface StressProgress {
  sent: number
  ok: number
  conflicts: number
  errors: number
}
export interface PassengerDetail {
  passenger: Passenger
  status: MyStatus
  why: Why
}

// ---- WebSocket envelope
export interface WsMessage<T = any> {
  type: string
  ts: string
  scenario: string | null
  data: T
}
