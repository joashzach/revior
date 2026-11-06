import { z } from 'zod'

const schema = z.object({
  VITE_API_BASE: z.string().url().default('http://localhost:8000/api/v1'),
  VITE_WS_BASE: z.string().default('ws://localhost:8000'),
  VITE_USE_MOCKS: z.string().default('true'),
  VITE_DEFAULT_SCENARIO: z.string().default('potheri-demo'),
  VITE_MAP_TILE_URL: z.string().default('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'),
  VITE_MAP_ATTRIBUTION: z.string().default('&copy; OpenStreetMap contributors'),
})

const parsed = schema.safeParse(import.meta.env)

export const envError: string | null = parsed.success ? null : parsed.error.issues.map((i) => `${i.path.join('.')}: ${i.message}`).join('; ')

const raw = parsed.success ? parsed.data : schema.parse({})

export const env = {
  apiBase: raw.VITE_API_BASE.replace(/\/$/, ''),
  wsBase: raw.VITE_WS_BASE.replace(/\/$/, ''),
  useMocksDefault: raw.VITE_USE_MOCKS === 'true',
  scenario: raw.VITE_DEFAULT_SCENARIO,
  tileUrl: raw.VITE_MAP_TILE_URL,
  attribution: raw.VITE_MAP_ATTRIBUTION,
}

const MOCK_KEY = 'revior_mock'

/** Mock mode: env default, overridden at runtime by `?mock=1` (or `?mock=0`), remembered for the tab. */
export function isMock(): boolean {
  if (typeof window === 'undefined') return env.useMocksDefault
  const q = new URLSearchParams(window.location.search).get('mock')
  if (q === '1') sessionStorage.setItem(MOCK_KEY, '1')
  if (q === '0') sessionStorage.setItem(MOCK_KEY, '0')
  const s = sessionStorage.getItem(MOCK_KEY)
  return s === null ? env.useMocksDefault : s === '1'
}
