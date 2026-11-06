# Revior frontend

Landing page, passenger app and operator dashboard for Revior, a disruption-recovery platform. Default hub: Potheri, Chennai.

React 18 · Vite · TypeScript (strict) · Tailwind 4 with tokens from `DESIGN.md` · Radix/shadcn-style primitives · TanStack Query · react-router · react-leaflet · Recharts · Motion · vaul · sonner · react-hook-form + zod.

## Run it

```bash
cd frontend
npm install
cp .env.example .env     # then edit, see below
npm run dev              # http://localhost:5173
```

| Script | What it does |
|---|---|
| `npm run dev` | Vite dev server on port 5173 |
| `npm run build` | type-check, then production build to `dist/` |
| `npm run lint` | ESLint |
| `npm test` | Vitest unit tests |

## Environment

| Variable | Meaning |
|---|---|
| `VITE_API_BASE` | REST base, e.g. `http://localhost:8000/api/v1` (`8001` if `API_HOST_PORT=8001` in `backend/.env`) |
| `VITE_WS_BASE` | WebSocket base, e.g. `ws://localhost:8000` |
| `VITE_USE_MOCKS` | `true` runs entirely offline against an in-memory mock backend; `false` talks to the real API |
| `VITE_MAP_TILE_URL`, `VITE_MAP_ATTRIBUTION` | Map tiles; keep the attribution visible |

Add `?mock=1` to any URL to force the mock layer for that browser session, whatever `VITE_USE_MOCKS` says.

## Routes

Public: `/` landing · `/demo-join` persona picker · `/join` register · `/login` · `/qr-login?t=…`
Passenger (needs login): `/trip` · `/options` · `/status` · `/why` · `/alternatives` · `/profile`
Operator: `/ops/login` · `/ops`

Tokens live in `localStorage` as `revior_passenger_token` and `revior_ops_token`. A 401 clears the matching token and returns to the matching login.

## Demo runbook

1. Start the backend (`docker compose up -d --build` in `backend/`) and wait for `/api/v1/health`.
2. Reset: `POST /api/v1/ops/scenarios/potheri-demo/reset`, or the **Reset** button on `/ops`.
3. Open `/ops`, sign in with the operator password from `backend/.env` (`OPS_PASSWORD`). Set Join QR to **Full** and show it to the room.
4. Judges scan the QR, pick a persona on `/demo-join` and land on `/trip`.
5. On `/ops` → Disruptions → Cancel → pick the 6:10 PM local → **Preview** → **Confirm**. Passenger phones switch to the options screen on their own.
6. Judges choose a first and second option and send. The batch closes and allocation runs; held seats count down on each phone.
7. Open **Why this?** on a phone, then the **Rules** tab: change a weight, **Preview**, **Apply**.
8. Close a road on the map (click it → "Close this road") to show re-routing, then run the **Stress test** tab.

The Windows Docker WebSocket proxy can drop sockets. The app reconnects with backoff, refetches on reconnect and falls back to polling after 5 s offline.

## Structure

```
src/
  api/        typed client, endpoints, error mapping (contract §3)
  app/        router, providers, guards, session, state router
  components/ ui (primitives), common (domain widgets), layout, map, brand
  config/     env validation, all UI copy
  hooks/      queries, idempotent actions, countdown
  lib/        server clock, geo (the only [lng,lat] → [lat,lng] conversion), utils
  mocks/      offline backend: world, state machine, router, socket emitter
  pages/      landing, auth, passenger screens, ops dashboard + tabs
  realtime/   socket manager, event → cache invalidation, live stores
  styles/     tokens.css (from DESIGN.md), globals.css
```

## Deploy (Vercel)

`vercel.json` rewrites every path to `index.html`. From `frontend/`:

```bash
npx vercel link
npx vercel env add VITE_API_BASE production      # https://<backend>/api/v1
npx vercel env add VITE_WS_BASE production       # wss://<backend>
npx vercel env add VITE_USE_MOCKS production     # false
npx vercel --prod
```

The backend must allow the Vercel origin in its CORS setting.
