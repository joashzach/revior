import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useCountdown } from '@/hooks/useCountdown'
import { useIdempotencyKey } from '@/hooks/useIdempotencyKey'
import { syncServerTime } from '@/lib/clock'
import { timerTone } from '@/components/common/domain'

afterEach(() => vi.useRealTimers())

describe('idempotency key', () => {
  it('reuses one key for a retried tap and mints a new one after release', () => {
    const { result } = renderHook(() => useIdempotencyKey())
    const a = result.current.begin()
    expect(result.current.begin()).toBe(a)
    act(() => result.current.release())
    expect(result.current.begin()).not.toBe(a)
  })
})

describe('useCountdown', () => {
  it('counts down by the server clock, not the device clock', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T10:00:00Z'))
    syncServerTime('2026-01-01T10:00:20Z') // server is 20 s ahead
    const { result } = renderHook(() => useCountdown('2026-01-01T10:01:00Z'))
    expect(result.current).toBe(40)
    act(() => { vi.advanceTimersByTime(5000) })
    expect(result.current).toBe(35)
  })
})

describe('hold timer thresholds', () => {
  it('warns at 30 s and turns urgent at 10 s', () => {
    expect(timerTone(120)).toBe('info')
    expect(timerTone(30)).toBe('warning')
    expect(timerTone(10)).toBe('danger')
  })
})
