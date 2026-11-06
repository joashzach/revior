const e = import.meta.env as Record<string, string | undefined>
const str = (v: string | undefined, d: string) => (v && v.trim() ? v.trim() : d)

function validUrl(v: string) {
  try { new URL(v); return true } catch { return false }
}
const apiBase = str(e.VITE_API_BASE, 'http://localhost:8000/api/v1')

/** A malformed VITE_API_BASE would make every request fail silently; surface it. */
export const envError: string | null = validUrl(apiBase) ? null : 'VITE_API_BASE: not a valid URL'

export const env = {
  apiBase: apiBase.replace(/\/$/, ''),
  wsBase: str(e.VITE_WS_BASE, 'ws://localhost:8000').replace(/\/$/, ''),
  useMocksDefault: str(e.VITE_USE_MOCKS, 'true') === 'true',
  scenario: str(e.VITE_DEFAULT_SCENARIO, 'potheri-demo'),
  tileUrl: str(e.VITE_MAP_TILE_URL, 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'),
  attribution: str(e.VITE_MAP_ATTRIBUTION, '&copy; OpenStreetMap contributors'),
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
