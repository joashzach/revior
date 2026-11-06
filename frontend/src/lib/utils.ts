import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs))

const TZ = 'Asia/Kolkata'
const timeFmt = new Intl.DateTimeFormat('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: TZ })
const dateTimeFmt = new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: TZ })

/** HH:mm in Asia/Kolkata (contract §3). */
export const fmtTime = (iso: string | null | undefined) => (iso ? timeFmt.format(new Date(iso)) : '—')
export const fmtDateTime = (iso: string | null | undefined) => (iso ? dateTimeFmt.format(new Date(iso)) : '—')

export const fmtPct = (x: number) => `${Math.round(x * 100)}%`
export const clamp = (n: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, n))
export const pluralize = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`

export function minutesBetween(aIso: string, bIso: string) {
  return Math.round((Date.parse(bIso) - Date.parse(aIso)) / 60000)
}

export function uuid(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
  })
}

/** Ordinal for choice ranks: 1 -> "1st". */
export const ordinal = (n: number) => (n === 1 ? '1st' : n === 2 ? '2nd' : `${n}th`)

export const fmtInr = (n: number) => `₹${Math.round(n).toLocaleString("en-IN")}`

/** The server `headline` is one sentence plus detail ("Placed on your 1st choice ✓ - MTC 570A…"). Screens show the lead; the detail lives in the card. */
export const leadOf = (headline: string) => headline.split(/\s[—–-]\s/)[0].replace(/\.$/, '')
