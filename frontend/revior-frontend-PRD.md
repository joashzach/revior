# Revior — Frontend PRD
**Disruption recovery & passenger coordination platform** · Hackathon problem statement PS2 ("The Stranded Network") · 24-hour build

| Field | Value |
|---|---|
| Document | Frontend Product Requirements Document (implementation-ready, for the coding agent) |
| Version | 1.0 · 2026-11-06 |
| Product name | **Revior** (use this name everywhere in the UI; "The Stranded Network" is only the hackathon problem-statement title) |
| Owner | Frontend developer (backend is built in parallel by the backend developer) |
| Coding agent | Google Antigravity (workspace = the `frontend/` folder) |
| Stack | React 18 + Vite + TypeScript · Tailwind CSS · shadcn/ui (Radix) · react-router · TanStack Query · react-leaflet · Recharts · Motion (`motion/react`) · qrcode.react · sonner · vaul · Zod + react-hook-form |
| Default scenario / hub | `potheri-demo` · Potheri Railway Station, Chennai |
| Build mode | **Staged build order, continuous execution** (§19). Build F0 → F8 in order without stopping; one final report at the end. |

---

## 0. The document set — what each file is, where it lives, how they connect

### 0.1 Files in the frontend workspace

**Initial state (as handed over):** all files sit in the workspace root, including `SKILL.md`:
```
frontend/
├── SKILL.md                                   ← skill file, initially in the root (must be moved, see §0.5)
├── design.md
├── revior-frontend-PRD.md
└── stranded-network-frontend-API-contract.md
```

**Required layout (after the very first task, §0.5):**
```
frontend/                                      ← open THIS folder as the Antigravity workspace
├── .agent/
│   └── skills/
│       └── interface-craft/
│           └── SKILL.md                       ← design-engineering skill (generic rules + anti-AI-slop)
├── design.md                                  ← Revior's visual identity (project tokens, fonts, components)
├── revior-frontend-PRD.md                     ← THIS FILE: what to build, in what order
├── stranded-network-frontend-API-contract.md  ← every endpoint, type, WS event, screen spec
├── contracts/examples/*.json                  ← real example payloads (arrive after backend Stage 1)
├── .env.example
└── src/ ...
```
The backend PRD (`stranded-network-backend-PRD.md`) lives with the backend. The frontend agent does **not** need it. If it is present, it is reference only.

### 0.2 Authority & precedence (when two documents disagree)
| Question | Authority (highest first) |
|---|---|
| **What** to build, scope, screens, stages, acceptance criteria | 1. this PRD |
| **Data**: endpoints, request/response shapes, TS types, error codes, WS events, state machine | 1. API contract · 2. `contracts/examples/*.json` (when present, they reflect the real backend) |
| **How it looks**: colours, fonts, spacing, radius, shadows, components, voice | 1. `design.md` · 2. `SKILL.md` (interface-craft) defaults |
| **How it's crafted**: states, accessibility, motion rules, polish, anti-slop | 1. `SKILL.md` (design.md may override specific choices) |

Rules:
- `design.md` **overrides** any colour, font, spacing, radius or motion value in `SKILL.md` and in this PRD. Values in this PRD are fallbacks, used only if `design.md` doesn't define them.
- The API contract **overrides** this PRD on data shapes. If the contract and the example JSON disagree, follow the example JSON and **report the mismatch**.
- Never invent an endpoint or field. If something is missing, mock it, mark it `// TODO(contract)` and list it in the final report.

### 0.3 When to (re)read each document — mandatory
| Moment | Read |
|---|---|
| Before writing any code | This PRD fully · API contract fully · design.md fully · SKILL.md fully |
| Before building or restyling **any** screen/component | design.md (tokens/components) + SKILL.md §0 workflow, §1 anti-slop, §7 states |
| Before wiring **any** API call or WS event | API contract §3 (conventions), §4 (types), the endpoint row in §5, the event row in §6 |
| Before adding **any** animation, scroll or map motion | SKILL.md §5 (motion tokens), §8 (transitions) + design.md motion section |
| When hitting an error, ambiguity or conflict | The relevant document again **before** deciding anything; log the decision in the final report |
| At the end of every stage | SKILL.md §13 polish checklist + §14 review mode on the screens built in that stage (fix findings before moving on; record them for the final report) |

### 0.4 How the skill is used
- After the move in §0.5, the skill is `.agent/skills/interface-craft/SKILL.md`. Antigravity loads skills from `.agent/skills/` in the workspace. If it is not auto-loaded, read the file manually and follow it anyway. Record which happened in the final report.
- Follow the skill's workflow (§0 of the skill): read `design.md` → state the direction sentence (take it from design.md if it has one) → tokens → structure → states → motion → polish → anti-slop audit → verify.
- The skill's anti-slop bans (§1) apply **unless design.md explicitly chooses otherwise**.

### 0.5 First task: move the skill into place (before anything else)
`SKILL.md` starts in the workspace root. Before writing any code:
1. Create the folder `.agent/skills/interface-craft/` (note the leading dot in `.agent`).
2. **Move** (not copy) `SKILL.md` from the root to `.agent/skills/interface-craft/SKILL.md`. Keep the file name exactly `SKILL.md`, in capitals, and don't edit its content.
   - macOS/Linux/Git Bash: `mkdir -p .agent/skills/interface-craft && mv SKILL.md .agent/skills/interface-craft/SKILL.md`
   - Windows PowerShell: `New-Item -ItemType Directory -Force .agent\skills\interface-craft; Move-Item SKILL.md .agent\skills\interface-craft\SKILL.md`
3. Verify: the root no longer has `SKILL.md`, the new path exists, and the frontmatter starts with `name: "interface-craft"`.
4. Check whether Antigravity now lists `interface-craft` as an available skill. Whether it does or not, read the file fully and follow it.
5. Make sure `.agent/` is **not** in `.gitignore`, so the skill is committed with the project.

---

## 1. Product overview

### 1.1 Problem
A cancelled service at a local hub (local train) strands hundreds of people at once. Existing tools re-plan journeys one passenger at a time, and first-come-first-served booking during a surge is unfair (the fastest phone wins), wastes seats, splits families and over-books.

### 1.2 What Revior does
Revior treats the disruption as a **group recovery event**:

```
Disruption → affected passengers alerted → they pick preferred alternatives (1st / 2nd / Any, fastest)
→ requests collected in a short BATCH WINDOW → allocation engine places everyone at once
   (choices honoured where possible, transparent priority score resolves conflicts,
    families kept together, accessible seats to wheelchair users first, never over-allocated)
→ timed SEAT HOLD (Accept / Decline / Swap) → declines CASCADE to the waitlist
→ ALTERNATIVES for the unplaced (later service, multi-leg, shared-cab pods, nearby hub)
→ operator dashboard shows and controls all of it live
```

**Tagline (UI):** *Passengers choose. Revior decides fairly. Every decision is explainable.*

### 1.3 Surfaces to build
| Surface | Device | Users |
|---|---|---|
| **Landing page** `/` | all | public, judges |
| **Passenger app** (`/demo-join`, `/join`, `/login`, `/qr-login`, `/trip`, `/options`, `/status`, `/why`, `/alternatives`, `/profile`) | **laptop-first (1280–1920 px), fully mobile-responsive down to 360 px**: judges open it on phones via the Join QR | stranded passengers, judges using demo personas |
| **Operator dashboard** (`/ops/login`, `/ops`) | **desktop/projector-first** (1366 px+, readable from 4 m) | operator/presenter |

### 1.4 Out of scope (frontend)
Native apps, payments, real ticket booking, multi-language (English only; keep strings in one module so i18n can be added later), offline-first PWA (a basic manifest is optional).

---

## 2. Users, roles & access
| Role | Entry | Token key (localStorage) | Can access |
|---|---|---|---|
| Demo persona (judge) | Scan the shared Join QR → `/demo-join` → pick persona | `revior_passenger_token` | passenger routes |
| Registered passenger | `/join` (email + password) or `/login` | `revior_passenger_token` | passenger routes |
| Passenger via personal QR | `/qr-login?t=…` | `revior_passenger_token` | passenger routes |
| Operator | `/ops/login` (password) | `revior_ops_token` | `/ops` only |

- Both tokens can exist on the presenter laptop at once. Keep them in separate keys and separate API clients.
- There is no operator link on the landing page. The operator opens `/ops` directly.
- Contract references: §2 (auth), §5.2 (auth endpoints), §5.3 (personas).

---

## 3. Information architecture & routing

### 3.1 Route table
| Route | Guard | Layout | Spec |
|---|---|---|---|
| `/` | public | Marketing | §11 |
| `/demo-join` | public | PassengerAuth | §8.1 |
| `/join` | public | PassengerAuth | §8.2 |
| `/login` | public | PassengerAuth | §8.3 |
| `/qr-login` | public | PassengerAuth | §8.3 |
| `/trip` | passenger | PassengerShell | §8.4 |
| `/options` | passenger | PassengerShell | §8.5 |
| `/status` | passenger | PassengerShell | §8.6 |
| `/why` | passenger | PassengerShell | §8.7 |
| `/alternatives` | passenger | PassengerShell | §8.8 |
| `/profile` | passenger | PassengerShell | §8.9 |
| `/ops/login` | public | OpsAuth | §9.1 |
| `/ops` | operator | OpsShell | §9 |
| `*` | — | Marketing | 404: "This stop doesn't exist" + link home |

### 3.2 Guards & state-driven navigation
- No passenger token on a passenger route → `/login?next=<path>`. No ops token on `/ops` → `/ops/login`.
- On `401` from any call: clear **that** token, toast "Session ended, please log in again", go to the matching login.
- **State router** (contract §1.2): after login, on app load, and on every `allocation.result`, `disruption.created` or state change, navigate by `passenger.state`:

| state | route |
|---|---|
| `REGISTERED`, `BOOKED` | `/trip` |
| `AFFECTED`, `REOFFER` | `/options` |
| `REQUESTED`, `HELD`, `CONFIRMED`, `WAITLISTED`, `RESOLVED_ALT` | `/status` |
| `UNRESOLVED` | `/alternatives` |

- Auto-navigation happens only on a **state change**, never while the user is viewing `/why`, `/profile` or `/alternatives` by choice. In that case, show a sticky banner with a "Go" button instead.
- SPA hosting needs a rewrite of all paths to `index.html`, so `/qr-login` and `/demo-join` deep links work (§17).

---

## 4. Architecture

### 4.1 Folder structure
```
src/
  app/            router.tsx, providers.tsx (QueryClient, Theme, Toaster), guards.tsx
  config/         env.ts (validated with zod), constants.ts, strings.ts (all UI copy)
  styles/         tokens.css (generated from design.md), globals.css, leaflet.css overrides
  api/
    http.ts       fetch wrapper: base URL, auth header, error envelope → ApiError, idempotency
    types.ts      TS types copied from contract §4 (single source)
    passenger.ts  one function per passenger endpoint (contract §5.2–5.5)
    ops.ts        one function per ops endpoint (contract §5.6)
    public.ts     health, scenarios, hubs, destinations, personas
    queryKeys.ts  all TanStack Query keys
  realtime/
    ws.ts         socket manager: connect, ping, backoff, reconnect → refetch
    events.ts     event type map (contract §6) + invalidation table (§6.3 here)
    usePassengerSocket.ts, useOpsSocket.ts
  mocks/          mock adapter (reads contracts/examples or hand fixtures), mock WS script
  hooks/          useServerClock, useCountdown, useStateRouter, useGeolocation, useIdempotencyKey
  components/
    ui/           shadcn primitives, re-themed to tokens
    brand/        ReviorLogo (wordmark), Tagline
    common/       StatusPill, CountdownRing, HoldTimer, ScoreBars, EmptyState, ErrorState,
                  SkeletonBlocks, LiveDot, NumberRoll, QRPanel, NeedChips, ServiceCard
    map/          ReviorMap, layers/*, VehicleMarker, Legend, EdgePopup
  features/
    landing/  personas/  auth/  trip/  options/  status/  why/  alternatives/  pods/  profile/
    ops/      topbar/ kpis/ map/ controls/ capacity/ clusters/ allocations/ unresolved/
              rules/ fairness/ audit/ messages/ personas/ stress/ qr/
  pages/          one file per route, composing features
  test/           vitest setup, fixtures
```

### 4.2 Environment (`.env.example`)
```
VITE_API_BASE=http://localhost:8000/api/v1
VITE_WS_BASE=ws://localhost:8000
VITE_USE_MOCKS=true
VITE_DEFAULT_SCENARIO=potheri-demo
VITE_MAP_TILE_URL=https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png
VITE_MAP_ATTRIBUTION=&copy; OpenStreetMap contributors
```
Validate env at boot with zod. If it's invalid, show a full-page config error (dev only).

### 4.3 Data layer rules
- **TanStack Query** for all server state. No server data in global stores. A small Zustand store is allowed only for UI state (selected tab, map layer toggles, QR mode mirror).
- Query defaults: `staleTime: 5s` passenger, `2s` ops KPIs, `retry: 1` (never retry 4xx), `refetchOnWindowFocus: true`.
- Mutations: `onSuccess` → set/invalidate the affected queries; `onError` → map `ApiError.code` to UI using contract §3.
- **Idempotency:** `accept`, `decline`, `claim`, `swap` and pod `join` send `Idempotency-Key`. Generate one UUID per user tap (`useIdempotencyKey`) and reuse it on retry. Disable the button while pending.
- **Server clock:** `useServerClock` stores `offset = server_time − Date.now()` from `/health`, `/me/status` and every WS `ts`. Every countdown uses `Date.now() + offset`. This prevents drift between judges' phones.

### 4.4 Mock layer (must exist from Stage F0)
- `VITE_USE_MOCKS=true` routes every API function to `mocks/` and starts a mock WS emitter.
- Fixtures: hand-written from contract §4 types until `contracts/examples/*.json` arrive, then load those files directly.
- **Mock demo script** (timer-driven, restartable from a hidden dev menu): t+5 s judge joined → t+10 s `disruption.created` → batch open 30 s → `allocation.result` → t+60 s `offer.created` (cascade) → t+75 s `service.rerouted` → t+90 s `rules.updated`.
- Mocks stay available forever as a demo fallback (`?mock=1` query param forces mock mode at runtime).

---

## 5. Visual system (from design.md, crafted with SKILL.md)

### 5.1 Tokens
- Read `design.md` and generate `src/styles/tokens.css`: CSS custom properties for colour, type, spacing, radius, shadow and motion. Mirror them in `tailwind.config` (`theme.extend`) so Tailwind classes use the tokens. **Never hard-code hex values in components.**
- If design.md lacks a token, use the matching SKILL.md default (§2 colour in OKLCH, §3 type, §4 space, §5 motion) and list it under "Fallback tokens used" in the final report.
- shadcn/ui components must be **fully re-themed** to these tokens. The stock shadcn look is a slop tell (SKILL.md §1).

### 5.2 Semantic status colours (same mapping everywhere: pills, map, toasts, charts)
| Meaning | Token | Used for |
|---|---|---|
| success | `--success` | placed, confirmed, rerouted route line, invariants OK |
| warning | `--warning` | held, waitlisted, delayed, reoffer, hold ≤ 30 s |
| danger | `--danger` | cancelled, expired, unresolved, closed edge, invariant failed |
| info | `--info` | neutral updates, scheduled, batch open |
| accent | `--accent` | primary actions, selected option, focus ring |

Never rely on colour alone. Every status also shows an icon and a word ("Cancelled", "Waitlisted #2").

### 5.3 Brand
- Product name **Revior**. The wordmark is set in the design.md display font with typographic treatment only. No generated or copied logos, and no emoji logo.
- Favicon: a simple monogram "R" in accent on the background token (SVG).
- Voice: calm, specific and kind. People reading it are stressed on a platform. Use the copy rules from SKILL.md §1 and the design.md voice section. All strings live in `config/strings.ts`.

### 5.4 Layout bases
- Passenger, **laptop-first** (≥ 1024 px): two-pane layouts that use the width. Left sidebar nav (Trip · Status · Why · Alternatives · Profile) with the main content and a contextual side panel, e.g. options list + selected-option detail/summary, status card + mini-map + Why breakdown, persona picker as a wide grid. Content max-width ~1280 px. Primary actions are reachable by keyboard and shown in a sticky action bar.
- Passenger, **tablet** (768–1023 px): collapsible sidebar, side panel stacks under the main content.
- Passenger, **mobile** (< 768 px), must be just as polished: single column, bottom nav **Trip · Status · Why · More**, sticky thumb-reachable primary action, bottom sheets (vaul) instead of side panels, inputs ≥ 16 px, touch targets ≥ 44 px, safe-area insets, `100dvh`. Never a squeezed desktop layout.
- Ops: 12-column grid at 1366–1920 px. Projector-legible: KPI numerals ≥ 32 px, labels ≥ 14 px, no thin weights for data.
- Landing: fluid 360 → 1920 px, designed for laptop first, fully polished on phones, max content width ~1200 px.

---

## 6. Backend integration

### 6.1 Endpoint ownership by screen
| Screen / feature | Endpoints (contract §5) |
|---|---|
| App boot | `GET /health` (server time), `GET /scenarios/active` |
| Persona picker | `GET /demo/personas`, `POST /auth/demo-claim` |
| Register | `POST /hubs/nearby`, `GET /destinations`, `POST /auth/register` |
| Login / QR login | `POST /auth/login`, `POST /auth/qr-login` |
| Trip | `GET /me`, `GET /me/trip` |
| Options | `GET /me/options`, `PATCH /me` (allow_auto), `POST /me/request`, `POST /me/claim` |
| Status | `GET /me/status`, `POST /me/allocation/accept`, `POST /me/allocation/decline`, `POST /me/swap` |
| Why | `GET /me/why` |
| Alternatives & pods | `GET /me/alternatives`, `POST /me/alternatives/accept`, `GET /me/pods/suggested`, `POST /me/pods`, `POST /pods/{id}/join\|leave\|confirm` |
| Profile | `GET/PATCH /me`, `GET /me/login-qr`, `POST /me/demo-switch`, `POST /auth/logout` |
| Notifications | `GET /me/notifications`, `POST /me/notifications/read` |
| Ops login | `POST /auth/ops-login` |
| Ops top bar | `GET /ops/scenarios`, `POST /ops/scenarios/{slug}/activate`, `POST …/reset`, `GET/PATCH …/config`, `POST /ops/open-booking` |
| Ops KPIs | `GET /ops/kpis`, `GET /ops/invariants` |
| Ops map | `GET /ops/map`, `GET /ops/network` |
| Ops controls | `GET /ops/services`, `GET /ops/disruptions/preview`, `POST /ops/disruptions`, `GET /ops/disruptions`, `POST /ops/disruptions/{id}/resolve`, `GET /ops/batches/current`, `POST /ops/batches/current/close`, `POST /ops/allocation/run`, `POST /ops/services` |
| Ops tabs | `/ops/capacity`, `/ops/clusters`, `/ops/allocations`, `/ops/passengers/{id}`, `/ops/passengers/{id}/login-qr`, `/ops/unresolved`, `/ops/rules`, `/ops/rules/preview`, `/ops/rules/apply`, `/ops/fairness`, `/ops/audit`, `/ops/notifications`, `/ops/demo/personas*`, `/ops/stress/run` |

### 6.2 WebSockets
- Passenger: `${VITE_WS_BASE}/ws/passenger?token=…`. Ops: `${VITE_WS_BASE}/ws/ops?token=…`.
- Ping every 20 s. Reconnect backoff 1 s → 2 s → 5 s → 10 s (max). **On reconnect, refetch** `/me/status` (passenger) or `/ops/kpis` + `/ops/map` (ops). Events are not replayed.
- WS down for more than 5 s → polling fallback: passenger `/me/status` every 3 s, ops `/ops/kpis` every 2 s. Show a "Reconnecting…" live dot state.
- One socket per app, created after login and closed on logout or token swap (persona switch → reconnect with the new token).

### 6.3 Event → UI action table
| Event (contract §6) | Query invalidation | Immediate UI |
|---|---|---|
| `service.status_changed` | trip, options / services, map | Passenger: red full-width alert if own ticket is cancelled |
| `disruption.created` / `.resolved` | trip, options, status / disruptions, kpis, map | Passenger → `/options` |
| `batch.opened` / `.closed` | status, options / batch | Start/stop countdown |
| `allocation.run_started` / `.run_completed` | — / capacity, allocations, kpis, clusters, unresolved | Ops: spinner → run-stats toast |
| `allocation.result` | status, why | Result card animates in, state router |
| `offer.created` | status | Toast "A seat opened up for you!" + hold timer |
| `swap.offer_created` | status | Swap banner |
| `hold.expiring` | — | Timer turns danger, vibrate (`navigator.vibrate(200)` if supported) |
| `hold.expired` | status | Toast, refetch |
| `allocation.confirmed` / `.declined`, `seat.released` | capacity, allocations, kpis | Flash the capacity row once |
| `waitlist.position_changed` | status | NumberRoll on position |
| `eta.updated` | status / map | Update ETA text |
| `service.rerouted` | status / map, services | Ops map: old line → muted, new line → success colour; passenger banner |
| `vehicle.positions` | — (write to map store) | Animate markers |
| `kpi.updated` | set `kpis` query data directly | NumberRoll per tile |
| `rules.updated` | why, status / rules, allocations | — |
| `pod.updated` | pods / unresolved | — |
| `passenger.registered`, `persona.claimed` / `.released` | — / personas, kpis | Ops toast "Judge joined: Wheelchair user → Guindy" |
| `notification.created` | notifications | Bell badge + toast |
| `stress.progress` / `.result` | — | Live counters → result card |

### 6.4 Error handling
Map every error code exactly as in contract §3. Global rules: network failure → toast "Can't reach Revior, retrying"; 5xx → toast plus a retry button on the affected block; never a blank screen. Every page has an error boundary with a "Reload" action.

---

## 7. Shared components (build once, reuse)
| Component | Purpose / rules |
|---|---|
| `StatusPill` | state → token colour + icon + label; sizes sm/md/lg |
| `CountdownRing` / `HoldTimer` | server-clock based, tabular nums, `mm:ss`, warning at ≤ 30 s, danger at ≤ 10 s, `aria-live="polite"` announcing each minute and the last 10 s |
| `ServiceCard` | mode icon, label, depart → ETA, legs, seats-left bar, accessible badge, deadline tag, full → waitlist state, selected rank badge (1 / 2) |
| `ScoreBars` | horizontal bars per priority feature with points, total, rule version |
| `NumberRoll` | digit pop-in animation for changing numbers (SKILL.md §8), tabular nums |
| `NeedChips` | wheelchair, elderly, children, medical, deadline, party size (icon + text) |
| `QRPanel` | `qrcode.react` SVG, quiet zone ≥ 4 modules, high contrast, caption, sizes corner/fullscreen |
| `LiveDot` | connected / reconnecting / offline |
| `EmptyState`, `ErrorState`, `Skeleton*` | per SKILL.md §7 |
| `ReviorMap` | §10 |
| Toasts (sonner), bottom sheets (vaul), dialogs (Radix) | re-themed; focus trap, Esc, restore focus |

Icons: one icon set only (Lucide by default unless design.md says otherwise). Stroke width matches text weight (SKILL.md §11).

---

## 8. Passenger app — screen requirements
All screens are **laptop-first and fully mobile-responsive** (§5.4). Passenger shell: top bar (Revior wordmark, LiveDot, notification bell); on laptop a left sidebar nav + main + contextual side panel; on mobile a bottom nav **Trip · Status · Why · More** (More → Alternatives, Profile) and side panels become bottom sheets. Every requirement below must work at both 1280 px and 360 px. Detailed behaviour is in contract §8 (its mobile notes apply to the < 768 px layout). Requirements with IDs:

### 8.1 `/demo-join` — Persona picker (judges)
- **P-1.1** Heading: "You're stranded at Potheri. Pick who you are." Sub-copy explains it's a live demo.
- **P-1.2** Persona grid from `GET /demo/personas`: icon/emoji, title (e.g. "Wheelchair user → Guindy"), summary, destination, party size, need chips. Taken personas are greyed out with a "Taken" badge and can't be selected.
- **P-1.3** "Surprise me" button (`surprise: true`). Small link "Register as yourself" → `/join`.
- **P-1.4** Tap → `POST /auth/demo-claim` → store token → `/trip`. `PERSONA_TAKEN` → refetch the grid + toast.
- **P-1.5** Refresh the grid every 3 s while open.
- **P-1.6** Loading skeleton grid; empty state if no personas ("Surprise me" still works, since the backend auto-creates one).

### 8.2 `/join` — Register
- **P-2.1** Step 1, location: explain why, then request geolocation → `POST /hubs/nearby`. List hubs nearest first with Potheri pre-selected. "Change hub" opens the list. Denied, timed out (8 s) or no geolocation → Potheri with the note "Using Potheri (default)".
- **P-2.2** Step 2, form (react-hook-form + zod): name, email, password (≥ 6, show/hide), phone (optional), destination (searchable combobox, `GET /destinations?hub=`), party size stepper 1–6, need toggles (wheelchair, elderly, travelling with children, medical), optional connection deadline (time picker; helper "e.g. a flight at the Airport"), "Allow auto-placement if my choices are full" (default on).
- **P-2.3** Submit → `POST /auth/register` → success sheet showing the virtual ticket ID → `/trip`. `EMAIL_TAKEN` → inline error with a link to login.
- **P-2.4** Inputs ≥ 16 px. Correct `type`/`autocomplete`/`inputmode`. Errors show inline on blur.

### 8.3 `/login` and `/qr-login`
- **P-3.1** `/login`: email + password → `POST /auth/login`. `INVALID_CREDENTIALS` shows inline. Link "Use my login QR" explains how to scan your QR with the phone camera.
- **P-3.2** `/qr-login?t=`: auto `POST /auth/qr-login` with a full-screen loader → `/trip`. On failure: "This QR has expired. Log in with email" + button.
- **P-3.3** Honour `?next=` after login.

### 8.4 `/trip` — Home
- **P-4.1** Ticket card: virtual ticket ID, service label (e.g. "6:10 PM Chengalpattu → Chennai Beach local"), hub → destination, departure, status pill (On time / Delayed +N min / Cancelled).
- **P-4.2** Normal state: quiet reassurance line, "We'll alert you if anything changes."
- **P-4.3** Disruption (WS or refetch): full-width danger alert with the reason (e.g. "Cancelled: waterlogging near Guduvanchery"), CTA "Choose an alternative", auto-navigate to `/options` after 2 s (state router).
- **P-4.4** Delay below threshold: warning pill only. Delay with `WAIT_DELAYED` option: alert with CTA.

### 8.5 `/options` — Choose alternatives
- **P-5.1** Batch banner: "Requests close in 0:24" (CountdownRing, server clock). No batch → "Your request will join the next allocation round."
- **P-5.2** `ServiceCard` list from `GET /me/options`, sorted by ETA. Multi-leg cards show the leg timeline ("Bus to Tambaram → local to Beach"). Full options show "Full: join waitlist".
- **P-5.3** Selection: first tap = **1st**, second tap on another card = **2nd** (rank badges; tap again to unselect). "Any, fastest" toggle clears and disables manual picks. "Allow auto-placement" toggle → `PATCH /me {allow_auto}`.
- **P-5.4** Sticky bottom CTA "Send my request" (disabled until valid) → `POST /me/request` → `/status`. While the batch is open, the CTA becomes "Update request".
- **P-5.5** Open booking on (option with `seats_left > 0` and config flag): card shows "Grab now" → `POST /me/claim` with idempotency.
- **P-5.6** `WAIT_DELAYED` appears as its own card for delay disruptions.
- **P-5.7** `BATCH_CLOSED` → toast "That round just closed. You're in the next one" and resubmit automatically.

### 8.6 `/status` — Result & actions
- **P-6.1** `REQUESTED`: CountdownRing "Allocating in 0:18" with a summary of the choices and "Edit request" (back to `/options` while the batch is open).
- **P-6.2** `HELD`: result card. Placed on 1st choice → success treatment "Placed on your 1st choice ✓". 2nd/auto → warning treatment "Moved to Bus-5: see why". Shows service, departure, ETA, seats, **HoldTimer**, primary **Accept**, secondary **Decline** (confirm sheet), link "Why this?", "Request a different option" (swap picker sheet listing other options → `POST /me/swap`).
- **P-6.3** `CONFIRMED`: boarding-pass card (service, seats, departure, live ETA). Mini-map of own vehicle (§10.6). Re-route banner on `service.rerouted`.
- **P-6.4** `WAITLISTED`: one row per waitlist entry, "Waitlisted #2 of 7 for Bus-3" (NumberRoll), the line "We'll offer you a seat the moment one frees up", and a link to Alternatives.
- **P-6.5** `REOFFER`: warning "Your bus was re-routed and may miss your deadline. Choose again; you keep your seat until then" → `/options`.
- **P-6.6** `RESOLVED_ALT`: card for the chosen alternative (pod members and fare, multi-leg legs, or "Waiting for the delayed train").
- **P-6.7** Swap offer present: top banner with its own HoldTimer, **Switch** (accept with `allocation_id`) / **Keep current** (decline with `allocation_id`).
- **P-6.8** Cascade offer (`offer.created`): toast, then the result card animates in (enter transition per SKILL.md §8).
- **P-6.9** Use `headline` from `MyStatus` as the screen's main sentence when present.

### 8.7 `/why` — Transparency
- **P-7.1** Total score as a large numeral, plus `ScoreBars` per feature (medical, wheelchair, elderly, with children, deadline urgency, wait time) with points.
- **P-7.2** `explanation` and `decision_explanation` sentences, waitlist positions, rule version and weights table ("Rules v3").
- **P-7.3** Footer: "Ticket price is never used to decide who gets a seat."
- **P-7.4** Refetch on `rules.updated` and animate the bar changes.

### 8.8 `/alternatives` (includes pods)
- **P-8.1** Alternative cards by ETA: Later service · Multi-leg · Pod · Nearby hub · Wait for delayed train. Each shows title, description, ETA and legs.
- **P-8.2** Seat-bearing (`requires_allocation: true`) → "Request this" (`POST /me/request`). Others → "Choose this" (`POST /me/alternatives/accept`) with a confirm sheet.
- **P-8.3** Pods: suggested pods (`2/4` seats, fare per seat, destination, mode cab/auto) → **Join**. **Create pod** sheet (mode select). Inside a pod: member list, live fare split, **Confirm pod** (≥ 2 members), **Leave**. `POD_FULL` → toast + refetch.

### 8.9 `/profile`
- **P-9.1** Name, email, hub, destination, party size, needs. Editable only in `REGISTERED`, `BOOKED` and `AFFECTED`; otherwise read-only with an explanation.
- **P-9.2** **My login QR**: `GET /me/login-qr` → QRPanel, expiry text, "Show full screen".
- **P-9.3** **Switch passenger** (demo personas only): "Next persona" / "Pick a persona" (opens the persona grid in a sheet) → `POST /me/demo-switch` → replace token → reconnect WS → `/trip`.
- **P-9.4** Logout → `POST /auth/logout` → clear token → `/`.

### 8.10 Notifications
- **P-10.1** Bell with unread count. Drawer lists `GET /me/notifications`. Opening the drawer marks them read. Toast on `notification.created`.

---

## 9. Operator dashboard — requirements (`/ops`)

### 9.1 `/ops/login`
- **O-1.1** Password field → `POST /auth/ops-login` → `/ops`. Show inline errors. No "forgot password".

### 9.2 Layout (contract §9.1)
```
TOP BAR    Revior · Scenario ▼ · LiveDot · Batch countdown · Join QR [Corner|Full|Hidden] · Open booking ⏻ · Reset · Logout
KPI ROW    Affected · Checked-in · Requested · Held · Confirmed · Waitlisted · Unresolved · Avg wait · Fill rate · Invariants
MAIN       Live map (≈60%)                     | Control panel (≈40%): Disruptions · Allocation · Add capacity
TABS       Capacity | Clusters | Allocations | Unresolved | Rules | Fairness | Audit | Messages | Demo personas | Stress test
```
Use a sticky top bar. On viewports < 1280 px, the map and control panel stack vertically (it should still work, but projector is the target).

### 9.3 Requirements
| ID | Area | Requirement |
|---|---|---|
| O-2.1 | Top bar | Scenario dropdown (`/ops/scenarios`, activate with a confirm dialog), LiveDot, batch countdown, Join QR segmented control (writes `join_qr_mode` via config PATCH), Open booking switch, **Reset scenario** (confirm dialog, then refetch everything), Logout |
| O-2.2 | KPI row | 10 tiles, NumberRoll on change, tabular nums. Invariants tile shows success ✓ when `ok`, danger ✗ otherwise (poll `/ops/invariants` every 5 s) |
| O-2.3 | Disruptions | Type tabs: **Cancel** (any service from `/ops/services`, searchable), **Delay** (service + minutes), **Close edge** (edge dropdown or map click). Reason text. **Preview** → affected count by destination. **Confirm** → toast + map update. Active disruptions list with **Resolve** |
| O-2.4 | Allocation | Batch status + request count, **Close batch now**, **Run allocation** (mode select; OR-Tools option hidden unless the backend reports it), last-run stats card (placed 1st/2nd/auto, waitlisted, unresolved, duration ms) |
| O-2.5 | Add capacity | Form: label, mode (charter/shuttle), ordered stops (multi-select from network nodes with drag reorder), departs in N min, seats, accessible seats → `POST /ops/services` → toast "Re-allocating…" |
| O-3.1 | Capacity tab | Row per service: label, mode, departure, stacked bar (confirmed / held / free) **clamped to 100%**, `x/total`, accessible free badge, waitlist length. Row flashes once on `seat.released` |
| O-3.2 | Clusters tab | Destination × time bucket × needs class, size, demand-vs-capacity bar (danger when demand > capacity) |
| O-3.3 | Allocations tab | Server-paginated table with filters (status, destination, needs), search, columns from contract §5.6, truncated explanation with tooltip. Row click → **Passenger drawer** (`/ops/passengers/{id}`: status, why, login QR via `/ops/passengers/{id}/login-qr`) |
| O-3.4 | Unresolved tab | Queue sorted by waited time, alternatives per row, header button **Add charter bus** (opens Add capacity) |
| O-3.5 | Rules tab | Slider per weight (0–50) with numeric input, current vs edited. **Preview** → diff panel (placed delta, placement rate by needs class before→after, top movers with position before→after). **Apply** → confirm → version toast. History list |
| O-3.6 | Fairness tab | Recharts, re-themed: placement rate by needs class (bar), wait p50/p90 by class, placement by destination, Gini number with the caption "lower is fairer" |
| O-3.7 | Audit tab | Paginated log (time, actor, action, entity, explanation), filter by passenger ID |
| O-3.8 | Messages tab | Simulated email/SMS/push log |
| O-3.9 | Demo personas tab | Table: persona, claimed at, current state, **Release**. **Release all** (confirm) |
| O-3.10 | Stress test tab | Inputs (requests 1000, seats 10) → **Run** → live counters (sent, ok, conflicts, errors) → big result card "1000 requests · 10 seats · 0 over-allocations · 0 errors" |
| O-4.1 | Join QR | `scenario.join_url` → QRPanel. **Corner**: ~140 px card over the map's bottom-right, caption "Scan to join as a stranded passenger". **Fullscreen**: overlay with the QR at ~70vh, caption, live "Judges joined: N" counter (`persona.claimed`), Esc / "Start demo" → Corner. **Hidden**: nothing shown. The mode persists through config |
| O-5.1 | Toasts | Judge joined, run completed, disruption created, re-route, rule applied, reset done |

---

## 10. Map implementation (react-leaflet)

### 10.1 Setup
- `react-leaflet` + `leaflet`. Import `leaflet/dist/leaflet.css` once. Use `preferCanvas` for performance with many polylines.
- **Vite marker icon gotcha:** don't use default PNG markers. Use `L.divIcon` / `CircleMarker` styled with tokens.
- Tiles: `VITE_MAP_TILE_URL` with `VITE_MAP_ATTRIBUTION` (attribution must stay visible; follow the tile provider's usage policy). Mute the base map so data stands out: CSS `filter` on `.leaflet-tile-pane` (e.g. `grayscale(1) contrast(0.9) brightness(1.05)`, tinted per design.md). For a dark theme, use an inverted/tinted variant from design.md.
- Initial view: `fitBounds` to all network nodes with 40 px padding. Disable scroll-wheel zoom until the map is clicked (avoids scroll traps on the landing page and passenger mini-map).

### 10.2 Coordinate gotcha (must handle)
GeoJSON `LineString.coordinates` from the backend are **`[lng, lat]`**. Leaflet expects **`[lat, lng]`**. Convert in one utility (`toLatLngs`) and unit-test it.

### 10.3 Layers (toggleable via a legend/layer control)
| Layer | Source | Style |
|---|---|---|
| Stations / stops | `/ops/map.nodes` | small CircleMarker, neutral; rail vs bus shapes differ (circle vs square divIcon) |
| Hubs | nodes with `is_hub` | larger marker; **Potheri (default hub)** gets an accent ring + permanent label |
| Road / rail edges | `/ops/network.edges` | thin neutral lines; **closed edge = thick danger line, dashed**, with a closure icon at the midpoint |
| Service routes | `/ops/map.services[].polyline` | colour by status (scheduled info, running accent, delayed warning, cancelled danger dashed, rerouted **success**) |
| Rerouted transition | `service.rerouted` | old polyline fades to muted (300 ms), new polyline draws in (stroke-dashoffset animation, 600 ms) |
| Vehicles | `vehicle.positions` (1 Hz) | divIcon by mode; **interpolate** position between updates with `requestAnimationFrame` over ~1 s (ease-in-out) so markers glide, never jump; heading rotation optional |
| Clusters | `/ops/map.clusters` | translucent circles at the node, radius ∝ √size, label with count |

### 10.4 Interactions
- Click a service line or vehicle → side sheet with service details and its capacity row.
- Click an edge → popup "Close this road" → pre-fills the Disruptions form (type Close edge) and focuses Preview.
- Hover tooltips with name and status (pointer devices only).
- Legend card (bottom-left) explaining colours with words, not just swatches.

### 10.5 Performance
Memoise layers by data version. Update vehicle markers imperatively (refs), not by re-rendering the whole map. Throttle cluster re-renders to 1/s. Target 60 fps on the presenter laptop.

### 10.6 Passenger mini-map (`/status` when CONFIRMED)
A small static-height map (200 px) showing own service route + own vehicle marker + hub/destination. No other layers. Zoom and drag disabled (tap opens a full-screen sheet with zoom). Reduced motion → no marker interpolation; jump to position.

---

## 11. Landing page (`/`)
- **L-1 Hero:** "Revior" wordmark, tagline, one-line problem ("When a local train is cancelled, hundreds are stranded at once. Revior gets them home together, fairly."). CTAs: **Try the live demo** → `/demo-join`, **Join as a passenger** → `/join`, **Log in** → `/login`. Show the real product (a framed screenshot or live-rendered passenger status card and dashboard KPI strip), not abstract blobs.
- **L-2 How it works:** 4 steps: Disruption detected → Passengers choose → Revior allocates fairly → Everyone gets a way home. One scroll-driven narrative section is allowed (SKILL.md §9, e.g. a pinned phone mock where the status changes step by step). Must have a reduced-motion static fallback.
- **L-3 Why it's different:** 3 points: Group recovery, not one-by-one · Transparent priority, never ticket price · Zero over-allocation (show the stress-test result).
- **L-4 Footer:** hackathon PS2 credit, team names, GitHub link placeholder.
- **L-5** Static content. Only optional `GET /scenarios/active`. Lighthouse performance ≥ 90 on desktop and mobile. No operator link.

---

## 12. Motion & interaction rules (summary; full rules in SKILL.md §5, §8–§10)
- Use motion tokens from design.md (fallback to SKILL.md §5). Never `transition: all`. Animate transform and opacity only.
- Passenger result cards: enter with opacity + 8 px rise (+ optional blur), staggered children. Exits are quieter and shorter.
- Button press `scale(0.96)`. Icon swaps cross-fade with scale and blur. Numbers use NumberRoll. Status text swaps blur-crossfade.
- `AnimatePresence initial={false}`. No bounce or elastic easing.
- `prefers-reduced-motion`: all durations 0, no map interpolation, no scroll narrative pinning.
- Don't animate on every WS tick. Batch KPI animations to at most 1/s.

---

## 13. Accessibility requirements
- WCAG 2.2 AA: text contrast ≥ 4.5:1, UI ≥ 3:1 (verify against design.md tokens and report any failures).
- Full keyboard path on ops and passenger. Visible `:focus-visible` ring. Skip-to-content link.
- Dialogs and sheets: focus trap, Esc, restore focus. Toasts announced via `aria-live`.
- Countdowns announce politely (each minute and the final 10 s). Status changes announced.
- Map: all map-only information also exists in tables/tabs (capacity, services, disruptions) and the legend uses words.
- Touch targets ≥ 44 px (passenger), ≥ 40 px (ops).

---

## 14. Responsiveness & devices
| Surface | Must work at |
|---|---|
| Passenger | **Laptop first:** 1280×720, 1366×768, 1440×900, 1920×1080. **Tablet:** 768×1024. **Mobile (must be equally polished):** 360×640, 390×844, 414×896, landscape usable; safe-area insets; `100dvh` |
| Ops | 1366×768 (minimum), 1920×1080 (projector target) |
| Landing | 360 → 1920 fluid |
Test in Chrome and Safari (iOS Safari for passengers: geolocation, camera QR scanning flow, `vibrate` unsupported → silent).

---

## 15. Performance budgets
- Passenger initial JS ≤ 200 KB gzipped (lazy-load map, charts, QR).
- Ops: lazy-load each tab; map chunk separate.
- LCP ≤ 2.5 s on 4G for `/` and `/demo-join`. Self-host fonts, preload the 1–2 critical weights, `font-display: swap`.

---

## 16. Testing
- **Vitest + React Testing Library:** `toLatLngs`, `useCountdown` (with server offset), state router mapping, WS event → invalidation table, error-code mapping, idempotency key reuse on retry, capacity bar clamping to 100%.
- **Component tests:** ServiceCard selection ranks, HoldTimer thresholds, persona taken state.
- **Smoke (optional Playwright):** mock mode full passenger flow (claim persona → cancelled → choose → placed → accept) and ops flow (cancel → run allocation → KPIs update).
- The final report lists the tests added and the run output.

---

## 17. Build, deploy & demo readiness
- `npm run dev` / `build` / `preview` / `test` / `lint` (ESLint + Prettier, TypeScript strict).
- Deploy on **Vercel**. Add `vercel.json` with an SPA rewrite (`{ "rewrites": [{ "source": "/(.*)", "destination": "/" }] }`) so deep links work. Set env vars in Vercel. CORS origin must be added on the backend.
- The join QR URL comes from the backend (`join_url`), so the frontend deploy URL must be given to the backend owner (`FRONTEND_BASE_URL`).
- **Demo-day checklist:** mock mode verified offline; real mode verified against the deployed backend; Join QR scannable from the back of the room in fullscreen; personas release-all tested; reset tested; projector resolution tested; browser zoom 100%; notifications muted on the presenter laptop.

---

## 18. Demo flow the frontend must support (contract §11)
| # | Ops (projector) | Judges (phones) | Frontend requirement IDs |
|---|---|---|---|
| 1 | Join QR fullscreen | Scan → persona picker → pick → `/trip` "On time" | O-4.1, P-1.x, P-4.1, O-5.1 |
| 2 | QR → corner; Cancel the local train | Red alert → `/options` | O-2.3, P-4.3 |
| 3 | Narrate | Pick 1st/2nd, send, countdown | P-5.x, P-6.1 |
| 4 | Batch closes → Run allocation; capacity fills to 100% | Placed / Moved / Waitlisted | O-2.4, O-3.1, P-6.2, P-6.4 |
| 5 | Point at the contested bus | Open "Why this?" | P-7.x |
| 6 | A judge declines | Another judge gets "A seat opened up" | P-6.8 |
| 7 | Click GST Road edge → Close | Re-route banner + ETA; map draws new route | §10.3–10.4, P-6.3 |
| 8 | Rules: raise medical → Preview → Apply | Waitlist positions animate | O-3.5, P-7.4 |
| 9 | Unresolved → Add charter bus | Waitlisted judges placed / pods | O-3.4, O-2.5, P-8.3 |
| 10 | Stress test | — | O-3.10 |
| 11 | Switch scenario 10 s and back | — | O-2.1 |

---

## 19. Build plan for the coding agent (staged order, continuous execution)

### 19.1 Rules
- First do §0.5 (move `SKILL.md` into `.agent/skills/interface-craft/`).
- Build stages **F0 → F8 in order, without stopping between stages** and without per-stage reports. A stage is done when its acceptance criteria pass; then continue straight to the next.
- At the end of each stage: app builds, lint and tests pass, mock mode works; commit `fe-stage-N: <summary>`; run SKILL.md §13 checklist + §14 review on the screens built and **fix the findings before moving on**.
- Before each stage, re-read the documents listed in §0.3 for that stage's work.
- Never silently skip a requirement. Deferred items are listed in the final report with a reason.
- Blocked (contract gap, unclear design.md token, backend not ready) → keep working with mocks and note it; stop and ask only if continuing would change data shapes or the design direction.
- Produce **one final report** (§19.3) when everything is done (or when blocked on the backend for F7).

### 19.2 Stages
| Stage | Scope | Requirement IDs | Acceptance criteria |
|---|---|---|---|
| **F0 — Foundation** | Vite + TS strict, Tailwind, shadcn init, router + guards, env validation, `tokens.css` generated from design.md, theme applied to shadcn primitives, `http.ts` (error envelope, auth, idempotency), query client, `useServerClock`, WS manager skeleton, mock layer + mock WS script, layouts (Marketing, PassengerShell, OpsShell), `strings.ts`, `ReviorLogo` | §0, §4, §5, §7 (base) | `npm run build` OK; skill confirmed available; tokens trace to design.md (fallbacks listed); mock mode boots; empty shells render at 1280 px and 360 px (passenger), 1366 px (ops) |
| **F1 — Landing & auth entry** | `/` landing, `/demo-join`, `/join` (location + form), `/login`, `/qr-login`, `/ops/login`, 404 | L-1…L-5, P-1.x, P-2.x, P-3.x, O-1.1 | Persona claim → token stored → redirect; taken persona handled; geolocation denial → Potheri; Lighthouse ≥ 90 on `/` (desktop and mobile); persona picker works at 1280 px and on a real phone; anti-slop audit clean |
| **F2 — Passenger core** | `/trip`, `/options`, `/status` (all states, HoldTimer, accept/decline/swap), state router, shared components (StatusPill, ServiceCard, CountdownRing, HoldTimer, NumberRoll) | P-4.x, P-5.x, P-6.x, §3.2 | Full mock flow: cancelled → choose → placed → accept; decline → waitlisted; cascade offer appears; countdowns use server clock; idempotency on retry tested |
| **F3 — Passenger secondary** | `/why`, `/alternatives` + pods, `/profile` (login QR, switch passenger, logout), notifications drawer | P-7.x, P-8.x, P-9.x, P-10.1 | Score bars animate on rules update; pod join/leave/confirm in mock; persona switch replaces token + reconnects WS |
| **F4 — Ops shell & controls** | `/ops` layout, top bar, KPI row, control panel (Disruptions with preview, Allocation, Add capacity), Join QR panel (3 modes), toasts | O-2.x, O-4.1, O-5.1 | Cancel → KPIs change (mock); run allocation → stats card; QR fullscreen scannable on a phone; reset confirm works |
| **F5 — Map** | `ReviorMap`, all layers, `toLatLngs` + test, vehicle interpolation, reroute animation, edge click → close flow, legend, passenger mini-map | §10, P-6.3 | Closed edge renders danger dashed; reroute draws new success line; vehicles glide at 1 Hz updates; 60 fps; reduced motion respected |
| **F6 — Ops tabs** | Capacity, Clusters, Allocations (+ passenger drawer), Unresolved, Rules (preview/apply), Fairness charts, Audit, Messages, Demo personas, Stress test | O-3.1…O-3.10 | Capacity bars never exceed 100% (test); rules preview changes nothing until Apply; stress result card renders from WS |
| **F7 — Real backend integration** | Switch from mocks to real API per backend checkpoints (Stage 1 examples → Stage 4 REST → Stage 7 WS), full event table §6.3, reconnect + polling fallback, mismatch report | §6 | Full demo script §18 runs against the deployed backend with `VITE_USE_MOCKS=false`; mock mode still works with `?mock=1` |
| **F8 — Polish, a11y, perf, deploy** | SKILL.md full review on every screen, accessibility pass, performance budgets, responsive matrix, README (setup, env, demo runbook), Vercel deploy + SPA rewrite | §12–§17 | Review verdict Approve/Needs-changes with no HIGH; contrast report; Lighthouse numbers; deployed URL works incl. `/qr-login` deep link |

**Backend dependency map:** F0–F6 use mocks only. F7 needs backend Stage 1 (examples), Stage 4 (allocation REST) and Stage 7 (WebSockets). Integrate incrementally as each lands.

### 19.3 Final report template (output once, at the end)
```markdown
# Revior Frontend — Final Report

## 1. Summary
## 2. Requirements status
| ID | Item | Files | Status (done / deferred) |
## 3. Skill setup
- SKILL.md moved to .agent/skills/interface-craft/: yes/no · auto-loaded by Antigravity: yes/no
## 4. Design decisions
- Direction sentence used:
- Tokens from design.md / fallback tokens from SKILL.md:
## 5. API / WS integration
- Endpoints & events wired (mock / real):
- **Contract mismatches / gaps:** none | <list>
## 6. interface-craft review (SKILL.md §14), remaining findings
| Severity | Location | Before | After | Why |
Verdict:
## 7. Tests (command + result)
## 8. Screens verified (passenger 1280 px + 360 px · ops 1366 px + 1920 px · reduced motion · keyboard)
## 9. Deferred / not done
## 10. Known issues / risks
## 11. How to run, deploy & demo
```

---

## 20. Definition of done (whole frontend)
- Every requirement ID in §8, §9, §10 and §11 is implemented and verified.
- The demo script (§18) runs end-to-end on the real backend and in mock mode.
- No anti-slop tells (SKILL.md §1) except deliberate design.md choices. The design matches design.md tokens exactly.
- Capacity is never shown above 100%. Every status uses colour + icon + text. Every countdown uses the server clock.
- Accessibility AA verified, responsive matrix passed, performance budgets met, deployed on Vercel with working deep links.

---

## 21. Glossary
**Hub**: station where stranded passengers gather (default Potheri). **Service**: one vehicle run. **Batch window**: period when requests are collected before one allocation run. **Hold**: temporary seat reservation awaiting Accept. **Cascade**: re-offering a released seat to the waitlist in priority order. **Swap**: requesting a different option while keeping the current seat. **Pod**: shared cab/auto of unplaced passengers. **Persona**: seeded demo passenger a judge can claim. **Open booking**: first-come claims on leftover seats after fair allocation.
