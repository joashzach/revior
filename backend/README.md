# Revior — Backend

> **Passengers choose. Revior decides fairly. Every decision is explainable.**
> Hackathon problem statement PS2 — *The Stranded Network*. When a local train is cancelled, hundreds of people are stranded at once; Revior recovers them **together**: batch allocation, transparent priority, groups kept together, accessible seats first, time-limited holds, cascade to the waitlist, pods, re-routing — and **never an over-allocated seat**.

FastAPI · PostgreSQL 16 · SQLAlchemy 2 (async) · Alembic · networkx · WebSockets.
Spec: [`../stranded-network-backend-PRD.md`](../stranded-network-backend-PRD.md) · frontend contract: [`../stranded-network-frontend-API-contract.md`](../stranded-network-frontend-API-contract.md) · OpenAPI: [`contracts/openapi.json`](contracts/openapi.json) · mock payloads: [`contracts/examples/`](contracts/examples/).

## Quick start

### Docker (recommended / demo fallback)
```bash
cp .env.example .env            # set JWT_SECRET (>= 32 chars), OPS_PASSWORD; API_HOST_PORT=8001 if 8000 is busy
docker compose up -d --build    # db on :5433, api on :${API_HOST_PORT:-8000}
curl localhost:8000/api/v1/health
```
On first boot the API runs the Alembic migrations and seeds both scenarios (`potheri-demo`, `secondary-demo`).
Swagger UI: `http://localhost:8000/docs`.

### Local
```bash
docker compose up -d db
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"      # Linux/macOS: .venv/bin/pip
.venv/Scripts/alembic upgrade head
.venv/Scripts/uvicorn app.main:app --workers 1                    # ALWAYS exactly one worker
```
> One worker is a hard requirement: the WebSocket hub, background loops and in-process pub/sub live in the process. Concurrency safety comes from PostgreSQL row locks + advisory locks, not process memory.

## Configuration (env)
| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | local compose DB | `postgresql+asyncpg://…` **direct / session-mode** connection (advisory + row locks need session semantics) |
| `JWT_SECRET`, `JWT_TTL_HOURS` | `change-me`, 24 | HS256 signing key (use ≥ 32 chars), token lifetime |
| `OPS_PASSWORD` | `change-me` | operator password for `POST /auth/ops-login` |
| `CORS_ORIGINS` | `http://localhost:5173` | comma-separated frontend origins |
| `FRONTEND_BASE_URL` | `http://localhost:5173` | used to build `join_url` and the personal login-QR URL (`/qr-login?t=…`) |
| `DEMO_PERSONA_PASSWORD` | `revior-demo` | shared password of the demo personas (backup logins) |
| `DEFAULT_SCENARIO` | `potheri-demo` | scenario activated on first boot |
| `DEMO_MODE` | `true` | enables `POST /ops/stress/run` |
| `BATCH_WINDOW_SECONDS`, `HOLD_SECONDS` | 150, 600 | seed the scenario config on reset (demo: 30 / 120). Editable live: `PATCH /ops/scenarios/{slug}/config` |
| `DELAY_THRESHOLD_MINUTES`, `HUB_RADIUS_KM`, `SIM_SPEED` | 20, 10, 10 | likewise |
| `AUTO_BOOTSTRAP` | `true` | seed empty scenarios on startup |
| `RUN_BACKGROUND_LOOPS` | `true` | batch_closer, hold_expirer, simulator, KPI broadcaster, cleanup |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` / `DB_POOL_TIMEOUT` | 10 / 10 / 120 | connection pool |
| `ENABLE_ORTOOLS` | `false` | optional stretch (F8.9) — not implemented, greedy is the production mode |
| `TWILIO_*` | off | optional real SMS for *registered judges only* (never seeded passengers or personas) |
| `LOG_LEVEL`, `SQL_SLOW_MS` | `INFO`, 0 | structlog JSON logs; >0 logs slow SQL |

## Demo runbook (PRD §19)
1. `docker compose up -d --build`; open the ops dashboard on the projector; Join QR → `${FRONTEND_BASE_URL}/demo-join?scenario=potheri-demo` (it is `join_url` in `GET /scenarios/active`).
2. **Reset** between panels: `POST /ops/scenarios/potheri-demo/reset` (≈ 1–3 s, deterministic, frees all personas).
3. Judges pick a persona (or *Surprise me*). Backup logins (email + `DEMO_PERSONA_PASSWORD`): [`seed/potheri/judge_logins.md`](seed/potheri/judge_logins.md).
4. Operator: cancel the 6:10 PM local → judges choose 1st/2nd → batch closes (auto-runs allocation) → *Why this?* → a judge declines (cascade) → close GST Road at Vandalur (re-route) → raise a weight → preview → apply → add a charter bus → stress test → switch scenario for 10 s.
5. **Whole flow scripted over the API + WebSockets**: 
   ```bash
   python scripts/demo_flow.py --base-url http://localhost:8000 --ops-password "$OPS_PASSWORD"
   ```
Tip for demos: `PATCH /ops/scenarios/potheri-demo/config {"batch_window_seconds":30,"hold_seconds":120}`.

## Scripts
| Script | Purpose |
|---|---|
| `scripts/demo_flow.py` | the 11-step demo end-to-end (REST + WS), asserts every step |
| `scripts/stress_test.py` | 1000 concurrent requests / 10 seats → `0 over-allocations, 0 5xx` (`--base-url` for real HTTP) |
| `scripts/fetch_polylines.py` | fetch OSRM road polylines **once** (offline) → `seed/<scenario>/road_polylines.json`; straight-line fallback if OSRM is unreachable |
| `scripts/export_openapi.py` | write `contracts/openapi.json` |
| `scripts/build_examples.py` | regenerate `contracts/examples/*.json` (exact contract shapes) |
| `scripts/build_seed_data.py` | regenerate `nodes.json` / `edges.json` from coordinates |

## Tests
```bash
.venv/Scripts/python -m pytest -q          # uses the `stranded_test` database (created automatically by docker compose users: see below)
```
Create the test DB once: `docker compose exec db psql -U stranded -d postgres -c "create database stranded_test"`. Override with `TEST_DATABASE_URL`.

## Architecture in one screen
* **Scenario-scoped everything** — Potheri, local hubs, services are *seed data* (`seed/<scenario>/`), nothing location-specific lives in code. `MockAdapter` implements `TransportDataAdapter`; `GtfsRtAdapter` is a documented stub.
* **Allocation engine** (`app/domain/allocation.py`) — greedy two-pass (wheelchair first for accessible seats), deterministic ordering `(-score, affected_at, registered_at, id)`, all free seats row-locked up front (`FOR UPDATE SKIP LOCKED`), bulk write-back, advisory lock per scenario, every decision explained + audited.
* **No over-allocation** — seat rows are the lock unit; partial unique indexes (`one_primary_active`, `one_swap_active`, `one_open_batch`, `one_active_rule`); allocation runs hold the *exclusive* advisory lock while claims/cascades hold the *shared* one; `Idempotency-Key` on accept/decline/claim/swap/pod-join; events are published only **after commit**.
* **Real time** — `/ws/passenger?token=` and `/ws/ops?token=`; every event in the contract is emitted; KPI snapshots debounced to 1 s.
* **Auth** — passenger email+password (bcrypt), personal login QR (24 h, hashed, revocable), operator password, `token_version` (logout / persona release / switch invalidate old JWTs).

## Deploying (Render / Railway)
`render.yaml` is included (Docker web service + managed Postgres). Steps:
1. Create a PostgreSQL 16 database and copy its **direct** connection string as `postgresql+asyncpg://…` (not a transaction-mode pooler).
2. New web service from this repo (root `backend/`, Dockerfile). Set env: `DATABASE_URL`, `JWT_SECRET` (≥ 32 chars), `OPS_PASSWORD`, `CORS_ORIGINS=https://<frontend>.vercel.app,http://localhost:5173`, `FRONTEND_BASE_URL=https://<frontend>.vercel.app`, `DEMO_PERSONA_PASSWORD`, `DEMO_MODE=true`, `BATCH_WINDOW_SECONDS=30`, `HOLD_SECONDS=120`. Keep **1 instance / 1 worker**.
3. Health check path: `/api/v1/health`. After deploy: `curl https://<backend>/api/v1/health` → `{"status":"ok","db":"ok",…}` and run `python scripts/demo_flow.py --base-url https://<backend> --ops-password …`.
4. Give the frontend `VITE_API_BASE=https://<backend>/api/v1` and `VITE_WS_BASE=wss://<backend>`.
Local fallback with a phone hotspot: `docker compose up` on the presenter laptop and point the frontend at `http://<laptop-ip>:8000`.
