import { env, isMock } from '@/config/env'

export type AuthKind = 'public' | 'passenger' | 'ops'

export const TOKEN_KEYS = { passenger: 'revior_passenger_token', ops: 'revior_ops_token' } as const

export const tokens = {
  get: (k: 'passenger' | 'ops') => localStorage.getItem(TOKEN_KEYS[k]),
  set: (k: 'passenger' | 'ops', t: string) => localStorage.setItem(TOKEN_KEYS[k], t),
  clear: (k: 'passenger' | 'ops') => localStorage.removeItem(TOKEN_KEYS[k]),
}

export class ApiError extends Error {
  status: number
  code: string
  details: Record<string, any>
  constructor(status: number, code: string, message: string, details: Record<string, any> = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
  /** `details.fields` from VALIDATION_ERROR: { fieldName: message } */
  get fields(): Record<string, string> {
    return (this.details?.fields as Record<string, string>) ?? {}
  }
}

export interface RequestOpts {
  body?: unknown
  query?: Record<string, string | number | boolean | undefined | null>
  idempotencyKey?: string
  signal?: AbortSignal
}

export const UNAUTHORIZED_EVENT = 'revior:unauthorized'

function qs(query?: RequestOpts['query']): string {
  if (!query) return ''
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) if (v !== undefined && v !== null && v !== '') p.set(k, String(v))
  const s = p.toString()
  return s ? `?${s}` : ''
}

export async function request<T>(kind: AuthKind, method: string, path: string, opts: RequestOpts = {}): Promise<T> {
  const token = kind === 'public' ? null : tokens.get(kind)
  if (isMock()) {
    const { mockRequest } = await import('@/mocks/server')
    return mockRequest<T>(kind, method, path + qs(opts.query), opts.body, token, opts.idempotencyKey)
  }
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json'
  if (token) headers.Authorization = `Bearer ${token}`
  if (opts.idempotencyKey) headers['Idempotency-Key'] = opts.idempotencyKey
  let res: Response
  try {
    res = await fetch(`${env.apiBase}${path}${qs(opts.query)}`, {
      method,
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: opts.signal,
    })
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw e
    throw new ApiError(0, 'NETWORK', "Can't reach Revior, retrying")
  }
  if (res.status === 204) return undefined as T
  let json: any = null
  try {
    json = await res.json()
  } catch {
    /* non-JSON body */
  }
  if (!res.ok) {
    const err = json?.error
    const code = err?.code ?? (res.status >= 500 ? 'SERVER_ERROR' : 'ERROR')
    if (res.status === 401 && kind !== 'public' && code === 'UNAUTHORIZED') {
      tokens.clear(kind)
      window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT, { detail: { kind } }))
    }
    throw new ApiError(res.status, code, err?.message ?? `Request failed (${res.status})`, err?.details ?? {})
  }
  return json as T
}

export const get = <T>(kind: AuthKind, path: string, query?: RequestOpts['query']) => request<T>(kind, 'GET', path, { query })
export const post = <T>(kind: AuthKind, path: string, body?: unknown, idempotencyKey?: string) =>
  request<T>(kind, 'POST', path, { body: body ?? {}, idempotencyKey })
export const patch = <T>(kind: AuthKind, path: string, body: unknown) => request<T>(kind, 'PATCH', path, { body })
