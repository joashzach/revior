// Mock WebSocket emitter: forwards the mock server's events to the realtime bus, plus a 1 Hz vehicle ticker.
import { tokens } from '@/api/http'
import { bus } from '@/realtime/bus'
import { syncServerTime } from '@/lib/clock'
import { mock as M } from './state'
import { mockRequest, mockVehicles } from './server'

export function startMockEmitter(kind: 'passenger' | 'ops'): () => void {
  const pid = () => [...M.pax.values()].find((p) => p.token === tokens.get('passenger'))?.id
  const send = (type: string, data: unknown) => {
    const ts = M.iso()
    syncServerTime(ts)
    bus.emit({ type, ts, scenario: M.scenarioSlug, data })
  }
  const off = M.on((e) => {
    if (kind === 'ops') {
      if (e.aud === 'ops' || e.aud === 'all') send(e.type, e.data)
      return
    }
    if (e.aud === 'ops') return
    if (e.pax && !e.pax.includes(pid() ?? -1)) return
    send(e.type, e.data)
  })
  const tick = setInterval(() => {
    const v = mockVehicles()
    if (!v.length) return
    if (kind === 'ops') return send('vehicle.positions', { items: v })
    const me = [...M.pax.values()].find((p) => p.id === pid())
    const own = v.filter((x) => x.service_id === me?.alloc?.serviceId || x.service_id === 1)
    if (own.length) send('vehicle.positions', { items: own })
  }, 1000)
  return () => {
    off()
    clearInterval(tick)
  }
}

/** Hidden dev-menu script (PRD §4.4): judge joins → disruption → batch → result → cascade → re-route → rules. */
export function playMockDemoScript(log: (s: string) => void = () => {}) {
  const ops = (m: string, p: string, b?: unknown) => mockRequest<any>('ops', m, p, b ?? {}, 'mock-ops')
  const at = (s: number, label: string, fn: () => unknown) => setTimeout(async () => { log(label); try { await fn() } catch (e) { log(String(e)) } }, s * 1000)
  at(5, 'judge joined', async () => {
    const free = (await mockRequest<any>('public', 'GET', '/demo/personas', {}, null)).items.find((p: any) => !p.is_taken)
    if (free) await mockRequest('public', 'POST', '/auth/demo-claim', { persona_id: free.id }, null)
  })
  at(10, 'disruption.created', () => ops('POST', '/ops/disruptions', { type: 'cancellation', service_id: 1, reason: 'Waterlogging near Guduvanchery' }))
  at(60, 'offer cascade', () => { const p = [...M.pax.values()].find((x) => x.state === 'HELD'); if (p) M.later(0, () => mockRequest('passenger', 'POST', '/me/allocation/decline', {}, p.token, 'script')) })
  at(75, 'service.rerouted', async () => {
    const e = (await ops('GET', '/ops/network')).edges.find((x: any) => x.mode === 'road' && x.road_name === 'GST Road' && x.from_node_id === 4)
    if (e) await ops('POST', '/ops/disruptions', { type: 'closure', edge_id: e.id, reason: 'Road closed near Vandalur' })
  })
  at(90, 'rules.updated', () => ops('POST', '/ops/rules/apply', { weights: { medical: 40 } }))
}
