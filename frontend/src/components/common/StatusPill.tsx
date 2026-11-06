import { AlertTriangle, Ban, Check, CheckCheck, Clock, Hourglass, Info, Radio, RotateCcw, Route, X, type LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { AllocationStatus, PassengerState, ServiceStatus } from '@/api/types'

export type Tone = 'success' | 'warning' | 'danger' | 'info' | 'neutral'

/** Semantic mapping used everywhere (PRD §5.2): colour + icon + word, never colour alone. */
export const TONE_CLASS: Record<Tone, string> = {
  success: 'bg-success-bg text-success-fg border-success/30',
  warning: 'bg-warning-bg text-warning-fg border-warning/40',
  danger: 'bg-danger-bg text-danger-fg border-danger/30',
  info: 'bg-info-bg text-info-fg border-info/25',
  neutral: 'bg-transparent text-muted border-line',
}
export const TONE_SOLID: Record<Tone, string> = {
  success: 'bg-success',
  warning: 'bg-warning',
  danger: 'bg-danger',
  info: 'bg-info',
  neutral: 'bg-smoke',
}

interface Def {
  tone: Tone
  icon: LucideIcon
  label: string
}

export const PASSENGER_STATE: Record<PassengerState, Def> = {
  REGISTERED: { tone: 'info', icon: Info, label: 'Registered' },
  BOOKED: { tone: 'success', icon: Check, label: 'On time' },
  AFFECTED: { tone: 'danger', icon: AlertTriangle, label: 'Disrupted' },
  REQUESTED: { tone: 'info', icon: Clock, label: 'Request sent' },
  HELD: { tone: 'warning', icon: Hourglass, label: 'Seat held' },
  CONFIRMED: { tone: 'success', icon: CheckCheck, label: 'Confirmed' },
  WAITLISTED: { tone: 'warning', icon: Hourglass, label: 'Waitlisted' },
  UNRESOLVED: { tone: 'danger', icon: X, label: 'No seat yet' },
  RESOLVED_ALT: { tone: 'success', icon: Route, label: 'Alternative chosen' },
  REOFFER: { tone: 'warning', icon: RotateCcw, label: 'Choose again' },
}

export const SERVICE_STATUS: Record<ServiceStatus, Def> = {
  scheduled: { tone: 'info', icon: Clock, label: 'Scheduled' },
  delayed: { tone: 'warning', icon: Clock, label: 'Delayed' },
  cancelled: { tone: 'danger', icon: Ban, label: 'Cancelled' },
  running: { tone: 'info', icon: Radio, label: 'Running' },
  completed: { tone: 'neutral', icon: CheckCheck, label: 'Completed' },
  rerouted: { tone: 'success', icon: Route, label: 'Re-routed' },
}

export const ALLOCATION_STATUS: Record<AllocationStatus, Def> = {
  held: { tone: 'warning', icon: Hourglass, label: 'Held' },
  swap_held: { tone: 'warning', icon: RotateCcw, label: 'Swap offer' },
  confirmed: { tone: 'success', icon: CheckCheck, label: 'Confirmed' },
  declined: { tone: 'neutral', icon: X, label: 'Declined' },
  expired: { tone: 'danger', icon: Clock, label: 'Expired' },
  released: { tone: 'neutral', icon: X, label: 'Released' },
}

export function Pill({ tone = 'neutral', icon: Icon, children, size = 'md', className }: { tone?: Tone; icon?: LucideIcon; children: React.ReactNode; size?: 'sm' | 'md' | 'lg'; className?: string }) {
  const sz = { sm: 'h-6 px-2.5 text-[11px] gap-1', md: 'h-8 px-3.5 text-[13px] gap-1.5', lg: 'h-10 px-5 text-[15px] gap-2' }[size]
  return (
    <span className={cn('inline-flex items-center whitespace-nowrap rounded-pill border font-medium', TONE_CLASS[tone], sz, className)}>
      {Icon && <Icon className={size === 'lg' ? 'size-[18px]' : 'size-3.5'} aria-hidden />}
      {children}
    </span>
  )
}

export function StatusPill({ kind, value, label, size, className }: { kind: 'passenger' | 'service' | 'allocation'; value: string; label?: string; size?: 'sm' | 'md' | 'lg'; className?: string }) {
  const map = kind === 'passenger' ? PASSENGER_STATE : kind === 'service' ? SERVICE_STATUS : ALLOCATION_STATUS
  const d = (map as Record<string, Def>)[value] ?? { tone: 'neutral' as Tone, icon: Info, label: value }
  return (
    <Pill tone={d.tone} icon={d.icon} size={size} className={className}>
      {label ?? d.label}
    </Pill>
  )
}
