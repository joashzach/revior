import { AlertTriangle, ArrowRight, CalendarClock, Clock, MapPin } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ErrorState, SkeletonBlocks } from '@/components/common/primitives'
import { MODE_ICON, MODE_LABEL, NeedChips } from '@/components/common/domain'
import { buttonVariants } from '@/components/ui/button'
import { S } from '@/config/strings'
import { useMe, useTrip } from '@/hooks/queries'
import { cn, fmtTime, leadOf } from '@/lib/utils'

export default function Trip() {
  const trip = useTrip()
  const me = useMe()
  if (trip.isLoading || me.isLoading) return <SkeletonBlocks rows={2} rowClass="h-56" />
  if (trip.isError || !trip.data) return <ErrorState title="We couldn't load your trip" onRetry={() => trip.refetch()} />
  const t = trip.data
  const s = t.ticket.service
  const p = me.data
  const Icon = MODE_ICON[s.mode]
  const cancelled = s.status === 'cancelled'
  const delayed = s.delay_minutes > 0
  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_340px]">
      <div className="grid content-start gap-6">
        <div className="grid gap-2">
          <h1 className="rise text-[clamp(2.2rem,1.4rem+3vw,3.5rem)] leading-[1.05]">{leadOf(t.headline)}</h1>
        </div>

        {cancelled && (
          <div role="alert" className="rise grid gap-4 rounded-card-sm border border-danger/40 bg-danger-bg p-6 text-danger-fg sm:p-8">
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-1 size-6 shrink-0" aria-hidden />
              <div className="grid gap-1">
                <h2 className="text-[28px]">Your train is cancelled</h2>
                <p className="text-[15px]">{t.disruption?.reason ? `${t.disruption.reason}.` : 'There is a service disruption.'} Revior is placing everyone together.</p>
              </div>
            </div>
            <div><Link to="/options" className={buttonVariants({ variant: 'primary', size: 'lg' })}>{S.trip.chooseCta} <ArrowRight /></Link></div>
          </div>
        )}
        {!cancelled && delayed && (
          <div role="status" className="rise flex items-center gap-3 rounded-card-sm border border-warning/40 bg-warning-bg p-5 text-warning-fg">
            <Clock className="size-5 shrink-0" aria-hidden />
            <p className="text-[15px]">{s.delay_minutes >= 20 ? `Your train is ${s.delay_minutes} min late. You can wait, or choose another way.` : `Running ${s.delay_minutes} min late. No action needed.`}</p>
            {s.delay_minutes >= 20 && <Link to="/options" className={cn(buttonVariants({ variant: 'dark', size: 'xs' }), 'ml-auto')}>See options</Link>}
          </div>
        )}

        <article aria-label="Ticket" className="rise rise-2 grid gap-6 rounded-card-sm border border-line p-6 sm:p-8">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="flex items-center gap-2 text-[13px] uppercase tracking-[0.05em] text-muted"><Icon className="size-4" aria-hidden /> {MODE_LABEL[s.mode]}</span>
          </div>
          <div className="grid gap-1">
            <h2 className="text-[clamp(1.6rem,1.2rem+1.4vw,2.2rem)] leading-tight">{s.label}</h2>
            <p className="flex flex-wrap items-center gap-x-2 text-[15px] text-muted"><MapPin className="size-4" aria-hidden /> {p?.hub.name ?? s.origin.name} <ArrowRight className="size-4" aria-hidden /> {p?.destination.name ?? s.destination.name}</p>
          </div>
          <dl className="grid gap-6 border-t border-line pt-6 sm:grid-cols-3">
            <div><dt className="eyebrow">Ticket ID</dt><dd className="tnum mt-1 font-serif text-[28px] leading-none">{t.ticket.ticket_id}</dd></div>
            <div><dt className="eyebrow">Departs</dt><dd className="tnum mt-1 flex items-center gap-2 font-serif text-[28px] leading-none"><CalendarClock className="size-5 text-faint" aria-hidden />{fmtTime(s.depart_at)}</dd></div>
            <div><dt className="eyebrow">Arrives</dt><dd className="tnum mt-1 font-serif text-[28px] leading-none">{fmtTime(s.arrive_at)}</dd></div>
          </dl>
          
        </article>
      </div>

      <aside aria-label="About you" className="grid content-start gap-4">
        {p && (
          <div className="rise grid gap-3 rounded-card-sm border border-line p-6">
            <span className="eyebrow">Your details</span>
            <p className="text-[15px]">{p.party_size > 1 ? `Party of ${p.party_size}` : 'Travelling alone'}</p>
            <NeedChips needs={p.needs} />
            <Link to="/profile" className="text-[13px] underline decoration-line underline-offset-4 hover:decoration-ink">Edit details</Link>
          </div>
        )}
        <div className="rise grid gap-2 rounded-card-sm bg-surface-2 p-6">
          <span className="eyebrow !text-info-fg">If your train is cancelled</span>
          <p className="text-[14px] text-info-fg">Pick a first and second option. Everyone's picks are placed together, and you can see exactly why.</p>
        </div>
      </aside>
    </div>
  )
}
