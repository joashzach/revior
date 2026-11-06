import { env, isMock } from '@/config/env'
import { syncServerTime } from '@/lib/clock'
import { bus, useConnStore } from './bus'
import type { WsMessage } from '@/api/types'

const BACKOFF = [1000, 2000, 5000, 10000]
const PING_MS = 20_000

/**
 * One socket per app (PRD §6.2): ping every 20 s, backoff 1s→2s→5s→10s, `onReconnect` fires after every re-open so
 * the caller refetches (events are not replayed). In mock mode the mock emitter feeds the bus instead.
 */
export class SocketManager {
  private ws: WebSocket | null = null
  private attempt = 0
  private timer: ReturnType<typeof setTimeout> | null = null
  private pinger: ReturnType<typeof setInterval> | null = null
  private closed = true
  private everConnected = false
  private mockStop: (() => void) | null = null

  constructor(
    private kind: 'passenger' | 'ops',
    private token: string,
    private onReconnect: () => void,
  ) {}

  start() {
    this.closed = false
    if (isMock()) {
      useConnStore.getState().set('connected')
      import('@/mocks/ws').then((m) => {
        if (!this.closed) this.mockStop = m.startMockEmitter(this.kind)
      })
      return
    }
    this.connect()
  }

  stop() {
    this.closed = true
    this.mockStop?.()
    this.mockStop = null
    if (this.timer) clearTimeout(this.timer)
    if (this.pinger) clearInterval(this.pinger)
    this.ws?.close()
    this.ws = null
    useConnStore.getState().set('offline')
  }

  private connect() {
    if (this.closed) return
    useConnStore.getState().set(this.everConnected ? 'reconnecting' : 'connecting')
    const ws = new WebSocket(`${env.wsBase}/ws/${this.kind}?token=${encodeURIComponent(this.token)}`)
    this.ws = ws
    ws.onopen = () => {
      const wasDown = this.everConnected
      this.everConnected = true
      this.attempt = 0
      useConnStore.getState().set('connected')
      if (this.pinger) clearInterval(this.pinger)
      this.pinger = setInterval(() => ws.readyState === 1 && ws.send(JSON.stringify({ type: 'ping' })), PING_MS)
      if (wasDown) this.onReconnect()
    }
    ws.onmessage = (e) => {
      let m: WsMessage
      try {
        m = JSON.parse(e.data)
      } catch {
        return
      }
      if (m.ts) syncServerTime(m.ts)
      if (m.type === 'pong' || m.type === 'ping') return
      bus.emit(m)
    }
    ws.onclose = (e) => {
      if (this.pinger) clearInterval(this.pinger)
      if (this.closed) return
      if (e.code === 4401) {
        // token invalid (logout / persona released): the HTTP layer will 401 and send the user to login
        useConnStore.getState().set('offline')
        window.dispatchEvent(new CustomEvent('revior:socket-unauthorized', { detail: { kind: this.kind } }))
        return
      }
      useConnStore.getState().set('reconnecting')
      const delay = BACKOFF[Math.min(this.attempt++, BACKOFF.length - 1)]
      this.timer = setTimeout(() => this.connect(), delay)
    }
    ws.onerror = () => ws.close()
  }
}
