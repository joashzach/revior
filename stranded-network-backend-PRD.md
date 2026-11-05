# The Stranded Network — Backend PRD
**Dynamic Travel Recovery & Passenger Coordination Platform**
Hackathon PS2 · 24-hour build · Backend owner: Backend developer · Frontend owner: Frontend developer

| Field | Value |
|---|---|
| Document type | Backend Product Requirements Document (implementation-ready) |
| Version | 1.0 |
| Date | 2026-11-05 |
| Stack | Python 3.12 · FastAPI · PostgreSQL 16 · SQLAlchemy 2 (async) · networkx · WebSockets |
| Default hub | **Potheri Railway Station, Chennai** (hackathon venue) |
| Build mode | Coding agent, **stage-gated** (see §20). Agent STOPS after every stage and reports. |

---

## 0. How to read this document (instructions for the coding agent)

1. This PRD is the **single source of truth**. If anything here seems ambiguous, choose the simplest interpretation that satisfies the acceptance criteria, and **record the decision in your stage report** under "Assumptions".
2. Build **only the stage you were told to build**. After finishing it, produce the Stage Report (§20.3) and **STOP**. Do not start the next stage until the user explicitly says `Proceed to Stage N`.
3. Do **not** change the API contract (§12) or the WebSocket event schema (§13) without listing the change in "Contract changes" in your report — the frontend is built against them in parallel.
4. Everything is **scenario-scoped** (§5.1). No hard-coded station, train, or city anywhere in business logic. Potheri is *data*, not code.
5. Correctness priorities, in order: **(1) never over-allocate a seat, (2) every allocation decision is explainable and audited, (3) determinism (same seed + same inputs → same result), (4) speed.**

---

## 1. Product summary

### 1.1 Problem
A single disruption (e.g., a cancelled local train) strands hundreds of people at once, but route planners solve journeys one passenger at a time. First-come-first-served self-booking during a surge is unfair (fastest phone wins, vulnerable passengers lose), wastes capacity (a Tambaram-bound passenger takes the last Egmore seat), splits families, and causes over-booking races.

### 1.2 Solution (core concept)
Treat a disruption as a **group recovery event**:

```
Disruption → detect affected passengers → passengers check in & state needs
→ passengers pick preferred options (1st / 2nd / "Any, fastest")
→ requests collected in a BATCH WINDOW
→ ALLOCATION ENGINE places everyone at once (choices honoured where possible,
   priority score resolves conflicts, groups kept together, all constraints enforced)
→ time-limited SEAT HOLDS (accept / decline / swap)
→ CASCADE freed seats to waitlist in priority order
→ FALLBACKS for unplaced (later service, multi-leg, pod cab, alternate hub)
→ OPEN BOOKING of leftover seats after fair rounds
```

**Tagline:** *Passengers choose. The engine decides fairly. Every decision is explainable.*

### 1.3 Key design decisions (locked — do not revisit)
| # | Decision | Rationale |
|---|---|---|
| D1 | **Request-based batch allocation**, not instant self-booking | Fairness, global efficiency, no surge race. Instant per-request checks are still first-come-first-served. |
| D2 | Passengers select **1st choice, 2nd choice, or "Any, fastest"** | User agency without losing coordination. |
| D3 | **Transparent weighted priority score**; ticket price is **never** a factor | Explainable, inspectable, fair. |
| D4 | **Seat holds with expiry** (accept/decline) + **cascade** | Handles no-shows, prevents over-allocation. |
| D5 | **Pods** (shared cab/auto pooling) for unplaced passengers | Creates capacity instead of only dividing it. |
| D6 | **Mock vehicles/capacity/disruptions on real geography** (OSM coords, OSRM road polylines) | No public live seat-capacity API; disruptions must be triggerable on demand. Adapter interface allows real feeds later. |
| D7 | **Default hub = Potheri Railway Station**. Live location suggests nearest hubs within radius; user can switch. Location denied → Potheri. | Hackathon venue; real location used without breaking scenario. |
| D8 | **Operator cancels any local train** from the dashboard (nothing hard-coded). | Generality. |
| D9 | Local trains have **no PNR** → passenger identity = **phone + ticket/season-pass ID**; new registrations receive a **virtual ticket**. | Indian suburban rail reality. |
| D10 | Accessible seats are **reserved for accessibility-need passengers first** (two-pass allocation). | Prevents wheelchair users losing accessible seats to higher-scored non-need passengers. |
| D11 | Single backend instance, in-process pub/sub, Postgres row locks for concurrency. Redis is a documented upgrade path only. | 24-hour scope; correctness via DB. |

### 1.4 Out of scope
Real payments, real ticketing integrations (CRIS/UTS), real SMS at scale (Twilio sandbox optional), hotel booking, ML-based demand prediction, multi-instance horizontal scaling, native mobile apps.

---

## 2. Users & roles

| Role | Access | Auth |
|---|---|---|
| **Passenger** (seeded or newly registered, incl. judges) | Passenger app routes: `/join`, `/trip`, `/options`, `/status`, `/why`, `/alternatives` | JWT (role=`passenger`) |
| **Operator** | Dashboard `/ops` (presenter laptop only) | Password from env → JWT (role=`operator`) |
| **System** | Background jobs (batch closer, hold expiry, simulator, cascade) | Internal |

---

## 3. Real-world flow (functional narrative)

1. **Normal state:** Passengers hold tickets for local trains from their hub. Passenger app shows "6:10 PM Beach local — On time".
2. **Disruption:** Operator cancels a local train (or marks a delay ≥ threshold, or closes a road/rail edge). System flags every passenger whose ticket is on that service (or whose route uses the closed edge).
3. **Alert:** Affected passengers receive push (WebSocket) + simulated SMS: "Your train is cancelled. Choose an alternative."
4. **Check-in:** Passenger confirms hub (location snapped, Potheri default), destination, needs (wheelchair, elderly, children, medical, connection deadline, party size).
5. **Options:** Passenger sees alternative services serving hub → destination: mode, departure, ETA, seats left, accessibility, transfer count.
6. **Request:** Passenger selects 1st + optional 2nd choice, or "Any, fastest". Request is queued into the current **batch**.
7. **Batch close:** Window closes (configurable: real 150 s, demo 30 s). Allocation engine runs over all queued requests at once.
8. **Result:** "Placed on your choice ✓", "Moved to Bus 5 — here's why", or "Waitlisted #2". A placed seat is a **hold** (real 600 s, demo 120 s) until Accept.
9. **Cascade:** Decline/expiry frees the seat → offered to next eligible waitlisted passenger in priority order.
10. **Swap:** A placed passenger may request a different option; they keep their current seat and join that option's waitlist with a swap flag. If offered and accepted, old seat is released atomically (and cascades).
11. **Unresolved:** Unplaced passengers get fallbacks: later service, multi-leg (e.g., bus Potheri→Tambaram + local Tambaram→Beach), pod cab, alternate hub. Operator can **add capacity** (charter bus) → automatic re-allocation.
12. **Live changes:** Road closure (e.g., GST Road near Vandalur) → buses re-routed (k-shortest path), ETAs updated, deadline feasibility re-checked, affected passengers notified/re-offered.
13. **Open booking:** After allocation rounds settle (operator toggle or auto after N rounds), leftover seats become instantly claimable (still transactional, still capacity-safe).
14. **Transparency:** Operator can change priority weights, preview a what-if diff, apply. Waitlist positions re-rank live. Confirmed and currently-held allocations are **never revoked** by a rule change.

---

## 4. System architecture

```
┌──────────────────────┐        HTTPS/JSON         ┌───────────────────────────────────────┐
│ Passenger app (React)│ ───────────────────────▶ │ FastAPI (single instance, 1 worker)    │
│ Ops dashboard (React)│ ◀──── WebSocket ───────── │  ├─ REST routers (§12)                 │
└──────────────────────┘                           │  ├─ WS hub + in-process pub/sub (§13)  │
                                                   │  ├─ Domain services                    │
                                                   │  │   disruption · grouping · routing   │
                                                   │  │   priority · allocation · holds     │
                                                   │  │   cascade · pods · alternatives     │
                                                   │  │   metrics · what-if · audit         │
                                                   │  ├─ Background loops (lifespan)        │
                                                   │  │   batch_closer · hold_expirer       │
                                                   │  │   simulator_tick · kpi_broadcaster  │
                                                   │  ├─ Data adapter interface (mock impl) │
                                                   │  └─ Notification service (sim SMS)     │
                                                   └──────────────┬────────────────────────┘
                                                                  │ asyncpg
                                                       ┌──────────▼──────────┐
                                                       │ PostgreSQL 16        │
                                                       │ (Supabase/Neon/local)│
                                                       └──────────────────────┘
Static assets (seed): stations/nodes, edges, OSRM road polylines (pre-fetched JSON cache)
```

**Why single instance:** WebSocket fan-out and background loops live in-process. Concurrency safety comes from Postgres transactions + row locks, not from app memory. Run uvicorn with **exactly 1 worker**.

---

## 5. Domain model

### 5.1 Scenario
Every dynamic entity belongs to a `scenario`. Scenarios:
- **`potheri-demo`** (default, active): hub Potheri, ~400 seeded passengers, Chengalpattu–Chennai Beach suburban corridor + GST Road bus network.
- **`secondary-demo`** (small, ~50 passengers, different city/hub, e.g., Mumbai CSMT): proves the engine is location-agnostic. Switchable from the dashboard.

Scenario clock: on reset, `scenario.t0 = now()`. All seeded service times are **offsets from t0** (`depart_offset_min`), so the demo works at any real time of day.

### 5.2 Network
- **Nodes:** rail stations, bus stops, hubs. Hubs are nodes with `is_hub = true`; exactly one hub per scenario has `is_default_hub = true`.
- **Edges:** directed, `mode ∈ {rail, road, walk}`, with `base_minutes`, `distance_km`, `road_name`, `polyline` (GeoJSON LineString), `is_closed`.

**Corridor (potheri-demo) rail nodes in order (south → north):**
Chengalpattu → Paranur → Singaperumal Koil → Maraimalai Nagar → Kattankulathur → **Potheri (default hub)** → Guduvanchery → Urapakkam → Vandalur → Perungalathur → Tambaram → Chromepet → Pallavaram → Tirusulam (Airport) → Guindy → Mambalam → Egmore → Chennai Beach.

**Hubs (potheri-demo):** Potheri (default), Kattankulathur, Guduvanchery, Maraimalai Nagar (all within ~10 km).

**Road nodes:** major GST Road stops between Potheri and Guindy plus detour nodes on Vandalur–Kelambakkam Road / Outer Ring Road for re-routing.

Coordinates come from OpenStreetMap. The agent must store them in `seed/potheri/nodes.json` and **mark any coordinate it could not verify** in the stage report.

### 5.3 Services (scheduled runs with capacity)
A **service** = one vehicle run along an ordered stop list. `mode ∈ {local_train, bus, charter_bus, shuttle}`.
- The **original local trains** (e.g., "6:10 PM Chengalpattu → Chennai Beach local", mock ID `EMU-CGL-BCH-1810`) are **unreserved** (no seats table rows; `has_seat_inventory = false`). Passengers hold tickets for them.
- **Alternative services** (MTC/shuttle buses on GST Road, charter buses, locals running north of a disruption point, later locals) have **seat inventory** (`has_seat_inventory = true`) and are what the allocation engine assigns.
- Status: `scheduled | delayed | cancelled | running | completed | rerouted`.

### 5.4 Seats
One row per physical seat on seat-inventory services. `is_accessible` flag. Seats are the unit of locking (§9).

### 5.5 Passengers & groups
- Identity: `phone` + `ticket_id` (season pass ID or ticket ID). New registrations receive a virtual ticket ID (`VT-XXXXXX`).
- Needs: `wheelchair`, `elderly`, `with_children`, `medical`, `connection_deadline_at` (nullable, e.g., flight at Airport), `party_size` (1–6).
- `party_size > 1` creates a **group**; a group is allocated as a single unit to a single service (seats need not be adjacent).
- `is_seeded` distinguishes seed data from live registrations (judges).

### 5.6 Passenger journey state machine

```
REGISTERED ──(ticket assigned)──▶ BOOKED
BOOKED ──(disruption hits ticket/route)──▶ AFFECTED
AFFECTED ──(submits request)──▶ REQUESTED
REQUESTED ──(allocation: placed)──▶ HELD ──(accept)──▶ CONFIRMED
                                     │──(decline)──▶ WAITLISTED | UNRESOLVED
                                     └──(expire)───▶ WAITLISTED | UNRESOLVED
REQUESTED ──(allocation: not placed, waitlist exists)──▶ WAITLISTED ──(cascade offer)──▶ HELD
REQUESTED/WAITLISTED ──(no feasible option)──▶ UNRESOLVED
UNRESOLVED/WAITLISTED ──(joins pod / accepts multi-leg / alt hub)──▶ RESOLVED_ALT
CONFIRMED ──(route change breaks deadline)──▶ REOFFER (treated like AFFECTED, keeps seat until new accept)
BOOKED ──(delay < threshold)──▶ BOOKED (status shows delay only)
```
Allowed transitions must be enforced in one module (`domain/state.py`); invalid transitions raise `409 INVALID_STATE`.

---

## 6. Feature requirements

Each feature has an ID used in tests and stage reports.

### F1 — Scenario management
- F1.1 List scenarios; get active scenario; switch active scenario (operator).
- F1.2 **Reset scenario** (operator): truncate scenario-scoped dynamic data, reseed deterministically (fixed RNG seed), set `t0 = now()`. Must finish in **< 5 s** for 400 passengers.
- F1.3 Scenario config (stored on scenario row, editable by operator): `batch_window_seconds`, `hold_seconds`, `auto_run_on_batch_close`, `delay_threshold_minutes`, `hub_radius_km`, `open_booking_enabled`, `sim_speed`, `demo_mode`.

### F2 — Passenger registration & login
- F2.1 `POST /auth/register`: name, phone, destination_node_id, hub_node_id (optional), needs, party_size. Assigns virtual ticket on the scenario's **featured service** if it serves hub → destination, otherwise the next scheduled local from hub that serves destination. Returns JWT + passenger.
- F2.2 `POST /auth/login`: phone + ticket_id (seeded passengers, judges' backup logins). Optional mock OTP (`DEMO_OTP=1234`) behind a flag; default off.
- F2.3 JWT is long-lived (24 h) so judges stay logged in after refresh.
- F2.4 Rate limit `/auth/register`: 20/min per IP (venue Wi-Fi shares an IP, so it can't be lower).
- F2.5 Registration while a disruption is already active on the assigned service → passenger goes straight to `AFFECTED`.

### F3 — Hub detection
- F3.1 `POST /hubs/nearby {lat, lng}` → hubs within `hub_radius_km` (default 10) sorted by haversine distance, default hub flagged and pre-selected.
- F3.2 No hubs in radius, location denied, or no coordinates → return default hub (Potheri) only, with `reason: "default"`.
- F3.3 QR deep link params `scenario` and `hub` are honoured: `/join?scenario=potheri-demo&hub=potheri`.

### F4 — Destinations & options
- F4.1 `GET /destinations?hub=` → nodes reachable from hub on the network (searchable by `q`).
- F4.2 `GET /me/options` → feasible alternative services for the passenger: serves hub → destination (stop order respected), departs ≥ now, not cancelled, arrival before `connection_deadline_at` (if set), accessible if wheelchair, `seats_left ≥ party_size` shown (but infeasible-by-capacity options are still shown as "Full — join waitlist"). Fields: service_id, label, mode, depart_at, eta_at, seats_left, accessible_seats_left, transfers, is_multi_leg, legs[].
- F4.3 Options include **multi-leg** journeys (max 1 transfer, transfer penalty 10 min) computed by routing (§10).

### F5 — Disruption management (operator)
- F5.1 **Cancel service:** any service. Marks `cancelled`; flags affected passengers (ticket on service and boarding at/before the end of the service's remaining route).
- F5.2 **Delay service:** `delay_minutes`. Passenger is affected if `delay ≥ delay_threshold_minutes` (default 20) **or** delay breaks their `connection_deadline_at`. Affected-by-delay passengers get an extra option `WAIT_DELAYED` (keep original train).
- F5.3 **Close edge (road or rail):** sets `is_closed`. Rail closure → services crossing that edge are cancelled or short-terminated at the last reachable station (passengers beyond become affected). Road closure → bus services crossing it are **re-routed** (§10.3).
- F5.4 Resolve/reopen disruption (restores edge; does not auto-revert allocations).
- F5.5 Every disruption opens a **batch** (F6) automatically and creates seeded requests for seeded affected passengers (their choices come from seed data).
- F5.6 Disruption impact preview: `GET /ops/disruptions/preview?type=&target=` → affected count, by destination, before confirming.

### F6 — Requests & batch window
- F6.1 `POST /me/request {choice1_service_id?, choice2_service_id?, any_fastest: bool}`; at least one choice or `any_fastest=true`. Choices must be in the passenger's feasible options (capacity excluded). Idempotent per passenger per batch (re-submitting replaces the previous request while the batch is open).
- F6.2 Batch lifecycle: `open → closed → allocated`. At most one open batch per scenario. Requests made while no batch is open go into a new batch (auto-opened) — this covers late arrivals.
- F6.3 `batch_closer` loop: closes a batch at `closes_at`; if `auto_run_on_batch_close`, triggers an allocation run; else operator clicks **Run allocation**.
- F6.4 Affected passengers who never submitted a request are **not** auto-allocated (they're shown as "Not checked in" on the dashboard). Exception: seeded passengers always have seeded requests.

### F7 — Priority scoring (transparent)
- F7.1 Score = Σ (weight × normalised feature), features in [0, 1]:

| Feature key | Definition | Default weight |
|---|---|---|
| `medical` | 1 if medical need | 30 |
| `wheelchair` | 1 if wheelchair | 30 |
| `elderly` | 1 if elderly | 15 |
| `with_children` | 1 if travelling with children | 10 |
| `deadline_urgency` | 1 − clamp(minutes_to_deadline / 180, 0, 1); 0 if no deadline | 20 |
| `wait_time` | clamp(minutes_since_affected / 120, 0, 1) | 20 |

- F7.2 Group score = **max** member score (protects the vulnerable member). For groups registered as one record, the needs flags apply to the group.
- F7.3 Tie-breaks (in order): earlier `affected_at`, earlier `registered_at`/ticket time, lower passenger id. **Ticket price/class is never used.**
- F7.4 Each computed score stores a **breakdown** `{feature: points}` and a human explanation, e.g. `"Priority 82 = medical +30, waited 2h +20, connection in 50 min +14.4, elderly +15, children +2.6"`.
- F7.5 Rule sets are **versioned** (`priority_rules` table). Exactly one active per scenario. Changing weights creates a new version (old kept for audit).
- F7.6 `wait_time` makes scores time-dependent: scores are computed **at run start** (snapshot) and stored on the allocation/waitlist row; waitlist re-ranking recomputes scores at the time of a cascade or rule change.

### F8 — Allocation engine (deterministic, explainable)
Inputs: all requests in the closed batch + all WAITLISTED passengers (re-tried) + active rule version. Algorithm in §8. Requirements:
- F8.1 Honour choices where no conflict; priority decides conflicts; fallback order: choice1 → choice2 → auto options by ETA (only if `any_fastest` or both choices fail **and** passenger opted "allow auto"; default `allow_auto = true`).
- F8.2 Groups kept together on one service.
- F8.3 Hard constraints: capacity (never exceed), accessibility (wheelchair → accessible seat), stop order, departure ≥ now, arrival ≤ deadline, service not cancelled.
- F8.4 Two-pass accessibility: accessible seats first offered only to wheelchair passengers; released to general pool in pass 2.
- F8.5 Output per unit: `HELD` allocation (with `choice_rank ∈ {1, 2, auto}`), `WAITLISTED` entries (on choice1 and choice2 services), or `UNRESOLVED` + generated alternatives.
- F8.6 Every decision writes an audit entry with explanation, e.g. `"Choice 1 Bus-3 full: last 3 seats went to scores 91, 88, 85 (yours 72). Placed on choice 2 Bus-5."`
- F8.7 Only **one run at a time per scenario** (Postgres advisory lock). A run on 500 passengers must finish in **< 2 s**.
- F8.8 Run stats saved: placed_choice1, placed_choice2, placed_auto, waitlisted, unresolved, fill_rate per service, duration_ms.
- F8.9 (Stretch, flag `ENABLE_ORTOOLS`) OR-Tools CP-SAT mode maximising Σ(score × preference_bonus) for comparison; dashboard shows greedy vs optimal stats. Greedy remains the production mode.

### F9 — Holds, accept, decline, expiry
- F9.1 Placement creates allocation `status = held`, `hold_expires_at = now + hold_seconds`.
- F9.2 `POST /me/allocation/accept` → `confirmed` (idempotency key header required).
- F9.3 `POST /me/allocation/decline` → `declined`, seats released → cascade (F10). Passenger → WAITLISTED (if they have waitlist entries) else UNRESOLVED with alternatives.
- F9.4 `hold_expirer` loop (every 2 s): expires held allocations past `hold_expires_at` → `expired` → release → cascade.
- F9.5 Confirmed allocations are final unless a later disruption invalidates them (F12).

### F10 — Cascade & waitlist
- F10.1 Waitlist entries exist per (service, passenger-or-group) for choice services the unit was **not** placed on, plus swap requests (F11).
- F10.2 On seat release for service S: recompute scores for S's active waitlist entries, pick the highest-priority **feasible** unit (capacity incl. party size, accessibility, deadline still valid), create a held allocation, notify. Repeat while seats remain.
- F10.3 Waitlist position (`GET /me/status`) = rank among active entries for that service under current rules. Positions are broadcast on change (`waitlist.position_changed`).
- F10.4 Entries are removed when the unit is confirmed elsewhere (unless it's a swap entry), joins a pod, accepts an alternative, or the service departs.

### F11 — Swap
- F11.1 `POST /me/swap {service_id}`: allowed while HELD or CONFIRMED. Creates waitlist entry with `is_swap = true` on target service. Passenger keeps current seat.
- F11.2 When a swap offer is made, a **second** allocation `status = swap_held` is created. Accepting it atomically: confirms new, releases old (→ cascade). Declining/expiry drops the swap offer only.
- F11.3 Invariant: per passenger at most **1** active primary allocation (`held|confirmed`) and at most **1** `swap_held`.

### F12 — Re-routing & live changes
- F12.1 Road closure → for each affected bus service, compute new path via k-shortest paths (k=3) avoiding closed edges, choose min travel time, update stop list (intermediate stops that are no longer served are flagged), polyline, ETA. Service status `rerouted`.
- F12.2 For every held/confirmed allocation on a rerouted service: if the passenger's destination is still served and deadline still met → notify `eta.updated`; else → state `REOFFER`: passenger keeps seat but gets new options and a fresh request into the next batch (with `wait_time` preserved).
- F12.3 No path exists → service cancelled (F5.1 flow for its allocations).

### F13 — Alternatives for unplaced passengers
Generated for UNRESOLVED (and shown to WAITLISTED) passengers, ranked by ETA:
| Type | Description |
|---|---|
| `LATER_SERVICE` | Next services (even if later than preferred) with seats. |
| `MULTI_LEG` | Bus/shuttle to an unaffected station + local onward (e.g., Potheri → Tambaram bus, then Tambaram → Beach local). |
| `POD` | Join/create a shared cab/auto pod (F14). |
| `ALT_HUB` | Go to a nearby hub (walk/auto edge) that has a feasible service. |
| `WAIT_DELAYED` | Only for delay disruptions: stay on the original train. |
Accepting a non-seat alternative (POD, MULTI_LEG legs without seats, WAIT_DELAYED) → `RESOLVED_ALT`. Alternatives with seat inventory go through the normal request → allocation path (they are just services).

### F14 — Pods (shared cabs/autos)
- F14.1 Pod = origin hub, destination node, `mode ∈ {cab(4), auto(3)}`, capacity, members, status `forming | full | confirmed | departed | cancelled`.
- F14.2 `GET /me/pods/suggested` → forming pods whose destination equals the passenger's or lies on the same corridor within detour ≤ 15% of direct distance.
- F14.3 `POST /me/pods` (create), `POST /pods/{id}/join`, `POST /pods/{id}/leave`, `POST /pods/{id}/confirm` (any member once ≥ 2 members; auto-confirm when full). Join is transactional (row lock on pod) — never exceed capacity.
- F14.4 Fare estimate = `base_fare + per_km × route_km`, split equally; recomputed on membership change. (Config: cab base 100 ₹ + 18 ₹/km; auto base 30 ₹ + 15 ₹/km — mock values.)
- F14.5 Auto-matching (optional, flag): after each run, system proposes pods to unresolved passengers going to the same destination.

### F15 — Add capacity (operator)
- F15.1 `POST /ops/services` (charter/shuttle): route (stop node ids), depart offset, seats, accessible seats → creates service + seats + polyline.
- F15.2 If `auto_run_on_capacity_add` (default true): immediately opens a batch containing all UNRESOLVED and WAITLISTED units (their existing choices kept, plus auto) and runs allocation.

### F16 — Open booking
- F16.1 Operator toggles `open_booking_enabled`. While on: `POST /me/claim {service_id}` instantly holds seats if free (same lock path as allocation). Accessible seats claimable only by wheelchair passengers while any wheelchair passenger is WAITLISTED/UNRESOLVED.
- F16.2 Claims are audited like allocations (`choice_rank = "claim"`).

### F17 — Priority rules editor, what-if, transparency
- F17.1 `GET /ops/rules` (active + history), `POST /ops/rules/preview {weights}` → dry run: re-score current waitlists and simulate the next run on the current snapshot **inside a rolled-back transaction**. Returns diff: passengers moving up/down in waitlist, placed-count change, per-needs-class placement rate change.
- F17.2 `POST /ops/rules/apply {weights}` → new active version → re-rank all waitlists → broadcast `rules.updated` + position changes. Held/confirmed allocations untouched.
- F17.3 `GET /me/why` → passenger's current score breakdown, explanation text, the allocation decision explanation, waitlist position(s), and rule version used.
- F17.4 `GET /ops/audit?entity=&passenger_id=&limit=` → filterable audit log.

### F18 — Dashboard data (operator)
- F18.1 **KPIs:** affected, checked-in, requested, held, confirmed, waitlisted, unresolved, resolved_alt, not-checked-in, avg wait (min), median time-to-placement, overall fill rate.
- F18.2 **Clusters:** grouping by destination node × time bucket (`cluster_window_minutes`, default 30 for locals) × needs class (`accessible | priority | general`) → size, demand vs capacity of options serving it.
- F18.3 **Capacity board:** per service seats total / held / confirmed / free / accessible free, waitlist length. Free never negative.
- F18.4 **Allocation table:** paginated, filterable by status/destination/needs; columns: passenger, score, choice_rank, service, status, hold expiry, explanation.
- F18.5 **Unresolved queue** with generated alternatives per passenger.
- F18.6 **Fairness metrics:** placement rate per needs class, wait-time spread (p50/p90 per class), Gini of wait time, placement rate per destination (no destination starved).
- F18.7 **Map data:** nodes, edges (closed flagged), service polylines (current), vehicle positions (from simulator), cluster bubbles (node + size).
- F18.8 **Invariants panel:** `GET /ops/invariants` → over-allocated services count (must be 0), passengers with >1 primary allocation (must be 0), negative free seats (must be 0).

### F19 — Real-time updates
WebSocket push for every state change relevant to the viewer (§13). KPI snapshot broadcast to ops at most every 1 s (debounced).

### F20 — Simulator
- F20.1 `simulator_tick` (every 1 s): for each running/scheduled service, compute position along its polyline from schedule; movement visually accelerated by `sim_speed` (visual only — ETAs and timers stay real time).
- F20.2 Status auto-transitions: scheduled → running at depart time; running → completed at arrival. Departed services drop their waitlists and unclaimed holds expire.
- F20.3 Broadcast `vehicle.positions` to ops (and to passengers for their own allocated service) at 1 Hz.

### F21 — Notifications
- F21.1 Every passenger-facing event creates a `notifications` row and is pushed over WS.
- F21.2 Channel `sms_sim`: logged + visible in dashboard "SMS log". Optional real Twilio sandbox when `TWILIO_ENABLED=true` (only for registered judges' phones, never for seeded).
- F21.3 Templates: `disruption_alert`, `batch_open`, `placed`, `moved`, `waitlisted`, `offer_cascade`, `hold_expiring` (at 30 s left), `expired`, `eta_updated`, `reoffer`, `swap_offer`, `pod_update`.

### F22 — Data adapter (future real feeds)
- Interface `TransportDataAdapter` with `load_network()`, `load_services()`, `stream_service_updates()`. Implementation `MockAdapter` (seed files). Stub `GtfsRtAdapter` documented but not implemented. Business logic depends only on the interface.

### F23 — Stress test & invariants
- F23.1 Script `scripts/stress_test.py`: 1000 concurrent requests (open-booking claims on a service with 10 seats + concurrent accept/decline traffic) via `httpx.AsyncClient`.
- F23.2 Pass criteria: confirmed+held seats ≤ capacity for every service; zero 5xx; `GET /ops/invariants` all zeros. Endpoint `POST /ops/stress/run` (demo mode only) triggers it server-side and streams results to ops WS so it can be shown live.

---

## 7. Database schema (PostgreSQL 16)

Conventions: `id` = `BIGSERIAL` unless noted; all timestamps `timestamptz`; every dynamic table has `scenario_id` FK + index. Enum types created via Alembic.

```sql
-- Scenario & config
scenarios(
  id, slug TEXT UNIQUE, name TEXT, is_active BOOL,
  t0 TIMESTAMPTZ, default_hub_node_id BIGINT, featured_service_id BIGINT NULL,
  config JSONB NOT NULL,          -- F1.3 keys
  rng_seed INT NOT NULL, created_at)

-- Network
nodes(id, scenario_id, code TEXT, name TEXT, lat DOUBLE PRECISION, lng DOUBLE PRECISION,
  kind ENUM('rail_station','bus_stop','hub_only'), is_hub BOOL, is_default_hub BOOL,
  UNIQUE(scenario_id, code))
edges(id, scenario_id, from_node_id, to_node_id, mode ENUM('rail','road','walk'),
  distance_km NUMERIC, base_minutes NUMERIC, road_name TEXT NULL,
  polyline JSONB, is_closed BOOL DEFAULT false)

-- Services
services(id, scenario_id, code TEXT, label TEXT,
  mode ENUM('local_train','bus','charter_bus','shuttle'),
  status ENUM('scheduled','delayed','cancelled','running','completed','rerouted'),
  delay_minutes INT DEFAULT 0, has_seat_inventory BOOL,
  total_seats INT, accessible_seats INT,
  depart_at TIMESTAMPTZ, arrive_at TIMESTAMPTZ,
  polyline JSONB, created_by ENUM('seed','operator'), version INT DEFAULT 1)
service_stops(service_id, seq INT, node_id, arrive_at, depart_at, is_skipped BOOL DEFAULT false,
  PRIMARY KEY(service_id, seq))
seats(id, service_id, seat_no TEXT, is_accessible BOOL,
  status ENUM('free','held','confirmed') DEFAULT 'free',
  allocation_id BIGINT NULL, UNIQUE(service_id, seat_no))

-- Passengers
groups(id, scenario_id, size INT)
passengers(id, scenario_id, name, phone, ticket_id TEXT,
  is_seeded BOOL, group_id NULL, party_size INT DEFAULT 1,
  hub_node_id, destination_node_id, ticket_service_id NULL,
  wheelchair BOOL, elderly BOOL, with_children BOOL, medical BOOL,
  connection_deadline_at TIMESTAMPTZ NULL, allow_auto BOOL DEFAULT true,
  state ENUM(...§5.6), affected_at NULL, registered_at,
  UNIQUE(scenario_id, phone, ticket_id))

-- Disruptions
disruptions(id, scenario_id, type ENUM('cancellation','delay','closure'),
  service_id NULL, edge_id NULL, delay_minutes NULL, reason TEXT,
  created_at, resolved_at NULL)
passenger_disruptions(passenger_id, disruption_id, affected_at, PRIMARY KEY(...))

-- Batches, requests, runs
batches(id, scenario_id, status ENUM('open','closed','allocated'),
  opens_at, closes_at, trigger ENUM('disruption','late_request','capacity_add','reoffer','manual'))
-- partial unique index: one open batch per scenario
CREATE UNIQUE INDEX one_open_batch ON batches(scenario_id) WHERE status='open';
requests(id, scenario_id, batch_id, passenger_id, choice1_service_id NULL, choice2_service_id NULL,
  any_fastest BOOL, status ENUM('queued','processed','superseded'), created_at,
  UNIQUE(batch_id, passenger_id))
allocation_runs(id, scenario_id, batch_id NULL, rule_version_id, mode ENUM('greedy','ortools','preview'),
  started_at, finished_at, stats JSONB)

-- Allocations
allocations(id, scenario_id, run_id NULL, passenger_id, service_id,
  seat_count INT, choice_rank ENUM('1','2','auto','cascade','claim','swap'),
  status ENUM('held','swap_held','confirmed','declined','expired','released'),
  is_primary BOOL, hold_expires_at NULL, score NUMERIC, score_breakdown JSONB,
  explanation TEXT, created_at, updated_at)
-- invariants via partial unique indexes
CREATE UNIQUE INDEX one_primary_active ON allocations(passenger_id)
  WHERE is_primary AND status IN ('held','confirmed');
CREATE UNIQUE INDEX one_swap_active ON allocations(passenger_id)
  WHERE status = 'swap_held';

waitlist_entries(id, scenario_id, service_id, passenger_id, is_swap BOOL,
  score NUMERIC, score_breakdown JSONB, status ENUM('active','offered','removed'),
  created_at, UNIQUE(service_id, passenger_id))

-- Pods
pods(id, scenario_id, origin_node_id, destination_node_id, mode ENUM('cab','auto'),
  capacity INT, status ENUM('forming','full','confirmed','departed','cancelled'),
  route_km NUMERIC, fare_total NUMERIC, created_at)
pod_members(pod_id, passenger_id, seat_count INT, joined_at, PRIMARY KEY(pod_id, passenger_id))

-- Rules, audit, notifications
priority_rules(id, scenario_id, version INT, weights JSONB, is_active BOOL, created_at)
CREATE UNIQUE INDEX one_active_rule ON priority_rules(scenario_id) WHERE is_active;
audit_log(id, scenario_id, actor ENUM('system','operator','passenger'), actor_id NULL,
  action TEXT, entity_type TEXT, entity_id BIGINT, payload JSONB, explanation TEXT, created_at)
notifications(id, scenario_id, passenger_id, channel ENUM('push','sms_sim','sms'),
  template TEXT, payload JSONB, status ENUM('queued','sent','failed'), created_at)
idempotency_keys(key TEXT PRIMARY KEY, passenger_id, endpoint TEXT, response JSONB, created_at)
```

**Seat-count rule:** a held/confirmed allocation for a party of N owns exactly N seat rows (`seats.allocation_id`). `allocations.seat_count = N`.

---

## 8. Allocation algorithm (greedy, two-pass, deterministic)

```
run_allocation(scenario, batch_or_none, mode="greedy"):
  acquire pg_advisory_xact_lock(hash('alloc', scenario_id))
  rules   = active priority rule
  units   = requests in batch (status=queued) ∪ active waitlisted units not holding a primary seat
            (group = one unit; seat_need = party_size)
  for u in units: u.score, u.breakdown = score(u, rules, now)
  for u in units: u.options = ordered([choice1, choice2] + (auto_options_by_eta if allow_auto or any_fastest))
                  filter each option by HARD constraints except capacity
  order units by (-score, affected_at, registered_at, id)

  PASS 1 (accessible): for u in units where u.wheelchair:
      for opt in u.options:
         seats = lock_free_seats(opt, u.seat_need, accessible_first=True)   -- SELECT ... FOR UPDATE SKIP LOCKED
         if seats: place(u, opt, seats); break
  PASS 2 (general): for u in units not placed:
      for opt in u.options:
         seats = lock_free_seats(opt, u.seat_need, accessible_ok = not wheelchair_pending_for(opt))
         if seats: place(u, opt, seats); break
  for u not placed:
      for opt in {choice1, choice2} ∩ feasible-except-capacity: upsert waitlist_entry(opt, u)
      if no waitlist entries: state=UNRESOLVED; generate alternatives (F13)
      else: state=WAITLISTED
  write explanations + audit for every unit
  mark requests processed, batch allocated, save run stats
  COMMIT → publish events after commit (never before)
```

- `wheelchair_pending_for(opt)`: true if any not-yet-placed wheelchair unit lists `opt` — keeps accessible seats for them through pass 2.
- `lock_free_seats` selects seats ordered by `(is_accessible ASC unless accessible_first, seat_no)` → deterministic.
- `place()` sets seats `held`, creates allocation `held`, `is_primary=true`, `hold_expires_at`, `choice_rank`, explanation.
- **Explanation generation** (`domain/explain.py`): templated, includes which higher-scored units took the contested seats (top 3 scores), passenger's score, rule version.
- **Preview mode**: identical code path inside a transaction that is rolled back; returns diff instead of committing; no events.

---

## 9. Concurrency & consistency (no over-allocation)

1. **Seat rows are the lock unit.** Every path that takes a seat (allocation, cascade, claim, swap) uses `SELECT ... FROM seats WHERE service_id=:s AND status='free' ... FOR UPDATE SKIP LOCKED LIMIT :n` inside one transaction, then updates them. If fewer than `n` rows come back → not enough capacity → no partial placement (rollback that unit's savepoint).
2. **Partial unique indexes** enforce one primary active allocation and one swap per passenger (§7).
3. **Advisory lock** serialises allocation runs per scenario; cascade/claim do not take it (they rely on row locks) but a running allocation run makes claim return `409 ALLOCATION_IN_PROGRESS` (check advisory lock via `pg_try_advisory_xact_lock`).
4. **Idempotency:** `Idempotency-Key` header required on accept/decline/claim/swap/pod join; stored response replayed on retry.
5. **Events after commit:** domain services return a list of events; the router publishes them only after successful commit.
6. **Background loops** each use their own session; failures are logged and the loop continues (never crash the app).
7. **Isolation:** default READ COMMITTED + row locks. Invariant checker query (F18.8) runs in REPEATABLE READ.
8. **DB connection:** use a direct (session-mode) connection, not a transaction-mode pooler, because advisory/row locks need session semantics. Pool size 10–20.

---

## 10. Routing

### 10.1 Graph
`networkx.MultiDiGraph` per scenario, built from nodes/edges at startup and rebuilt on closure/reopen. Edge weight = `base_minutes`. Closed edges excluded.

### 10.2 Journey search
- Direct options: services whose stop list contains hub then destination (in order), not cancelled.
- Multi-leg: for each intermediate transfer node T, leg1 service hub→T and leg2 service T→destination with `leg2.depart_at ≥ leg1.arrive_at + 10 min`. Max 1 transfer. Rank by arrival time, then transfers. Max 5 results.
- Walk/auto edges allow `ALT_HUB` options.

### 10.3 Road re-routing
On road edge closure: for each bus service whose consecutive stops traverse the edge, compute `nx.shortest_simple_paths` (k=3) between the stop before and after the closure on road edges only; choose the fastest; splice into the stop list (skipped stops flagged); recompute times from `base_minutes`; rebuild polyline by concatenating cached edge polylines. Bump `services.version`.

### 10.4 Polylines
`scripts/fetch_polylines.py` queries OSRM (public demo server) **once, offline, before the hackathon demo**, for each road edge, and writes `seed/<scenario>/road_polylines.json`. Runtime never calls OSRM. Fallback: straight line between node coordinates (rail edges always straight lines).

---

## 11. Seed data (potheri-demo)

Deterministic (`rng_seed = 42`). Files in `seed/potheri/`: `nodes.json`, `edges.json`, `road_polylines.json`, `services.yaml`, `passengers.yaml` (generator config), `rules.json`.

- **Local trains:** several up and down locals along the corridor at offsets (e.g., t0+15, +25, +35, +50 min). One is the **featured service** ("6:10 PM Beach local", `EMU-CGL-BCH-1810` style mock code) — judges' virtual tickets go on it. Operator can still cancel **any** train.
- **Alternative capacity:** 4–6 MTC/shuttle buses Potheri → Tambaram → Guindy (40–50 seats, 2–4 accessible), 2 charter buses to Guindy/Egmore, later locals from Tambaram northwards (seat inventory modelled as limited "assured standing/seat" capacity for the demo).
- **Passengers:** ~400 at Potheri hub, ticket on the featured service + others. Destinations: Tambaram, Chromepet, Airport (Tirusulam), Guindy, Egmore, Chennai Beach (weighted). Needs mix: wheelchair 5%, elderly 10%, with_children 12%, medical 3%, connection deadline 15% (mostly Airport). ~60 groups of 2–5.
- **Seeded requests:** created automatically when a disruption hits them (choice distribution from generator config: 70% choice1+choice2, 20% any_fastest, 10% choice1 only).
- **Capacity calibration (`capacity_mode: calibrated`):** on reset, after generating passengers, set each popular alternative's seats = seeded first-choice demand on it + `demo_leftover_seats` (default 3) so judges compete for the last few seats; set at least one destination's total capacity below demand so the unresolved queue is non-empty.
- **Judge backup logins:** 6 pre-made seeded passengers with distinct profiles (wheelchair, family of 4, airport deadline, elderly, general ×2), listed in `seed/potheri/judge_logins.md` (phone + ticket_id).
- **secondary-demo:** ~50 passengers, small network, one hub; same generator.

---

## 12. REST API contract

Base: `/api/v1`. JSON. Auth: `Authorization: Bearer <jwt>`. Errors use one envelope:
```json
{ "error": { "code": "SEAT_UNAVAILABLE", "message": "human text", "details": {} } }
```
Error codes: `VALIDATION_ERROR(422)`, `UNAUTHORIZED(401)`, `FORBIDDEN(403)`, `NOT_FOUND(404)`, `INVALID_STATE(409)`, `SEAT_UNAVAILABLE(409)`, `ALLOCATION_IN_PROGRESS(409)`, `BATCH_CLOSED(409)`, `HOLD_EXPIRED(409)`, `POD_FULL(409)`, `RATE_LIMITED(429)`, `IDEMPOTENCY_CONFLICT(409)`.

### 12.1 Public / auth
| Method | Path | Body / Query | Returns |
|---|---|---|---|
| GET | `/health` | — | `{status, db, version}` |
| GET | `/scenarios/active` | — | scenario summary (slug, name, default hub) |
| POST | `/hubs/nearby` | `{scenario, lat?, lng?}` | `{hubs:[{id,name,distance_km,is_default}], selected_hub_id, reason}` |
| GET | `/destinations` | `scenario, hub, q?` | `[{node_id, name, kind}]` |
| POST | `/auth/register` | `{scenario, name, phone, hub_node_id?, destination_node_id, needs:{wheelchair,elderly,with_children,medical,connection_deadline_at?}, party_size, allow_auto?}` | `{token, passenger, ticket:{ticket_id, service}}` |
| POST | `/auth/login` | `{scenario, phone, ticket_id, otp?}` | `{token, passenger}` |
| POST | `/auth/ops-login` | `{password}` | `{token}` |

### 12.2 Passenger (role=passenger)
| Method | Path | Notes |
|---|---|---|
| GET | `/me` | passenger profile + state |
| PATCH | `/me` | update needs/destination/hub (only in REGISTERED/BOOKED/AFFECTED) |
| GET | `/me/trip` | ticket service, live status, delay, disruption info |
| GET | `/me/options` | F4.2 (includes multi-leg, seats_left, full flag) |
| POST | `/me/request` | F6.1 → `{request, batch:{id, closes_at}}` |
| GET | `/me/status` | state, current allocation (hold countdown), swap offer, waitlist positions, batch countdown |
| POST | `/me/allocation/accept` | header `Idempotency-Key`; accepts primary or `{allocation_id}` for swap_held |
| POST | `/me/allocation/decline` | header `Idempotency-Key` |
| POST | `/me/swap` | `{service_id}` |
| POST | `/me/claim` | `{service_id}` (open booking only) |
| GET | `/me/why` | F17.3 |
| GET | `/me/alternatives` | F13 list |
| POST | `/me/alternatives/accept` | `{type, ref}` for non-seat alternatives → RESOLVED_ALT |
| GET | `/me/pods/suggested` | F14.2 |
| POST | `/me/pods` | create `{destination_node_id, mode}` |
| POST | `/pods/{id}/join` · `/leave` · `/confirm` | Idempotency-Key on join |
| GET | `/me/notifications` | latest 50 |

### 12.3 Operator (role=operator)
| Method | Path | Notes |
|---|---|---|
| GET | `/ops/scenarios` · POST `/ops/scenarios/{slug}/activate` | F1.1 |
| POST | `/ops/scenarios/{slug}/reset` | F1.2 |
| PATCH | `/ops/scenarios/{slug}/config` | F1.3 |
| GET | `/ops/network` | nodes, edges, closed flags (map) |
| GET | `/ops/services` · POST `/ops/services` | list / add capacity F15 |
| GET | `/ops/disruptions/preview` | F5.6 |
| POST | `/ops/disruptions` | `{type, service_id?, edge_id?, delay_minutes?, reason}` |
| POST | `/ops/disruptions/{id}/resolve` | F5.4 |
| GET | `/ops/batches/current` · POST `/ops/batches/current/close` | manual close |
| POST | `/ops/allocation/run` | `{mode:"greedy"|"ortools"}` |
| GET | `/ops/allocation/runs/{id}` | stats |
| GET | `/ops/kpis` | F18.1 |
| GET | `/ops/clusters` | F18.2 |
| GET | `/ops/capacity` | F18.3 |
| GET | `/ops/allocations` | F18.4 (`status, destination, needs, page, page_size`) |
| GET | `/ops/unresolved` | F18.5 |
| GET | `/ops/fairness` | F18.6 |
| GET | `/ops/map` | F18.7 snapshot |
| GET | `/ops/invariants` | F18.8 |
| GET | `/ops/rules` · POST `/ops/rules/preview` · POST `/ops/rules/apply` | F17 |
| GET | `/ops/audit` | F17.4 |
| GET | `/ops/notifications` | SMS log |
| POST | `/ops/open-booking` | `{enabled}` |
| POST | `/ops/stress/run` | demo_mode only, F23.2 |
| GET | `/ops/passengers/{id}` | full passenger detail incl. why |

Also served: OpenAPI at `/docs`; exported `contracts/openapi.json`; example payloads in `contracts/examples/*.json` (for the frontend's mock layer).

---

## 13. WebSocket contract

Endpoints: `/ws/passenger?token=` and `/ws/ops?token=`. Server → client messages:
```json
{ "type": "offer.created", "ts": "2026-11-05T18:10:00+05:30", "scenario": "potheri-demo", "data": { } }
```
Client → server: `{"type":"ping"}` → `{"type":"pong"}`. Server pings every 20 s; clients reconnect with backoff and re-fetch `/me/status` or `/ops/kpis` on reconnect (events are not replayed).

| Event | To | Data |
|---|---|---|
| `service.status_changed` | ops, affected passengers | service_id, status, delay_minutes |
| `disruption.created` / `disruption.resolved` | ops, affected passengers | disruption summary |
| `batch.opened` / `batch.closed` | ops, passengers in batch | batch_id, closes_at |
| `allocation.run_started` / `allocation.run_completed` | ops | run_id, stats |
| `allocation.result` | passenger | state, allocation, explanation |
| `offer.created` (cascade) / `swap.offer_created` | passenger | allocation, hold_expires_at |
| `hold.expiring` / `hold.expired` | passenger | allocation_id |
| `allocation.confirmed` / `allocation.declined` | ops | ids |
| `seat.released` | ops | service_id, count |
| `waitlist.position_changed` | passenger | service_id, position |
| `eta.updated` | passenger, ops | service_id, eta_at, polyline_version |
| `service.rerouted` | ops, affected passengers | service_id, polyline, skipped_stops |
| `vehicle.positions` | ops (all), passenger (own service) | [{service_id, lat, lng, progress}] |
| `kpi.updated` | ops | KPI snapshot (debounced 1 s) |
| `rules.updated` | ops, passengers | version |
| `pod.updated` | pod members, ops | pod |
| `stress.progress` / `stress.result` | ops | counts, invariant result |
| `passenger.registered` | ops | passenger summary (judges appearing live) |

---

## 14. Background loops (FastAPI lifespan)

| Loop | Interval | Responsibility |
|---|---|---|
| `batch_closer` | 1 s | close due batches; auto-run allocation if configured |
| `hold_expirer` | 2 s | expire holds/swap holds; release; cascade; `hold.expiring` at 30 s left |
| `simulator_tick` | 1 s | vehicle positions, status transitions (F20) |
| `kpi_broadcaster` | 1 s | emit `kpi.updated` if dirty flag set |
| `cleanup` | 60 s | remove waitlists of departed services; prune idempotency keys > 24 h |

All loops: try/except per iteration, structured logs, never kill the process.

---

## 15. Non-functional requirements

| Area | Requirement |
|---|---|
| Correctness | 0 over-allocations under 1000 concurrent requests (F23). |
| Latency | p95 < 200 ms for passenger reads; allocation run < 2 s for 500 units; reset < 5 s. |
| Determinism | Same seed + same request set + same rules → identical allocation output (test enforced). |
| Availability (demo) | Deployed on Render/Railway + local fallback (`docker compose up`) with a phone hotspot. |
| Security | Passenger JWT scoped to own data; ops password via env; CORS restricted to frontend origin(s); rate limiting on auth; no secrets in repo. |
| Observability | structlog JSON logs; request id; run stats; `/health`. |
| Privacy | Seeded data is fake. Judges' phone numbers never sent to Twilio unless `TWILIO_ENABLED` and they opted in. |
| Time zone | Store UTC; API returns ISO with offset; display Asia/Kolkata in examples. |

---

## 16. Configuration (env)

```
DATABASE_URL=postgresql+asyncpg://...        # direct/session connection
JWT_SECRET=...
JWT_TTL_HOURS=24
OPS_PASSWORD=...
CORS_ORIGINS=https://<frontend>.vercel.app,http://localhost:5173
DEFAULT_SCENARIO=potheri-demo
DEMO_MODE=true                 # enables stress endpoint, shorter timers
BATCH_WINDOW_SECONDS=150       # demo: 30
HOLD_SECONDS=600               # demo: 120
DELAY_THRESHOLD_MINUTES=20
HUB_RADIUS_KM=10
SIM_SPEED=10
ENABLE_ORTOOLS=false
DEMO_OTP_ENABLED=false
TWILIO_ENABLED=false
TWILIO_SID= TWILIO_TOKEN= TWILIO_FROM=
LOG_LEVEL=INFO
```
Env values seed the scenario config on reset; operator can override per scenario at runtime (F1.3).

---

## 17. Project structure

```
backend/
  app/
    main.py                 # app factory, lifespan, routers, CORS
    config.py               # pydantic-settings
    db.py                   # async engine/session, advisory lock helpers
    models/                 # SQLAlchemy models (one file per aggregate)
    schemas/                # Pydantic request/response models (contract)
    api/v1/                 # routers: public, auth, me, pods, ops
    ws/                     # hub, connection manager, event types
    domain/
      state.py              # passenger state machine
      scoring.py            # priority score + breakdown
      explain.py            # explanation templates
      allocation.py         # §8 engine (+ preview)
      holds.py  cascade.py  swap.py  claim.py
      disruption.py  grouping.py  alternatives.py  pods.py
      routing.py            # graph, journeys, reroute
      metrics.py  fairness.py  invariants.py
    adapters/
      base.py  mock.py  gtfs_rt_stub.py
    services/notifications.py
    jobs/                   # background loops
    seed/loader.py  seed/generator.py
  seed/potheri/ seed/secondary/
  scripts/fetch_polylines.py  scripts/stress_test.py  scripts/export_openapi.py
  contracts/openapi.json  contracts/examples/
  migrations/               # Alembic
  tests/                    # pytest, pytest-asyncio
  Dockerfile  docker-compose.yml  pyproject.toml  README.md
```

**Dependencies:** fastapi, uvicorn[standard], sqlalchemy[asyncio]>=2, asyncpg, alembic, pydantic>=2, pydantic-settings, networkx, pyjwt, slowapi, structlog, httpx, pyyaml, pytest, pytest-asyncio, (optional) ortools, twilio.

---

## 18. Testing requirements

| Test | Asserts |
|---|---|
| Scoring unit tests | weights × features, group max, tie-breaks, price never used |
| Allocation determinism | same input twice → identical allocations |
| Choice honouring | no-conflict case → everyone gets choice1 |
| Conflict | higher score wins contested seat; loser gets choice2 with explanation naming the cause |
| Accessibility two-pass | wheelchair passenger with lower score than non-need passenger still gets accessible seat |
| Groups | party of 4 never split; not placed if only 3 seats |
| Hold expiry & cascade | expired seat goes to top waitlisted feasible unit |
| Swap | accepting swap releases old seat atomically; invariants hold |
| Rule apply | waitlist re-ranked; held/confirmed untouched |
| Road closure | bus rerouted, ETA changed, deadline-violating passengers → REOFFER |
| Rail closure | services short-terminated; passengers beyond → AFFECTED |
| Delay threshold | 15 min delay not affected; 25 min affected; deadline break affected |
| Hub nearby | radius filter, default fallback |
| Concurrency | 200 parallel claims on 10 seats → exactly 10 successes |
| Invariants endpoint | zeros after all of the above |
| Reset | < 5 s, deterministic counts |

---

## 19. Demo support requirements (backend must enable all of these)

Setup: dashboard on projector (`/ops`), backend deployed, ~400 seeded passengers at Potheri, capacity calibrated (only 2–3 seats left on likely judge choices). QR → `https://<frontend>/join?scenario=potheri-demo&hub=potheri`.

| # | Operator action | Judges' phones | Backend capability |
|---|---|---|---|
| 1 | Show normal dashboard | Scan QR, register (location → Potheri pre-selected), get virtual ticket on featured local → "On time" | F2, F3, F4.1, `passenger.registered` |
| 2 | Cancel the local train | All phones flip to "Cancelled" simultaneously | F5.1, F21, WS |
| 3 | Narrate | Pick 1st/2nd choice | F4.2, F6 |
| 4 | Batch closes (30 s) → Run allocation; capacity bars fill to 100%, never beyond | Placed ✓ / Moved / Waitlisted #n | F8, F18.3 |
| 5 | Point out conflict | "Why this?" score breakdown | F17.3 |
| 6 | A judge declines | Another judge receives the seat | F9.3, F10 |
| 7 | Close GST Road near Vandalur | ETAs update; buses re-route on map | F12, F20 |
| 8 | Raise medical weight → preview → apply | Queue positions change | F17 |
| 9 | Unresolved queue → Add charter bus | Waitlisted judges placed / pod options | F13–F15 |
| 10 | Run stress test | — | F23 → "0 over-allocations" |
| 11 | Switch to secondary scenario for 10 s | — | F1.1 (proves location-agnostic) |

Backups: judge backup logins (§11), one-click reset (F1.2), local docker compose fallback.

---

## 20. Stage-gated build plan for the coding agent

### 20.1 Rules
- Execute **one stage at a time**. When the stage's acceptance criteria pass, write the Stage Report (§20.3) and **STOP**. Wait for `Proceed to Stage N` (the user may first send back requested changes — apply them before continuing).
- Each stage must leave the app **runnable** (`uvicorn app.main:app` starts, `/health` OK, tests green).
- Commit at the end of each stage: `stage-N: <summary>`.
- Never silently skip a requirement — if deferred, list it under "Deferred / not done" with a reason.

### 20.2 Stages

| Stage | Scope | Feature IDs | Acceptance criteria |
|---|---|---|---|
| **0 — Foundation** | Project skeleton (§17), config, async DB, Alembic baseline, error envelope, structlog, CORS, `/health`, Dockerfile + compose (Postgres), pytest setup | — | App boots; `/health` reports DB OK; `docker compose up` works; 1 passing test |
| **1 — Schema, seed & contracts** | All models + migration (§7, incl. partial unique indexes), seed files for potheri + secondary (§11), generator with calibrated capacity, `fetch_polylines.py` (with straight-line fallback), reset endpoint (F1.2), scenario endpoints (F1.1, F1.3), OpenAPI export + `contracts/examples` for **every** endpoint in §12 (stubs allowed) | F1, F22 (MockAdapter) | Reset < 5 s, deterministic counts printed; examples JSON present for frontend mocks; judge_logins.md generated |
| **2 — Auth, hubs, passenger read APIs** | Register/login/ops-login, JWT roles, rate limit, hub nearby, destinations, `/me`, `/me/trip`, state machine module | F2, F3, F4.1, §5.6 | Register → token → `/me/trip` shows featured service; hub fallback tested |
| **3 — Routing, disruptions, options, batches** | Graph build, direct + multi-leg journeys, `/me/options`, disruption create/preview/resolve (cancel, delay, closure incl. rail short-termination & road reroute), affected detection, seeded request creation, batch lifecycle + `batch_closer`, `/me/request` | F4.2–F4.3, F5, F6, F12.1, F12.3 | Cancel featured train → ~400 affected, batch opens, seeded requests exist; road closure reroutes a bus with new polyline |
| **4 — Scoring & allocation engine** | Priority rules (versioned), scoring + breakdown, explanation templates, §8 two-pass greedy engine, advisory lock, run stats, audit writes, `/ops/allocation/run`, `/me/status`, `/me/why` | F7, F8 (F8.9 optional), F17.3, F17.4 | All allocation tests in §18 pass; run on 500 units < 2 s; determinism test passes |
| **5 — Holds, cascade, swap, claim** | Accept/decline with idempotency, `hold_expirer`, cascade, waitlist positions, swap, open booking claim, REOFFER handling for reroutes | F9, F10, F11, F12.2, F16 | Concurrency test (200 claims / 10 seats) passes; invariants all zero |
| **6 — Alternatives, pods, capacity add** | Alternatives generation & accept, pods (suggest/create/join/leave/confirm/fare), add-capacity service + auto re-run | F13, F14, F15 | Unresolved passenger sees all applicable alternative types; adding charter places waitlisted units automatically |
| **7 — Realtime, simulator, notifications** | WS hub (both endpoints), every event in §13 emitted after commit, KPI debounce, simulator tick + status transitions, notifications + SMS log (+ optional Twilio) | F19, F20, F21 | A scripted WS client receives the full event sequence for demo steps 1–9 |
| **8 — Ops analytics & rules editor** | KPIs, clusters, capacity board, allocations table, unresolved, fairness, map snapshot, invariants, rules preview (rolled-back dry run) + apply + re-rank, scenario switch | F17.1–F17.2, F18 | Preview returns diff without changing DB; apply re-ranks waitlists live; fairness numbers sane |
| **9 — Hardening, stress, deploy** | `stress_test.py` + `/ops/stress/run`, full test suite, demo-mode timers, README (setup, env, demo runbook, judge logins), deploy to Render/Railway, local fallback verified | F23, §15, §19 | 1000-request stress → 0 over-allocations, 0 5xx; deployed URL healthy; full demo script runs end-to-end via API |

**Integration checkpoints with frontend:** after Stage 1 (contracts/examples), after Stage 4 (real allocation data), after Stage 7 (WebSockets live).

### 20.3 Stage Report template (agent must output exactly this structure, then STOP)

```markdown
# Stage N Report — <stage name>

## 1. Summary
<2–4 sentences: what this stage delivered>

## 2. Completed items
| Feature ID | Item | Files | Status |
|---|---|---|---|

## 3. Files created / modified
- path — purpose

## 4. Database changes
- migrations added, tables/indexes changed

## 5. API / WebSocket contract
- endpoints added/implemented (method + path)
- **Contract changes vs PRD:** none | <list with reason>

## 6. Tests
- tests added; command run; result (passed/failed counts); coverage of acceptance criteria

## 7. Acceptance criteria check
| Criterion | Result | Evidence (command/output) |
|---|---|---|

## 8. Assumptions & decisions
- <any interpretation of ambiguity>

## 9. Deferred / not done
- <item> — reason — proposed stage

## 10. Known issues / risks
-

## 11. How to run & verify
<exact commands>

## 12. Next stage preview
<what Stage N+1 will do; any input needed from the user>

**STOPPED — awaiting "Proceed to Stage N+1".**
```

---

## 21. Glossary
- **Hub:** station where stranded passengers gather (default Potheri).
- **Service:** one vehicle run with an ordered stop list.
- **Unit:** a single passenger or a group, allocated atomically.
- **Batch window:** period during which requests are collected before one allocation run.
- **Hold:** temporary seat reservation awaiting accept.
- **Cascade:** re-offering a released seat to the waitlist in priority order.
- **Pod:** shared cab/auto formed by unplaced passengers with compatible destinations.
- **Open booking:** post-allocation first-come-first-served claims on leftover seats, still capacity-safe.
