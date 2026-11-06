import { describe, expect, it, vi } from 'vitest'
import { toLatLngs } from '@/lib/geo'
import { routeForState, shouldAutoNavigate } from '@/app/stateRouter'
import { capacityParts } from '@/components/common/domain'
import { formatMmSs, secondsUntil, syncServerTime, serverNow, useClockStore } from '@/lib/clock'

describe('toLatLngs', () => {
  it('swaps GeoJSON [lng,lat] to Leaflet [lat,lng]', () => {
    expect(toLatLngs({ coordinates: [[80.0, 12.8], [80.1, 12.9]] })).toEqual([[12.8, 80.0], [12.9, 80.1]])
  })
  it('tolerates null and short vertices', () => {
    expect(toLatLngs(null)).toEqual([])
    expect(toLatLngs({ coordinates: [[1], [2, 3]] })).toEqual([[3, 2]])
  })
})

describe('state router', () => {
  it('maps every state to a screen', () => {
    expect(routeForState('BOOKED')).toBe('/trip')
    expect(routeForState('AFFECTED')).toBe('/options')
    expect(routeForState('HELD')).toBe('/status')
    expect(routeForState('UNRESOLVED')).toBe('/alternatives')
  })
  it('never yanks the user off sticky screens', () => {
    expect(shouldAutoNavigate('/why', 'REQUESTED', 'HELD')).toBe('banner')
    expect(shouldAutoNavigate('/profile', 'BOOKED', 'AFFECTED')).toBe('banner')
    expect(shouldAutoNavigate('/trip', 'BOOKED', 'AFFECTED')).toBe('go')
    expect(shouldAutoNavigate('/status', 'REQUESTED', 'HELD')).toBe('stay')
  })
})

describe('capacity bar', () => {
  it('never exceeds 100%', () => {
    const p = capacityParts(50, 60, 20)
    expect(p.confirmed + p.held).toBeLessThanOrEqual(100)
    expect(p.free).toBe(0)
    expect(capacityParts(0, 5, 5).confirmed).toBeLessThanOrEqual(100)
  })
})

describe('server clock', () => {
  it('applies the server offset to countdowns', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T10:00:00Z'))
    syncServerTime('2026-01-01T10:00:30Z') // server 30 s ahead of this device
    expect(Math.abs(useClockStore.getState().offset - 30_000)).toBeLessThan(50)
    expect(secondsUntil('2026-01-01T10:01:00Z')).toBe(30)
    expect(serverNow() - Date.now()).toBeGreaterThan(29_000)
    vi.useRealTimers()
  })
  it('formats mm:ss', () => {
    expect(formatMmSs(125)).toBe('2:05')
    expect(formatMmSs(-4)).toBe('0:00')
  })
})

import { describeError } from '@/api/errors'
import { ApiError } from '@/api/http'
import { invalidationFor } from '@/realtime/events'
import { qk } from '@/api/queryKeys'

describe('error mapping (contract §3)', () => {
  it('retries while allocation runs and treats idempotency conflicts as success', () => {
    expect(describeError(new ApiError(409, 'ALLOCATION_IN_PROGRESS', 'x')).retryMs).toBe(2000)
    expect(describeError(new ApiError(409, 'IDEMPOTENCY_CONFLICT', 'x')).asSuccess).toBe(true)
    expect(describeError(new ApiError(409, 'SEAT_UNAVAILABLE', 'x')).refetch).toBe('options')
  })
})

describe('realtime invalidation', () => {
  it('refreshes status and why on an allocation result for passengers', () => {
    const keys = invalidationFor('allocation.result', 'passenger')
    expect(keys).toContainEqual(qk.status)
    expect(keys).toContainEqual(qk.why)
  })
})
