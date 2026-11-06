import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useState } from 'react'
import { describeError, toastError } from '@/api/errors'
import { qk } from '@/api/queryKeys'
import type { MyStatus } from '@/api/types'
import { useIdempotencyKey } from './useIdempotencyKey'

/**
 * Runs an idempotent passenger action: ONE UUID per user tap, reused when the same tap is retried (network error /
 * ALLOCATION_IN_PROGRESS); released after a definitive outcome. Maps ApiError codes per contract §3.
 */
export function useIdempotentAction<A extends unknown[]>(fn: (key: string, ...args: A) => Promise<MyStatus | unknown>, opts?: { onDone?: (r: any) => void; onError?: (e: unknown) => boolean }) {
  const qc = useQueryClient()
  const key = useIdempotencyKey()
  const [pending, setPending] = useState(false)
  const run = useCallback(
    async (...args: A) => {
      if (pending) return
      setPending(true)
      const k = key.begin()
      try {
        const res = await fn(k, ...args)
        key.release()
        if (res && typeof res === 'object' && 'state' in (res as any)) qc.setQueryData(qk.status, res)
        qc.invalidateQueries({ queryKey: qk.status })
        qc.invalidateQueries({ queryKey: qk.options })
        qc.invalidateQueries({ queryKey: qk.me })
        opts?.onDone?.(res)
        return res
      } catch (e) {
        if (opts?.onError?.(e)) { key.release(); return }
        const ui = describeError(e)
        if (ui.asSuccess) { key.release(); qc.invalidateQueries({ queryKey: qk.status }); opts?.onDone?.(undefined); return }
        if (ui.retryMs) { setTimeout(() => { setPending(false); run(...args) }, ui.retryMs); toastError(e); return }
        // network errors keep the key so a retry of the SAME tap is idempotent; definitive errors release it
        if (!(e as any)?.status) toastError(e, { retry: () => run(...args) })
        else { key.release(); toastError(e) }
        if (ui.refetch === 'status') qc.invalidateQueries({ queryKey: qk.status })
        if (ui.refetch === 'options') qc.invalidateQueries({ queryKey: qk.options })
        if (ui.refetch === 'pods') qc.invalidateQueries({ queryKey: qk.pods })
      } finally {
        setPending(false)
      }
    },
    [fn, key, pending, qc, opts],
  )
  return { run, pending }
}
