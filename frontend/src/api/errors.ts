import { toast } from 'sonner'
import { S } from '@/config/strings'
import { ApiError } from './http'

export interface ErrorUi {
  message: string
  /** which caches to refetch */
  refetch?: 'status' | 'options' | 'pods' | 'personas'
  /** retry after N ms (ALLOCATION_IN_PROGRESS) */
  retryMs?: number
  /** treat as success (IDEMPOTENCY_CONFLICT) */
  asSuccess?: boolean
  inline?: boolean
}

/** Contract §3 error table → UI handling. Pure so it can be unit-tested. */
export function describeError(e: unknown): ErrorUi {
  if (!(e instanceof ApiError)) return { message: S.errors.server }
  switch (e.code) {
    case 'NETWORK': return { message: S.errors.network }
    case 'VALIDATION_ERROR': return { message: e.message, inline: true }
    case 'UNAUTHORIZED': return { message: S.errors.sessionEnded }
    case 'FORBIDDEN': return { message: S.errors.notAllowed }
    case 'NOT_FOUND': return { message: S.errors.notFound }
    case 'INVALID_STATE': return { message: e.message || S.errors.invalidState, refetch: 'status' }
    case 'SEAT_UNAVAILABLE': return { message: S.errors.seatUnavailable, refetch: 'options' }
    case 'ALLOCATION_IN_PROGRESS': return { message: S.errors.allocationRunning, retryMs: 2000 }
    case 'BATCH_CLOSED': return { message: S.errors.batchClosed, refetch: 'options' }
    case 'HOLD_EXPIRED': return { message: S.errors.holdExpired, refetch: 'status' }
    case 'POD_FULL': return { message: S.errors.podFull, refetch: 'pods' }
    case 'PERSONA_TAKEN': return { message: S.errors.personaTaken, refetch: 'personas' }
    case 'EMAIL_TAKEN': return { message: S.errors.emailTaken, inline: true }
    case 'INVALID_CREDENTIALS': return { message: S.errors.invalidCredentials, inline: true }
    case 'QR_TOKEN_INVALID': return { message: S.errors.qrInvalid, inline: true }
    case 'RATE_LIMITED': return { message: S.errors.rateLimited }
    case 'IDEMPOTENCY_CONFLICT': return { message: '', asSuccess: true, refetch: 'status' }
    default: return { message: e.status >= 500 ? S.errors.server : e.message }
  }
}

export function toastError(e: unknown, opts?: { retry?: () => void }) {
  const ui = describeError(e)
  if (ui.asSuccess || !ui.message) return ui
  toast.error(ui.message, opts?.retry ? { action: { label: S.common.retry, onClick: opts.retry } } : undefined)
  return ui
}
