import { Accessibility, Baby, Bus, BusFront, Clock, HeartPulse, Hourglass, PersonStanding, Plane, TrainFront, Users, type LucideIcon } from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { useEffect, useRef, useState } from 'react'
import type { Needs, Option, ServiceMode, WhyFeature } from '@/api/types'
import { S } from '@/config/strings'
import { useCountdown, useProgress } from '@/hooks/useCountdown'
import { formatMmSs } from '@/lib/clock'
import { clamp, cn, fmtTime } from '@/lib/utils'
import { Pill, TONE_SOLID, type Tone } from './StatusPill'

export const MODE_ICON: Record<ServiceMode, LucideIcon> = { local_train: TrainFront, bus: Bus, charter_bus: BusFront, shuttle: BusFront }
export const MODE_LABEL: Record<ServiceMode, string> = { local_train: 'Local train', bus: 'Bus', charter_bus: 'Charter bus', shuttle: 'Shuttle' }

// ---------- capacity bar: never above 100% (PRD non-negotiable)
export function capacityParts(total: number, confirmed: number, held: number) {
  const t = Math.max(1, total)
  const c = clamp(confirmed / t, 0, 1)
  const h = clamp(held / t, 0, 1 - c)
  return { confirmed: c * 100, held: h * 100, free: Math.max(0, 100 - (c + h) * 100), full: c + h >= 1 }
}

export function CapacityBar({ total, confirmed, held, className }: { total: number; confirmed: number; held: number; className?: string }) {
  const p = capacityParts(total, confirmed, held)
  return (
    <div
      role="img"
      aria-label={`${confirmed} confirmed, ${held} held, ${Math.max(0, total - confirmed - held)} free of ${total} seats`}
      className={cn('flex h-3 w-full overflow-hidden rounded-full bg-line', className)}
    >
      <span className="h-full bg-success" style={{ width: `${p.confirmed}%` }} />
      <span className="h-full bg-warning" style={{ width: `${p.held}%` }} />
    </div>
  )
}

// ---------- countdown ring + hold timer (server clock, tabular nums, thresholds, polite announcements)
function useAnnounce(secs: number, active: boolean) {
  const [msg, setMsg] = useState('')
  const last = useRef(-1)
  useEffect(() => {
    if (!active) return
    const key = secs <= 10 ? secs : Math.floor(secs / 60) * 100
    if (key === last.current) return
    last.current = key
    if (secs <= 10 || secs % 60 === 0) setMsg(secs === 0 ? 'Time is up' : secs <= 10 ? `${secs} seconds left` : `${Math.round(secs / 60)} minutes left`)
  }, [secs, active])
  return msg
}

export function timerTone(secs: number): Tone {
  return secs <= 10 ? 'danger' : secs <= 30 ? 'warning' : 'info'
}

export function CountdownRing({ opensAt, closesAt, label, size = 132 }: { opensAt?: string | null; closesAt: string; label?: string; size?: number }) {
  const secs = useCountdown(closesAt)
  const prog = useProgress(opensAt ?? new Date(Date.parse(closesAt) - 30000).toISOString(), closesAt)
  const tone = timerTone(secs)
  const r = (size - 14) / 2
  const c = 2 * Math.PI * r
  const stroke = tone === 'danger' ? 'var(--danger)' : tone === 'warning' ? 'var(--warning)' : 'var(--accent)'
  const say = useAnnounce(secs, true)
  return (
    <div className="inline-grid place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--border)" strokeWidth="6" />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={stroke} strokeWidth="6" strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * prog} style={{ transition: 'stroke-dashoffset 250ms linear, stroke 150ms' }} />
      </svg>
      <div className="absolute grid place-items-center text-center">
        <span className="tnum font-serif text-[40px] leading-none">{formatMmSs(secs)}</span>
        {label && <span className="mt-1 text-[11px] uppercase tracking-[0.06em] text-muted">{label}</span>}
      </div>
      <span className="sr-only" aria-live="polite">{say}</span>
    </div>
  )
}

export function HoldTimer({ expiresAt, className, compact }: { expiresAt: string | null; className?: string; compact?: boolean }) {
  const secs = useCountdown(expiresAt)
  const tone = timerTone(secs)
  const say = useAnnounce(secs, !!expiresAt)
  if (!expiresAt) return null
  const color = tone === 'danger' ? 'text-danger-fg' : tone === 'warning' ? 'text-warning-fg' : 'text-ink'
  return (
    <div className={cn('inline-flex items-center gap-2', className)}>
      <Hourglass className={cn('size-5', color)} aria-hidden />
      <span className={cn('tnum font-serif leading-none transition-colors', compact ? 'text-[28px]' : 'text-[48px]', color)} data-tone={tone}>
        {formatMmSs(secs)}
      </span>
      {!compact && <span className="text-[12px] uppercase tracking-[0.06em] text-muted">{S.status.holdLeft}</span>}
      <span className="sr-only" aria-live="polite">{say}</span>
    </div>
  )
}

// ---------- need chips
export function NeedChips({ needs, party, className }: { needs: Needs; party?: number; className?: string }) {
  const items: { on: boolean; icon: LucideIcon; label: string; tone: Tone }[] = [
    { on: needs.wheelchair, icon: Accessibility, label: 'Wheelchair', tone: 'info' },
    { on: needs.elderly, icon: PersonStanding, label: 'Senior', tone: 'info' },
    { on: needs.with_children, icon: Baby, label: 'Children', tone: 'info' },
    { on: needs.medical, icon: HeartPulse, label: 'Medical', tone: 'info' },
    { on: !!needs.connection_deadline_at, icon: Plane, label: needs.connection_deadline_at ? `By ${fmtTime(needs.connection_deadline_at)}` : 'Deadline', tone: 'warning' },
    { on: (party ?? 1) > 1, icon: Users, label: `Party of ${party}`, tone: 'neutral' },
  ]
  const shown = items.filter((i) => i.on)
  if (!shown.length) return null
  return (
    <ul className={cn('flex flex-wrap gap-1.5', className)}>
      {shown.map((i) => (
        <li key={i.label}>
          <Pill tone={i.tone} icon={i.icon} size="sm">
            {i.label}
          </Pill>
        </li>
      ))}
    </ul>
  )
}

// ---------- QR panel (quiet zone >= 4 modules, high contrast)
export function QRPanel({ value, size = 160, caption, className, onDark }: { value: string; size?: number; caption?: string; className?: string; onDark?: boolean }) {
  return (
    <figure className={cn('inline-grid justify-items-center gap-2', className)}>
      <div className={cn('rounded-card-sm p-2', onDark ? 'bg-bg' : 'border border-line bg-white')}>
        <QRCodeSVG value={value} size={size} level="M" marginSize={4} bgColor="white" fgColor="black" title={caption ?? 'QR code'} />
      </div>
      {caption && <figcaption className="max-w-[28ch] text-center text-[12px] uppercase tracking-[0.05em] text-muted">{caption}</figcaption>}
    </figure>
  )
}

// ---------- score bars (priority breakdown)
export function ScoreBars({ breakdown, weights, className }: { breakdown: Record<WhyFeature, number>; weights: Record<string, number>; className?: string }) {
  const order: WhyFeature[] = ['medical', 'wheelchair', 'elderly', 'with_children', 'deadline_urgency', 'wait_time']
  return (
    <ul className={cn('grid gap-3.5', className)}>
      {order.map((k) => {
        const pts = breakdown[k] ?? 0
        const max = Math.max(1, weights[k] ?? 30)
        return (
          <li key={k} className="grid gap-1.5">
            <div className="flex items-baseline justify-between gap-3 text-[14px]">
              <span className={pts > 0 ? 'text-ink' : 'text-faint'}>{S.why.features[k]}</span>
              <span className="tnum font-medium">
                {pts > 0 ? '+' : ''}
                {Number.isInteger(pts) ? pts : pts.toFixed(1)}
                <span className="text-faint"> / {max}</span>
              </span>
            </div>
            <div className="h-2.5 overflow-hidden rounded-full bg-line" role="img" aria-label={`${S.why.features[k]}: ${pts} of ${max} points`}>
              <div className="h-full origin-left rounded-full bg-accent transition-[width] duration-500 ease-[var(--ease-out)]" style={{ width: `${clamp((pts / max) * 100, 0, 100)}%` }} />
            </div>
          </li>
        )
      })}
    </ul>
  )
}

// ---------- service card (options list)
export function SeatsBar({ left, total }: { left: number; total?: number }) {
  const t = total ?? Math.max(left, 1) + 10
  const pct = clamp((left / t) * 100, 0, 100)
  const tone: Tone = left <= 0 ? 'danger' : left <= 5 ? 'warning' : 'success'
  return (
    <div className="flex items-center gap-2.5">
      <div className="h-2 w-24 overflow-hidden rounded-full bg-line" aria-hidden>
        <div className={cn('h-full rounded-full', TONE_SOLID[tone])} style={{ width: `${pct}%` }} />
      </div>
      <span className="tnum text-[13px] text-muted">{left <= 0 ? S.common.full : `${left} ${left === 1 ? "seat" : "seats"} left`}</span>
    </div>
  )
}

export function ServiceCard({ option, rank, disabled, onSelect, onGrab, grabbing, openBooking, selectable = true }: { option: Option; rank?: 1 | 2; disabled?: boolean; onSelect?: () => void; onGrab?: () => void; grabbing?: boolean; openBooking?: boolean; selectable?: boolean }) {
  const Icon = MODE_ICON[option.mode]
  const selected = !!rank
  return (
    <div
      className={cn(
        'group relative grid gap-3 rounded-card-sm border p-5 transition-[border-color,background-color] duration-150 sm:p-6',
        selected ? 'border-accent bg-accent-subtle' : 'border-line hover:border-ink/40',
        disabled && 'opacity-55',
      )}
    >
      <div className="flex items-start gap-4">
        <div className={cn('grid size-12 shrink-0 place-items-center rounded-full border', selected ? 'border-accent bg-accent text-accent-contrast' : 'border-line')}>
          {rank ? <span className="font-serif text-[22px] leading-none" aria-hidden>{rank}</span> : <Icon className="size-5" aria-hidden />}
          {rank && <span className="sr-only">{rank === 1 ? S.options.first : S.options.second} choice</span>}
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-[22px] leading-tight sm:text-[24px]">{option.label}</h3>
          <p className="tnum mt-1 text-[14px] text-muted">
            Departs {fmtTime(option.depart_at)} <span aria-hidden>→</span> arrives {fmtTime(option.eta_at)}
          </p>
        </div>
      </div>
      {option.is_multi_leg && (
        <ol className="grid gap-1.5 border-l border-line pl-4 text-[13px] text-muted">
          {option.legs.map((l, i) => (
            <li key={i} className="tnum">
              <span className="text-ink">{l.service.mode === 'local_train' ? 'Local' : 'Bus'}</span> {l.from.name} {fmtTime(l.depart_at)} <span aria-hidden>→</span> {l.to.name} {fmtTime(l.arrive_at)}
            </li>
          ))}
        </ol>
      )}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        {option.is_full ? (
          <Pill tone="warning" icon={Hourglass} size="sm">{S.options.waitlist}</Pill>
        ) : (
          <SeatsBar left={option.seats_left} />
        )}
        {option.accessible && <Pill tone="info" icon={Accessibility} size="sm">{S.options.accessible}</Pill>}
        {option.transfers > 0 && <Pill tone="neutral" size="sm">{option.transfers} change</Pill>}
        {!option.meets_deadline && (
          <Pill tone="danger" icon={Clock} size="sm">{S.options.missesDeadline}</Pill>
        )}
      </div>
      {selectable && (
        <button
          type="button"
          onClick={onSelect}
          disabled={disabled}
          aria-pressed={selected}
          className="absolute inset-0 rounded-card-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-not-allowed"
        >
          <span className="sr-only">{selected ? `Unselect ${option.label}` : `Select ${option.label}`}</span>
        </button>
      )}
      {openBooking && !option.is_full && onGrab && (
        <div className="relative z-10 flex flex-wrap items-center gap-3 border-t border-line pt-3">
          <span className="text-[13px] text-muted">{S.options.seatsNow}</span>
          <button
            type="button"
            onClick={onGrab}
            disabled={grabbing}
            className="press inline-flex h-10 items-center rounded-button border border-ink px-5 text-[13px] uppercase tracking-[0.04em] hover:bg-ink hover:text-bg disabled:opacity-50"
          >
            {S.options.grab}
          </button>
        </div>
      )}
    </div>
  )
}
