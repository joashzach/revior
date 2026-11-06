import { useCallback, useRef } from 'react'
import { uuid } from '@/lib/utils'

/**
 * One UUID per user tap, reused on retry (contract §3). `next()` mints a key for a NEW tap; `current()` returns the
 * same key until `release()` is called after a definitive outcome (success or a non-retryable error).
 */
export function useIdempotencyKey() {
  const ref = useRef<string | null>(null)
  const begin = useCallback(() => {
    if (!ref.current) ref.current = uuid()
    return ref.current
  }, [])
  const release = useCallback(() => {
    ref.current = null
  }, [])
  return { begin, release }
}
