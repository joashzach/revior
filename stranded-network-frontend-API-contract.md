# Revior — Frontend API Contract & UI Specification
_Product name: **Revior** (hackathon problem statement PS2: "The Stranded Network")._
**For the frontend engineer.** Companion to `stranded-network-backend-PRD.md` (backend source of truth). If the two ever disagree, raise it with the backend owner — do not guess.

| Field | Value |
|---|---|
| Version | 1.0 · 2026-11-05 |
| Frontend stack | React + Vite + TypeScript · Tailwind + shadcn/ui · react-router · TanStack Query · react-leaflet (OSM tiles) · Recharts · qrcode.react |
| Backend | FastAPI · REST `/api/v1` · WebSockets `/ws/*` |
| Default scenario / hub | `potheri-demo` · Potheri Railway Station, Chennai |
| Integration checkpoints | Backend Stage 1 (example JSON) · Stage 4 (real allocation data) · Stage 7 (live WebSockets) |

---

## 0. What the product does (one paragraph)
A service at a local hub (local train) gets cancelled and hundreds of passengers are stranded together. Passengers check in, pick a 1st/2nd preferred alternative (or "Any, fastest"). Requests are collected in a short **batch window**, then the **allocation engine** places everyone at once: choices honoured where possible, a **transparent priority score** resolves conflicts, families stay together, accessible seats go to wheelchair users first, and seats are **never over-allocated**. Placed passengers get a **timed seat hold** (Accept/Decline). Declines and expiries **cascade** to the waitlist. Unplaced passengers get **alternatives** (later service, multi-leg, shared-cab **pods**, nearby hub). Operators run everything from a live **dashboard**: trigger disruptions, run allocation, close roads (buses re-route on the map), tune priority weights with a what-if preview, add capacity, and prove zero over-allocation with a stress test.

**Tagline (use in UI):** *Passengers choose. Revior decides fairly. Every decision is explainable.*

---

## 1. App map

### 1.1 Routes
| Route | Who | Purpose |
|---|---|---|
| `/` | public | Landing page (§10) |
| `/demo-join` | public (judges) | **Persona picker** — target of the shared Join QR |
| `/join` | public | Register as a real passenger (email + password) |
| `/login` | public | Email + password login, or "Scan my login QR" |
| `/qr-login?t=<token>` | public | Personal-QR login landing (auto-logs in) |
| `/trip` | passenger | Ticket + live train status (home screen) |
| `/options` | passenger | Choose 1st / 2nd / Any-fastest |
| `/status` | passenger | Batch countdown → result, hold timer, Accept/Decline, waitlist, swap |
| `/why` | passenger | Score breakdown + decision explanation |
| `/alternatives` | passenger | Fallbacks incl. pods |
| `/profile` | passenger | Needs, destination, My login QR, Switch passenger, Logout |
| `/ops/login` | operator | Operator password |
| `/ops` | operator | Disruption dashboard (§9) |

Passenger routes are **mobile-first**. `/ops` is **desktop/projector-first** (≥ 1366 px wide).

### 1.2 Route guards & auto-navigation
- No passenger token → passenger routes redirect to `/login` (keep `?next=`).
- No operator token → `/ops` redirects to `/ops/login`.
- **State-driven redirect** (passenger): after login and on every `allocation.result` / state change, navigate by `passenger.state`:

| state | route |
|---|---|
| `REGISTERED`, `BOOKED` | `/trip` |
| `AFFECTED`, `REOFFER` | `/options` |
| `REQUESTED`, `HELD`, `CONFIRMED`, `WAITLISTED` | `/status` |
| `UNRESOLVED` | `/alternatives` |
| `RESOLVED_ALT` | `/status` (shows chosen alternative) |

Users can still open `/why`, `/profile`, `/alternatives` manually.

---

## 2. Auth & sessions

| Role | How they log in | Token |
|---|---|---|
| **Demo persona (judge)** | Scan shared Join QR → `/demo-join` → pick persona (or "Surprise me") | JWT `role=passenger` |
| **Real passenger** | `/join` register (email + password) or `/login` | JWT `role=passenger` |
| **Passenger via personal QR** | Scan own login QR → `/qr-login?t=…` | JWT `role=passenger` |
| **Operator** | `/ops/login` with password | JWT `role=operator` |

- Send `Authorization: Bearer <token>` on every request.
- Store tokens in `localStorage` under **separate keys**: `revior_passenger_token`, `revior_ops_token` (presenter laptop may have both).
- Tokens last 24 h. On any `401` → clear that token, go to the matching login page with a toast "Session ended".
- A persona released by the operator or swapped via "Switch passenger" invalidates the old token (server-side `token_version`) → next call returns `401` → handled as above.
- Passenger tokens can only read/write their own data. Operator endpoints with a passenger token → `403`.

---

## 3. Conventions

- **Base URL:** `VITE_API_BASE` (e.g. `https://<backend>.onrender.com/api/v1`), **WS base:** `VITE_WS_BASE` (e.g. `wss://<backend>.onrender.com`).
- **IDs:** integers. **Times:** ISO-8601 with offset (UTC from server; display in Asia/Kolkata, `HH:mm`).
- **Countdowns:** compute from server timestamps (`closes_at`, `hold_expires_at`) minus `Date.now()` corrected by `server_time` offset (returned in `GET /health` and every WS message `ts`).
- **Error envelope (all non-2xx):**
```json
{ "error": { "code": "SEAT_UNAVAILABLE", "message": "That seat was just taken.", "details": {} } }
```
| code | HTTP | Frontend handling |
|---|---|---|
| `VALIDATION_ERROR` | 422 | Inline field errors from `details.fields` |
| `UNAUTHORIZED` | 401 | Clear token → login |
| `FORBIDDEN` | 403 | "Not allowed" toast |
| `NOT_FOUND` | 404 | Empty state |
| `INVALID_STATE` | 409 | Refetch `/me/status`, toast message |
| `SEAT_UNAVAILABLE` | 409 | Toast + refetch options/status |
| `ALLOCATION_IN_PROGRESS` | 409 | "Allocation running…" retry after 2 s |
| `BATCH_CLOSED` | 409 | Toast "Window closed — you're in the next batch" |
| `HOLD_EXPIRED` | 409 | Toast + refetch status |
| `POD_FULL` | 409 | Toast + refetch pods |
| `PERSONA_TAKEN` | 409 | Refresh picker, toast "Someone just picked that one" |
| `EMAIL_TAKEN` | 409 | Inline on email field |
| `INVALID_CREDENTIALS` | 401 | Inline "Wrong email or password" |
| `QR_TOKEN_INVALID` | 401 | "QR expired — log in with email" |
| `RATE_LIMITED` | 429 | "Too many attempts, wait a moment" |
| `IDEMPOTENCY_CONFLICT` | 409 | Treat as success, refetch |

- **Idempotency:** mutating passenger actions (`accept`, `decline`, `claim`, `swap`, pod `join`) require header `Idempotency-Key: <uuid v4>`. Generate once per user tap; reuse it on retry.
- **Pagination:** `?page=1&page_size=50` → `{ items, page, page_size, total }`.
- **Polling fallback:** if WS is disconnected > 5 s, poll `/me/status` (passenger) every 3 s or `/ops/kpis` (ops) every 2 s until reconnected.

---

## 4. Shared TypeScript types

```ts
// ---- enums
export type PassengerState =
  | 'REGISTERED' | 'BOOKED' | 'AFFECTED' | 'REQUESTED' | 'HELD' | 'CONFIRMED'
  | 'WAITLISTED' | 'UNRESOLVED' | 'RESOLVED_ALT' | 'REOFFER';
export type ServiceMode = 'local_train' | 'bus' | 'charter_bus' | 'shuttle';
export type ServiceStatus = 'scheduled' | 'delayed' | 'cancelled' | 'running' | 'completed' | 'rerouted';
export type AllocationStatus = 'held' | 'swap_held' | 'confirmed' | 'declined' | 'expired' | 'released';
export type ChoiceRank = '1' | '2' | 'auto' | 'cascade' | 'claim' | 'swap';
export type DisruptionType = 'cancellation' | 'delay' | 'closure';
export type BatchStatus = 'open' | 'closed' | 'allocated';
export type AlternativeType = 'LATER_SERVICE' | 'MULTI_LEG' | 'POD' | 'ALT_HUB' | 'WAIT_DELAYED';
export type PodStatus = 'forming' | 'full' | 'confirmed' | 'departed' | 'cancelled';
export type NeedsClass = 'accessible' | 'priority' | 'general';
export type NodeKind = 'rail_station' | 'bus_stop' | 'hub_only';

// ---- core
export interface Needs {
  wheelchair: boolean; elderly: boolean; with_children: boolean; medical: boolean;
  connection_deadline_at: string | null;
}
export interface NodeRef { id: number; code: string; name: string; lat: number; lng: number; kind: NodeKind; is_hub: boolean; is_default_hub: boolean; }
export interface ServiceSummary {
  id: number; code: string; label: string; mode: ServiceMode; status: ServiceStatus;
  delay_minutes: number; depart_at: string; arrive_at: string;
  origin: NodeRef; destination: NodeRef; accessible: boolean;
}
export interface Passenger {
  id: number; name: string; email: string | null; phone: string | null;
  is_seeded: boolean; is_demo_persona: boolean;
  hub: NodeRef; destination: NodeRef; party_size: number; needs: Needs;
  allow_auto: boolean; state: PassengerState; ticket_id: string;
  affected_at: string | null;
}
export interface Ticket { ticket_id: string; service: ServiceSummary; }

// ---- options & requests
export interface Leg { service: ServiceSummary; from: NodeRef; to: NodeRef; depart_at: string; arrive_at: string; has_seats: boolean; }
export interface Option {
  option_id: string;                // stable key for UI
  request_service_id: number;       // the seat-bearing service to send in /me/request
  label: string; mode: ServiceMode; legs: Leg[];
  depart_at: string; eta_at: string; transfers: number; is_multi_leg: boolean;
  seats_left: number; accessible_seats_left: number; is_full: boolean;   // full → "Join waitlist"
  meets_deadline: boolean; accessible: boolean;
}
export interface Batch { id: number; status: BatchStatus; opens_at: string; closes_at: string; }
export interface RequestOut {
  id: number; batch: Batch;
  choice1_service_id: number | null; choice2_service_id: number | null; any_fastest: boolean;
}

// ---- allocation
export interface Allocation {
  id: number; service: ServiceSummary; seat_count: number; seats: string[];
  choice_rank: ChoiceRank; status: AllocationStatus; is_primary: boolean;
  hold_expires_at: string | null; score: number; explanation: string;
}
export interface WaitlistPosition { service_id: number; label: string; position: number; total: number; is_swap: boolean; }
export interface MyStatus {
  state: PassengerState;
  batch: Batch | null;                    // present while REQUESTED
  allocation: Allocation | null;          // primary held/confirmed
  swap_offer: Allocation | null;          // swap_held
  waitlist: WaitlistPosition[];
  resolved_alternative: Alternative | null;
  headline: string;                       // ready-to-show sentence, e.g. "Placed on your 1st choice ✓"
  server_time: string;
}

// ---- transparency
export interface Why {
  score: number;
  breakdown: Record<'medical'|'wheelchair'|'elderly'|'with_children'|'deadline_urgency'|'wait_time', number>;
  explanation: string;                    // "Priority 82 = medical +30, waited 2h +20, ..."
  decision_explanation: string | null;    // "Choice 1 Bus-3 full: last 3 seats went to scores 91, 88, 85 (yours 72)..."
  rule_version: number; weights: Record<string, number>;
  waitlist: WaitlistPosition[];
}

// ---- alternatives & pods
export interface Alternative {
  type: AlternativeType; ref: string; title: string; description: string;
  eta_at: string | null; legs: Leg[]; pod: Pod | null; requires_allocation: boolean; // true → goes through /me/request
}
export interface Pod {
  id: number; origin: NodeRef; destination: NodeRef; mode: 'cab' | 'auto';
  capacity: number; seats_taken: number; status: PodStatus;
  members: { passenger_id: number; name: string; seat_count: number }[];
  route_km: number; fare_total: number; fare_per_seat: number;
}

// ---- personas
export interface Persona {
  id: number;                 // passenger id
  title: string;              // "Wheelchair user → Guindy"
  emoji: string;              // "♿"
  summary: string;            // "Needs accessible seat · travelling alone"
  destination: NodeRef; party_size: number; needs: Needs;
  is_taken: boolean;
}

// ---- notifications
export interface Notification { id: number; template: string; title: string; body: string; created_at: string; read: boolean; }
```

---

## 5. REST endpoints

All paths relative to `/api/v1`. 🔓 public · 🧍 passenger · 🛠 operator.

### 5.1 System & scenario
| | Method & path | Response |
|---|---|---|
| 🔓 | `GET /health` | `{ status: "ok", db: "ok", version: "1.0.0", server_time }` |
| 🔓 | `GET /scenarios/active` | `{ slug, name, default_hub: NodeRef, join_url, demo_mode: boolean }` |

### 5.2 Auth
| | Method & path | Body | Response |
|---|---|---|---|
| 🔓 | `POST /auth/register` | `{ scenario, name, email, password, phone?, hub_node_id?, destination_node_id, needs: Needs, party_size, allow_auto? }` | `{ token, passenger: Passenger, ticket: Ticket }` |
| 🔓 | `POST /auth/login` | `{ scenario, email, password }` | `{ token, passenger }` |
| 🔓 | `POST /auth/qr-login` | `{ token: "<t from URL>" }` | `{ token, passenger }` |
| 🔓 | `POST /auth/ops-login` | `{ password }` | `{ token }` |
| 🧍 | `POST /auth/logout` | — | `204` |

Validation: email format; password ≥ 6 chars; `party_size` 1–6; destination must come from `/destinations`.

### 5.3 Demo personas (judges)
| | Method & path | Body | Response |
|---|---|---|---|
| 🔓 | `GET /demo/personas?scenario=potheri-demo` | — | `{ items: Persona[] }` (taken ones `is_taken: true`) |
| 🔓 | `POST /auth/demo-claim` | `{ scenario, persona_id?: number, surprise?: boolean }` | `{ token, passenger, persona: Persona }` — if the pool is empty, server auto-creates a new passenger with random needs |
| 🧍 | `POST /me/demo-switch` | `{ mode: "next" \| "pick", persona_id? }` | `{ token, passenger, persona }` — old persona released, **replace stored token** |

### 5.4 Hubs & destinations
| | Method & path | Body/Query | Response |
|---|---|---|---|
| 🔓 | `POST /hubs/nearby` | `{ scenario, lat?, lng? }` | `{ hubs: [{ hub: NodeRef, distance_km: number \| null, is_default: boolean }], selected_hub_id, reason: "nearest" \| "default" }` |
| 🔓 | `GET /destinations?scenario=&hub=&q=` | — | `{ items: NodeRef[] }` |

Hub rule: hubs within 10 km of the user's location, nearest first, **Potheri pre-selected**. Denied/failed location → Potheri only (`reason: "default"`), with a "Change hub" option.

### 5.5 Passenger (🧍)
| Method & path | Body | Response | Notes |
|---|---|---|---|
| `GET /me` | — | `Passenger` | |
| `PATCH /me` | `{ destination_node_id?, hub_node_id?, needs?, party_size?, allow_auto? }` | `Passenger` | Allowed only in `REGISTERED`, `BOOKED`, `AFFECTED`; else `INVALID_STATE` |
| `GET /me/trip` | — | `{ ticket: Ticket, disruption: { id, type, reason, created_at } \| null, headline }` | |
| `GET /me/options` | — | `{ items: Option[], batch: Batch \| null }` | |
| `POST /me/request` | `{ choice1_service_id?, choice2_service_id?, any_fastest }` | `RequestOut` | Re-submitting while batch open **replaces** the request |
| `GET /me/status` | — | `MyStatus` | Main polling/refresh endpoint |
| `POST /me/allocation/accept` | `{ allocation_id? }` (omit = primary; pass swap offer id to accept swap) | `MyStatus` | `Idempotency-Key` |
| `POST /me/allocation/decline` | `{ allocation_id? }` | `MyStatus` | `Idempotency-Key` |
| `POST /me/swap` | `{ service_id }` | `MyStatus` | Keep current seat, join target waitlist |
| `POST /me/claim` | `{ service_id }` | `MyStatus` | Open booking only; `Idempotency-Key` |
| `GET /me/why` | — | `Why` | |
| `GET /me/alternatives` | — | `{ items: Alternative[] }` | |
| `POST /me/alternatives/accept` | `{ type, ref }` | `MyStatus` | For non-seat alternatives → `RESOLVED_ALT` |
| `GET /me/pods/suggested` | — | `{ items: Pod[] }` | |
| `POST /me/pods` | `{ destination_node_id, mode: "cab" \| "auto" }` | `Pod` | |
| `POST /pods/{id}/join` | — | `Pod` | `Idempotency-Key` |
| `POST /pods/{id}/leave` | — | `204` | |
| `POST /pods/{id}/confirm` | — | `Pod` | Needs ≥ 2 members |
| `GET /me/login-qr` | — | `{ url: "https://<frontend>/qr-login?t=...", expires_at }` | Render with `qrcode.react` |
| `GET /me/notifications` | — | `{ items: Notification[] }` | Latest 50 |
| `POST /me/notifications/read` | `{ ids: number[] }` | `204` | |

### 5.6 Operator (🛠)
**Scenario & config**
| Method & path | Body | Response |
|---|---|---|
| `GET /ops/scenarios` | — | `{ items: [{ slug, name, is_active }] }` |
| `POST /ops/scenarios/{slug}/activate` | — | `{ slug }` |
| `POST /ops/scenarios/{slug}/reset` | — | `{ duration_ms, counts: { passengers, services, personas } }` |
| `GET /ops/scenarios/{slug}/config` | — | `ScenarioConfig` |
| `PATCH /ops/scenarios/{slug}/config` | partial `ScenarioConfig` | `ScenarioConfig` |

```ts
interface ScenarioConfig {
  batch_window_seconds: number; hold_seconds: number; auto_run_on_batch_close: boolean;
  delay_threshold_minutes: number; hub_radius_km: number; open_booking_enabled: boolean;
  sim_speed: number; demo_mode: boolean; join_qr_mode: 'corner' | 'fullscreen' | 'hidden';
}
```

**Network, services, disruptions**
| Method & path | Body | Response |
|---|---|---|
| `GET /ops/network` | — | `{ nodes: NodeRef[], edges: [{ id, from_node_id, to_node_id, mode, road_name, is_closed, polyline: GeoJSON.LineString }] }` |
| `GET /ops/services` | `?status=&mode=` | `{ items: (ServiceSummary & { total_seats, held, confirmed, free, accessible_free, waitlist_len, polyline })[] }` |
| `POST /ops/services` | `{ label, mode: "charter_bus" \| "shuttle", stop_node_ids: number[], depart_in_minutes, total_seats, accessible_seats }` | `ServiceSummary` (auto re-allocation follows) |
| `GET /ops/disruptions/preview` | `?type=&service_id=&edge_id=&delay_minutes=` | `{ affected_count, by_destination: [{ destination: NodeRef, count }] }` |
| `POST /ops/disruptions` | `{ type, service_id?, edge_id?, delay_minutes?, reason }` | `{ disruption, affected_count, batch: Batch }` |
| `GET /ops/disruptions` | — | `{ items: [{ id, type, target_label, reason, created_at, resolved_at, affected_count }] }` |
| `POST /ops/disruptions/{id}/resolve` | — | `{ id, resolved_at }` |

**Batches & allocation**
| Method & path | Body | Response |
|---|---|---|
| `GET /ops/batches/current` | — | `{ batch: Batch \| null, request_count }` |
| `POST /ops/batches/current/close` | — | `Batch` |
| `POST /ops/allocation/run` | `{ mode: "greedy" \| "ortools" }` | `{ run_id, stats: RunStats }` |
| `GET /ops/allocation/runs/{id}` | — | `{ id, mode, started_at, finished_at, rule_version, stats: RunStats }` |

```ts
interface RunStats { units: number; placed_choice1: number; placed_choice2: number; placed_auto: number;
  waitlisted: number; unresolved: number; duration_ms: number;
  fill_rate_by_service: { service_id: number; label: string; fill_rate: number }[]; }
```

**Dashboard data**
| Method & path | Response |
|---|---|
| `GET /ops/kpis` | `{ affected, checked_in, not_checked_in, requested, held, confirmed, waitlisted, unresolved, resolved_alt, avg_wait_min, median_time_to_placement_min, fill_rate, batch: Batch \| null }` |
| `GET /ops/clusters` | `{ items: [{ id, destination: NodeRef, time_bucket_start, needs_class: NeedsClass, size, demand_seats, capacity_seats }] }` |
| `GET /ops/capacity` | `{ items: [{ service: ServiceSummary, total_seats, held, confirmed, free, accessible_free, waitlist_len }] }` |
| `GET /ops/allocations?status=&destination=&needs=&q=&page=&page_size=` | paginated `{ passenger: {id,name,party_size,needs}, score, choice_rank, service_label, status, hold_expires_at, explanation }` |
| `GET /ops/unresolved` | `{ items: [{ passenger: Passenger, waited_min, alternatives: Alternative[] }] }` |
| `GET /ops/fairness` | `{ by_needs_class: [{ needs_class, placement_rate, wait_p50, wait_p90 }], by_destination: [{ destination: NodeRef, placement_rate, unresolved }], wait_gini }` |
| `GET /ops/map` | `{ nodes, edges, services: [{ id, label, mode, status, polyline }], vehicles: [{ service_id, lat, lng, progress }], clusters: [{ node_id, size }] }` |
| `GET /ops/invariants` | `{ over_allocated_services: 0, multi_primary_passengers: 0, negative_free_seats: 0, ok: true }` |
| `GET /ops/passengers/{id}` | `{ passenger: Passenger, status: MyStatus, why: Why }` |
| `GET /ops/passengers/{id}/login-qr` | `{ url, expires_at }` |

**Rules, audit, notifications, open booking**
| Method & path | Body | Response |
|---|---|---|
| `GET /ops/rules` | — | `{ active: { version, weights }, history: [{ version, weights, created_at }] }` |
| `POST /ops/rules/preview` | `{ weights }` | `{ placed_delta, by_needs_class: [{ needs_class, placement_rate_before, placement_rate_after }], movers: [{ passenger_id, name, service_label, position_before, position_after }] }` |
| `POST /ops/rules/apply` | `{ weights }` | `{ version }` |
| `GET /ops/audit?passenger_id=&entity=&page=` | — | paginated `{ id, actor, action, entity_type, entity_id, explanation, created_at }` |
| `GET /ops/notifications?page=` | — | paginated `{ passenger_name, channel: "push" \| "email_sim" \| "sms_sim", template, body, created_at }` |
| `POST /ops/open-booking` | `{ enabled }` | `{ enabled }` |

**Demo personas & stress test**
| Method & path | Body | Response |
|---|---|---|
| `GET /ops/demo/personas` | — | `{ items: (Persona & { claimed_at: string \| null, state: PassengerState })[] }` |
| `POST /ops/demo/personas/{id}/release` | — | `204` (that phone gets 401 → back to picker) |
| `POST /ops/demo/personas/release-all` | — | `204` |
| `POST /ops/stress/run` | `{ requests?: 1000, seats?: 10 }` (demo_mode only) | `{ run_id }` — progress via WS |

---

## 6. WebSockets

- Passenger: `${VITE_WS_BASE}/ws/passenger?token=<passenger token>`
- Operator: `${VITE_WS_BASE}/ws/ops?token=<ops token>`
- Message shape: `{ "type": string, "ts": string, "scenario": string, "data": object }`
- Client sends `{"type":"ping"}` every 20 s; server answers `pong`. Reconnect with backoff (1 s, 2 s, 5 s, max 10 s). **After reconnect, refetch** `/me/status` or `/ops/kpis` (events are not replayed).
- Pattern: on any event, **invalidate the related TanStack Query key** rather than hand-merging (simpler and safe). Use event `data` for instant UI (toasts, countdowns).

| Event | Receiver | `data` | Frontend action |
|---|---|---|---|
| `service.status_changed` | both | `{ service_id, status, delay_minutes }` | Passenger: refetch trip; big alert if own ticket cancelled. Ops: refetch services/map |
| `disruption.created` / `disruption.resolved` | both | `{ disruption }` | Passenger → `/options`. Ops: refetch disruptions/kpis |
| `batch.opened` / `batch.closed` | both | `{ batch_id, closes_at }` | Start/stop countdown |
| `allocation.run_started` / `allocation.run_completed` | ops | `{ run_id, stats? }` | Spinner → stats toast; refetch capacity/allocations |
| `allocation.result` | passenger | `{ state, allocation, explanation }` | Navigate per §1.2, show result card |
| `offer.created` | passenger | `{ allocation }` | "A seat opened up for you!" + hold timer |
| `swap.offer_created` | passenger | `{ allocation }` | Swap offer banner |
| `hold.expiring` | passenger | `{ allocation_id, seconds_left: 30 }` | Vibrate / red timer |
| `hold.expired` | passenger | `{ allocation_id }` | Toast, refetch status |
| `allocation.confirmed` / `allocation.declined` | ops | `{ allocation_id, passenger_id, service_id }` | Refetch capacity/allocations |
| `seat.released` | ops | `{ service_id, count }` | Flash capacity bar |
| `waitlist.position_changed` | passenger | `{ service_id, position, total }` | Animate number |
| `eta.updated` | both | `{ service_id, eta_at }` | Update ETA text |
| `service.rerouted` | both | `{ service_id, polyline, skipped_stops: NodeRef[] }` | Ops map: grey old line, draw new green. Passenger: banner "Your bus is re-routing" |
| `vehicle.positions` | ops (all), passenger (own service) | `{ items: [{ service_id, lat, lng, progress }] }` | Move markers (1 Hz, animate) |
| `kpi.updated` | ops | KPI object | Replace KPI query data |
| `rules.updated` | both | `{ version }` | Refetch why/waitlist |
| `pod.updated` | pod members, ops | `{ pod }` | Refetch pods |
| `passenger.registered` | ops | `{ passenger, is_demo_persona }` | Toast "Judge joined: ♿ Wheelchair user → Guindy" |
| `persona.claimed` / `persona.released` | ops | `{ persona_id }` | Refetch personas panel |
| `notification.created` | passenger | `Notification` | Bell badge + toast |
| `stress.progress` / `stress.result` | ops | `{ sent, ok, conflicts, errors }` / `{ total, confirmed, capacity, over_allocations: 0, five_xx: 0, passed }` | Live counter → big ✓ "0 over-allocations" |

---

## 7. Feature → endpoint map (quick reference)
| Feature | Passenger UI | Ops UI | Endpoints |
|---|---|---|---|
| Join as judge | `/demo-join` | QR panel, personas panel | `/demo/personas`, `/auth/demo-claim`, `/me/demo-switch`, `/ops/demo/*` |
| Register / login | `/join`, `/login`, `/qr-login` | — | `/auth/*`, `/hubs/nearby`, `/destinations`, `/me/login-qr` |
| Disruption | trip alert | Disruption panel | `/ops/disruptions*`, WS `disruption.*` |
| Choose options | `/options` | — | `/me/options`, `/me/request` |
| Batch + allocation | `/status` countdown | Run allocation, KPI, capacity | `/ops/batches/*`, `/ops/allocation/run`, WS `allocation.*` |
| Hold / accept / decline / cascade | `/status` | Capacity board | `/me/allocation/*`, WS `offer.created` |
| Swap | `/status` | — | `/me/swap` |
| Transparency | `/why` | Rules editor, audit | `/me/why`, `/ops/rules*`, `/ops/audit` |
| Alternatives & pods | `/alternatives` | Unresolved queue | `/me/alternatives*`, `/me/pods*`, `/pods/*` |
| Re-routing | banner, ETA | Map, close road | `/ops/disruptions` (closure), WS `service.rerouted` |
| Add capacity | — | Add charter bus | `POST /ops/services` |
| Open booking | "Grab a seat" on options | Toggle | `/ops/open-booking`, `/me/claim` |
| Fairness | — | Fairness tab | `/ops/fairness` |
| Stress test | — | Stress tab | `/ops/stress/run`, WS `stress.*` |
| Scenario switch / reset | — | Top bar | `/ops/scenarios/*` |

---

## 8. Passenger app — screen specs (mobile-first)

**Global shell:** top bar (app name, live dot = WS connected, bell with unread count) · bottom nav: **Trip · Status · Why · More** (More → Alternatives, Profile). Toasts at top. Large tap targets (≥ 44 px). Status colours: green = placed/confirmed, amber = held/waitlisted/delayed, red = cancelled/expired/unresolved, blue = info.

### 8.1 `/demo-join` — Persona picker (judges)
- Header: "You're stranded at **Potheri** — pick who you are."
- Grid of persona cards (`GET /demo/personas`): emoji, title, summary, destination, party size, need chips. Taken cards greyed out with a "Taken" badge.
- Buttons: **"Surprise me"** (`surprise: true`), and a small link "Register as yourself instead" → `/join`.
- Tap card → `POST /auth/demo-claim` → store token → `/trip`. On `PERSONA_TAKEN` → refresh list + toast.
- Refresh list every 3 s while open (or on `persona.*` if WS available).

### 8.2 `/join` — Register
1. **Location step:** ask browser geolocation → `POST /hubs/nearby`. Show hub list with Potheri pre-selected; "Change hub". Denied → Potheri + note.
2. **Form:** name, email, password, optional phone, destination (searchable combobox from `/destinations`), party size stepper (1–6), need toggles (wheelchair, elderly, travelling with children, medical), optional connection deadline (time picker; helper text "e.g., flight at Airport").
3. Submit → `POST /auth/register` → `/trip`. Show the virtual ticket ID in a success sheet.

### 8.3 `/login` & `/qr-login`
- `/login`: email + password. Link "Use my login QR" explains: scan your QR with this phone's camera.
- `/qr-login?t=`: auto `POST /auth/qr-login` → `/trip`; on failure show "QR expired — log in with email".

### 8.4 `/trip` — Home
- Ticket card: virtual ticket ID, train label (e.g., "6:10 PM Chengalpattu → Chennai Beach local"), hub → destination, departure, status pill (On time / Delayed +25 min / **Cancelled**).
- Normal state: subtle "We'll alert you if anything changes."
- On cancellation/disruption (WS): full-width red alert "Your train is cancelled — waterlogging near Guduvanchery" + CTA **"Choose an alternative"** → `/options` (auto-navigate after 2 s).
- Delay below threshold: amber pill only.

### 8.5 `/options` — Choose alternatives
- Batch banner: "Requests close in **0:24**" (from `batch.closes_at`).
- Option cards (`GET /me/options`): mode icon, label, depart → ETA, transfers ("via Tambaram" for multi-leg, with leg breakdown), seats left bar, ♿ badge if accessible, "Meets your deadline" / "Arrives after your deadline" tag, **Full → "Join waitlist"** state.
- Selection: tap to set **1st**, tap another for **2nd** (numbered badges); toggle **"Any, fastest"** (disables manual picks). Toggle "Allow auto-placement if both are full" (maps to `allow_auto`, via `PATCH /me` before submit).
- Submit **"Send my request"** → `POST /me/request` → `/status`. Re-submit allowed while the batch is open ("Update request").
- If open booking is on: options with free seats show **"Grab now"** → `POST /me/claim`.
- `WAIT_DELAYED` appears as an option card for delay disruptions.

### 8.6 `/status` — Result & actions
States (driven by `MyStatus`):
| State | UI |
|---|---|
| `REQUESTED` | Countdown ring "Allocating in 0:18", summary of your choices, "Edit request" |
| `HELD` | Big green card: "Placed on your 1st choice ✓" / amber "Moved to Bus-5 — see why". Service, departure, seats (`seats[]`), **hold timer** (red at ≤ 30 s), buttons **Accept** / **Decline**, link "Why this?", "Request a different option" (swap picker → `POST /me/swap`) |
| `CONFIRMED` | Boarding-pass style card: service, seats, departure, ETA (live), live mini-map of own vehicle (`vehicle.positions`), re-route banner if `service.rerouted` |
| `WAITLISTED` | "Waitlisted **#2** for Bus-3" per waitlist entry (animate on change), hint "We'll offer you a seat the moment one frees up", link to Alternatives |
| `REOFFER` | Amber: "Your bus was re-routed and may miss your deadline — choose again (you keep your seat until then)" → `/options` |
| `RESOLVED_ALT` | Card for the chosen alternative (pod details/fare, multi-leg legs, or "Waiting for delayed train") |
| Swap offer present | Banner on top: "Your preferred Bus-3 has a seat — switch?" with its own timer, **Switch** (accept with `allocation_id`) / **Keep current** (decline with `allocation_id`) |
| Cascade offer | Toast + card animates in: "A seat opened up for you!" |

### 8.7 `/why` — Transparency
- Score dial (0–100+) + horizontal bar breakdown per feature (medical, wheelchair, elderly, with children, deadline urgency, wait time) with points.
- `explanation` sentence, `decision_explanation` sentence (e.g., "Bus-3's last 3 seats went to scores 91, 88, 85; yours is 72").
- Waitlist positions, rule version, and current weights shown in a small table ("Rules v3").
- Footer line: "Ticket price is never used in prioritisation."

### 8.8 `/alternatives`
- List of alternative cards by ETA: Later service · Multi-leg (leg timeline) · Pod · Nearby hub · Wait for delayed train.
- Seat-bearing alternatives → "Request this" (`POST /me/request`); non-seat → "Choose this" (`POST /me/alternatives/accept`).
- **Pods section:** suggested pods (`/me/pods/suggested`) with members count `2/4`, fare per seat, destination; **Join**; **Create pod** (choose cab/auto). Inside a pod: member list, fare split (live), **Confirm pod** (≥ 2 members), **Leave**.

### 8.9 `/profile`
- Name, email, hub, destination, party size, needs (editable only in allowed states; otherwise read-only with lock icon).
- **My login QR** (`GET /me/login-qr` → `<QRCodeSVG value={url} />`), expiry text, "Show full screen".
- **Switch passenger** (demo personas only): "Next persona" / "Pick a persona" → `POST /me/demo-switch` → replace token → `/trip`.
- Logout.

### 8.10 Notifications
Bell drawer listing `/me/notifications`; mark read on open. Templates: disruption alert, batch open, placed, moved, waitlisted, seat opened (cascade), hold expiring, expired, ETA updated, re-offer, swap offer, pod update.

---

## 9. Operator dashboard — `/ops` (desktop/projector)

### 9.1 Layout
```
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│ TOP BAR: Revior · Scenario ▼ (potheri-demo) · Live ● · Batch 0:24 ·                       │
│          [Join QR: Corner|Full|Hidden] [Open booking ⏻] [Reset scenario] [Ops logout]      │
├───────────────────────────────────────────────────────────────────────────────────────────┤
│ KPI ROW: Affected · Checked-in · Requested · Held · Confirmed · Waitlisted · Unresolved ·  │
│          Avg wait · Fill rate · Invariants ✓                                               │
├───────────────────────────────────────────────┬───────────────────────────────────────────┤
│ LIVE MAP (60%)                                │ CONTROL PANEL (40%)                        │
│ - nodes/stations, hubs (Potheri highlighted)  │ ▸ Disruptions: Cancel service · Delay ·    │
│ - service polylines (status colours)          │   Close road/rail edge · preview count ·   │
│ - closed edges red, rerouted new path green   │   active disruptions list (Resolve)        │
│ - vehicle markers moving                      │ ▸ Allocation: Close batch now · Run        │
│ - cluster bubbles at hub sized by demand      │   allocation (greedy/ortools) · last run   │
│ - click edge → "Close this road"              │   stats                                    │
│                                               │ ▸ Add capacity: charter bus form           │
│                                [Join QR corner]│                                           │
├───────────────────────────────────────────────┴───────────────────────────────────────────┤
│ TABS: Capacity | Clusters | Allocations | Unresolved | Rules | Fairness | Audit |           │
│       Messages | Demo personas | Stress test                                                │
└───────────────────────────────────────────────────────────────────────────────────────────┘
```

### 9.2 Panel specs
| Panel | Content & behaviour | Data |
|---|---|---|
| **Top bar** | Scenario dropdown (activate), live WS dot, batch countdown, Join QR mode segmented control (persists via config PATCH), Open booking switch, Reset (confirm dialog) | `/ops/scenarios*`, config, `/ops/open-booking` |
| **KPI row** | 10 stat tiles, animate on change; Invariants tile green ✓ when `ok`, red ✗ otherwise | `/ops/kpis` + `kpi.updated`, `/ops/invariants` (every 5 s) |
| **Live map** | react-leaflet + OSM tiles. Layers toggle: stations, roads, services, vehicles, clusters. Colours: scheduled grey-blue, running blue, delayed amber, cancelled red dashed, rerouted green, closed edge red thick. Click service → side sheet with capacity & passengers. Click road edge → "Close edge" pre-filled in disruption form | `/ops/map`, `service.rerouted`, `vehicle.positions` |
| **Disruption form** | Type tabs: Cancel (service dropdown — **any** local train/service), Delay (service + minutes), Close edge (edge dropdown or map click). Reason text. "Preview" shows affected count by destination; "Confirm" triggers | `/ops/disruptions/preview`, `POST /ops/disruptions` |
| **Allocation controls** | Batch status + request count, **Close batch now**, **Run allocation** (mode select; OR-Tools hidden unless enabled), last run stats card (placed 1st/2nd/auto, waitlisted, unresolved, duration ms) | `/ops/batches/current`, `/ops/allocation/run` |
| **Add capacity** | Form: label, mode (charter/shuttle), stops (multi-select in order, from network nodes), departs in N min, seats, accessible seats → submit → toast "Re-allocating…" | `POST /ops/services` |
| **Capacity tab** | One row per service: label, mode, departure, stacked bar (confirmed / held / free; accessible free badge), "x/total", waitlist length. Bar **never exceeds 100%**. Flash on `seat.released` | `/ops/capacity` |
| **Clusters tab** | Cards/table: destination × time bucket × needs class, size, demand vs capacity bar (red if demand > capacity) | `/ops/clusters` |
| **Allocations tab** | Filterable, searchable table: passenger, party, need chips, score, choice rank, service, status pill, hold expiry, explanation (truncate + tooltip). Row click → passenger drawer (status + why + login QR) | `/ops/allocations`, `/ops/passengers/{id}` |
| **Unresolved tab** | Queue sorted by waited time; each row shows generated alternatives; header button **Add charter bus** (opens Add capacity) | `/ops/unresolved` |
| **Rules tab** | Sliders for each weight (0–50), current vs edited values, **Preview** → diff panel (placed delta, placement rate by needs class before/after, top movers with position before → after), **Apply** → version bump toast; history list | `/ops/rules*` |
| **Fairness tab** | Bar chart placement rate by needs class; p50/p90 wait by class; placement by destination; Gini number with "lower is fairer" | `/ops/fairness` (Recharts) |
| **Audit tab** | Paginated log: time, actor, action, entity, explanation; filter by passenger | `/ops/audit` |
| **Messages tab** | Simulated email/SMS log (what each passenger was told) | `/ops/notifications` |
| **Demo personas tab** | Table: persona, claimed? (time), current state, **Release**; **Release all** | `/ops/demo/*`, `persona.*` |
| **Stress test tab** | Inputs (requests 1000, seats 10) → **Run** → live counters → result card "1000 requests · 10 seats · **0 over-allocations** · 0 errors" | `/ops/stress/run`, `stress.*` |

### 9.3 Join QR panel
- Value: `scenario.join_url` (= `https://<frontend>/demo-join?scenario=potheri-demo`), render with `qrcode.react`.
- **Corner** mode: 140 px card bottom-right of the map, caption "Scan to join as a stranded passenger".
- **Fullscreen** mode: overlay with a 70vh QR code, caption, live counter "Judges joined: 4" (from `persona.claimed`), Esc / "Start demo" closes it to Corner.
- **Hidden**: not shown.
- Mode is saved in scenario config so it survives a reload.

---

## 10. Landing page — `/` (brief)
- **Hero:** title "Revior", tagline, one-line problem ("When a local train is cancelled, hundreds are stranded at once. We recover them together, fairly."). Buttons: **Try the demo** → `/demo-join`, **Join as passenger** → `/join`, **Log in** → `/login`. (No operator link; operators go to `/ops` directly.)
- **How it works:** 4 steps with icons — Disruption detected → Passengers choose → Engine allocates fairly → Everyone gets a way home.
- **Why it's different:** 3 cards — Group recovery (not one-by-one) · Transparent priority (no ticket-price bias) · Zero over-allocation.
- **Footer:** hackathon PS2 credit, team names.
- Keep it light: static, mobile-friendly, no data calls except optional `GET /scenarios/active`.

---

## 11. Demo flow — what the frontend must show
| # | Operator (dashboard on projector) | Judges (phones) |
|---|---|---|
| 1 | Normal map; Join QR **fullscreen** | Scan → `/demo-join` → pick persona → `/trip` "On time". Ops toasts "Judge joined…" |
| 2 | Close QR → Corner; **Cancel** the local train | All phones flip to red "Cancelled" → `/options` |
| 3 | Narrate | Pick 1st/2nd, "Send my request", countdown |
| 4 | Batch closes → **Run allocation**; capacity bars fill to 100% | Placed ✓ / Moved / Waitlisted #n |
| 5 | Point at contested bus | Open `/why` |
| 6 | Ask a judge to Decline | Another judge gets "A seat opened up for you!" |
| 7 | Click GST Road near Vandalur → Close | Re-route banner, ETA update; map draws new green route |
| 8 | Rules tab: raise medical → Preview → Apply | Waitlist positions animate |
| 9 | Unresolved → Add charter bus | Waitlisted judges placed / pods shown |
| 10 | Stress test tab → Run | — big ✓ "0 over-allocations" |
| 11 | Scenario dropdown → secondary for 10 s → back | — |

Reset scenario between judging panels (frees all personas).

---

## 12. Mock layer & integration plan
- Build an API client (`src/api/`) with a switch `VITE_USE_MOCKS=true|false`. Mocks read `contracts/examples/*.json` (provided by backend after Stage 1) and simulate WS events with a timer script (cancel at 10 s, result at 40 s, cascade at 60 s).
- Until Stage 1 examples land, hand-write mocks from the types in §4 (they are the contract).
- Checkpoint 1 (backend Stage 1): swap hand mocks for `contracts/examples`. Checkpoint 2 (Stage 4): real REST for options/request/status/why. Checkpoint 3 (Stage 7): real WebSockets, remove mock timers.
- Keep mocks working forever as a demo fallback (`?mock=1`).

---

## 13. Frontend acceptance checklist
- [ ] Two separate token stores; 401 handling; state-driven routing (§1.2).
- [ ] Persona picker handles taken personas and "Surprise me"; Switch passenger replaces the token.
- [ ] Location prompt → Potheri pre-selected; denial falls back gracefully.
- [ ] All countdowns use server timestamps (no drift between judges' phones).
- [ ] Idempotency keys on accept/decline/claim/swap/pod join.
- [ ] WS reconnect + refetch; polling fallback.
- [ ] Capacity bars never render > 100%.
- [ ] Map: closed edges red, rerouted green, vehicles moving.
- [ ] Rules preview shows diff without changing anything until Apply.
- [ ] Join QR modes (corner/fullscreen/hidden) persist.
- [ ] Works on a 360 px wide phone and on a 1366 px projector.
- [ ] Mock mode works offline as a backup.
