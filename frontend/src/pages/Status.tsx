import { useQuery } from '@tanstack/react-query'
import { ArrowRight, CheckCircle2, Hourglass, Pencil, Repeat, Route, Undo2 } from 'lucide-react'
import { lazy, Suspense, useState } from 'react'
import { Link } from 'react-router-dom'
import { meApi } from '@/api/endpoints'
import { qk } from '@/api/queryKeys'
import type { Allocation } from '@/api/types'
import { CountdownRing, HoldTimer, MODE_ICON, MODE_LABEL, QRPanel } from '@/components/common/domain'
import { NumberRoll, ErrorState, SkeletonBlocks } from '@/components/common/primitives'
import { StatusPill } from '@/components/common/StatusPill'
import { Button, buttonVariants } from '@/components/ui/button'
import { ConfirmDialog, Sheet } from '@/components/ui/overlays'
import { S } from '@/config/strings'
import { useIdempotentAction } from '@/hooks/useAction'
import { useOptions, useStatus } from '@/hooks/queries'
import { useLiveStore } from '@/realtime/useRealtime'
import { cn, fmtTime, leadOf } from '@/lib/utils'

const MiniMap = lazy(() => import('@/components/map/MiniMap'))

function AllocationCard({ a, swap }: { a: Allocation; swap?: boolean }) {
  const s = a.service
  const Icon = MODE_ICON[s.mode]
  return (
    <article className="grid gap-5 rounded-card-sm border border-line p-6 sm:p-8" aria-label={swap ? 'Swap offer' : 'Your seat'}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="flex items-center gap-2 text-[13px] uppercase tracking-[0.05em] text-muted"><Icon className="size-4" aria-hidden /> {MODE_LABEL[s.mode]}</span>
        {a.status !== 'confirmed' && <StatusPill kind="allocation" value={a.status} size="lg" />}
      </div>
      <h2 className="text-[clamp(1.6rem,1.2rem+1.4vw,2.2rem)] leading-tight">{s.label}</h2>
      <dl className="grid gap-5 border-t border-line pt-5 sm:grid-cols-3">
        <div><dt className="eyebrow">Departs</dt><dd className="tnum mt-1 font-serif text-[28px] leading-none">{fmtTime(s.depart_at)}</dd></div>
        <div><dt className="eyebrow">Arrives</dt><dd className="tnum mt-1 font-serif text-[28px] leading-none">{fmtTime(s.arrive_at)}</dd></div>
        <div><dt className="eyebrow">Seats</dt><dd className="tnum mt-1 font-serif text-[28px] leading-none">{a.seats.length ? a.seats.join(', ') : a.seat_count}</dd></div>
      </dl>
    </article>
  )
}

export default function Status() {
  const st = useStatus()
  const opts = useOptions()
  const [declineOpen, setDeclineOpen] = useState(false)
  const [swapOpen, setSwapOpen] = useState(false)
  const accept = useIdempotentAction((k, id?: number) => meApi.accept(k, id))
  const decline = useIdempotentAction((k, id?: number) => meApi.decline(k, id), { onDone: () => setDeclineOpen(false) })
  const swap = useIdempotentAction((k, sid: number) => meApi.swap(k, sid), { onDone: () => setSwapOpen(false) })
  const rerouted = useLiveStore((s) => s.rerouted)
  const alts = useQuery({ queryKey: qk.alternatives, queryFn: meApi.alternatives, enabled: false })

  if (st.isLoading) return <SkeletonBlocks rows={2} rowClass="h-56" />
  if (st.isError || !st.data) return <ErrorState title="We couldn't load your status" onRetry={() => st.refetch()} />
  const d = st.data
  const a = d.allocation
  void alts

  const swapChoices = (opts.data?.items ?? []).filter((o) => o.request_service_id !== a?.service.id && o.meets_deadline)

  return (
    <div className={cn('grid gap-8', d.state === 'CONFIRMED' && 'lg:grid-cols-[1fr_340px]')}>
      <div className="grid max-w-[760px] content-start gap-6">
        <h1 className="rise flex items-start gap-3 text-[clamp(2rem,1.3rem+2.6vw,3.2rem)] leading-[1.08]" aria-live="polite">
          {d.state === 'CONFIRMED' && <CheckCircle2 className="mt-1.5 size-8 shrink-0 text-success-fg" aria-hidden />}
          {leadOf(d.headline)}
        </h1>

        {/* swap offer banner (P-6.x) */}
        {a && rerouted[a.service.id] && (
          <div role="status" className="flex items-start gap-3 rounded-card-sm border border-success/40 bg-success-bg p-5 text-success-fg">
            <Route className="mt-0.5 size-5 shrink-0" aria-hidden />
            <p className="text-[15px]">
              Your {a.service.mode === 'local_train' ? 'train' : 'bus'} was re-routed.{' '}
              {rerouted[a.service.id].skipped.length ? `It no longer stops at ${rerouted[a.service.id].skipped.join(', ')}. ` : ''}
              New arrival {fmtTime(a.service.arrive_at)}.
            </p>
          </div>
        )}

        {d.swap_offer && d.state !== 'HELD' && (
          <div role="status" className="rise flex flex-wrap items-center gap-3 rounded-card-sm border border-info/40 bg-info-bg p-5 text-info-fg">
            <Repeat className="size-5 shrink-0" aria-hidden />
            <p className="text-[15px]">Your preferred option has a seat: {d.swap_offer.service.label}.</p>
            <HoldTimer compact expiresAt={d.swap_offer.hold_expires_at} className="ml-auto" />
            <Button size="sm" variant="primary" loading={accept.pending} onClick={() => accept.run(d.swap_offer!.id)}>Switch now</Button>
          </div>
        )}

        {d.state === 'REQUESTED' && (
          <div className="rise grid gap-5 rounded-card-sm border border-line p-6 sm:p-8">
            <div className="flex flex-wrap items-center gap-6">
              {d.batch && <CountdownRing opensAt={d.batch.opens_at} closesAt={d.batch.closes_at} label={S.status.allocatingIn} size={120} />}
              <p className="max-w-[44ch] text-[15px] text-muted">Your request is in. When the window closes, everyone is placed together. You can still change it until then.</p>
            </div>
            <div><Link to="/options" className={buttonVariants({ variant: 'dark', size: 'sm' })}><Pencil /> {S.status.editRequest}</Link></div>
          </div>
        )}

        {d.state === 'HELD' && a && (
          <>
            <div className="rise flex flex-wrap items-center justify-between gap-4 rounded-card-sm border border-line p-6">
              <HoldTimer expiresAt={a.hold_expires_at} />
            </div>
            <AllocationCard a={a} />
            <div className="flex flex-wrap gap-3">
              <Button variant="primary" size="lg" loading={accept.pending} onClick={() => accept.run()}><CheckCircle2 /> {S.status.accept}</Button>
              <Button variant="ghost" size="lg" onClick={() => setDeclineOpen(true)}><Undo2 /> {S.status.decline}</Button>
              <Link to="/why" className={buttonVariants({ variant: 'quiet', size: 'lg' })}>{S.status.why}</Link>
            </div>
            {swapChoices.length > 0 && <button type="button" onClick={() => setSwapOpen(true)} className="press w-fit text-[14px] underline decoration-line underline-offset-4 hover:decoration-ink">{S.status.swap}</button>}
          </>
        )}

        {d.state === 'CONFIRMED' && a && (
          <>
            <AllocationCard a={a} />
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
              <Link to="/why" className="text-[14px] underline decoration-line underline-offset-4 hover:decoration-ink">{S.status.why}</Link>
              {swapChoices.length > 0 && <button type="button" onClick={() => setSwapOpen(true)} className="press w-fit text-[14px] underline decoration-line underline-offset-4 hover:decoration-ink">{S.status.swap}</button>}
            </div>
          </>
        )}

        {d.state === 'WAITLISTED' && (
          <div className="rise grid gap-4 rounded-card-sm border border-line p-6 sm:p-8">
            <p className="flex items-center gap-2 text-[15px] text-muted"><Hourglass className="size-5 text-info" aria-hidden /> {S.status.waitlistLine}</p>
            <ul className="grid gap-3">
              {d.waitlist.map((w) => (
                <li key={w.service_id} className="flex items-center justify-between gap-4 border-t border-line pt-3 first:border-0 first:pt-0">
                  <span className="text-[14px]">{w.label}{w.is_swap && <span className="ml-2 text-faint">(switch)</span>}</span>
                  <span className="tnum font-serif text-[28px] leading-none"><NumberRoll value={w.position} /><span className="text-[16px] text-faint"> / {w.total}</span></span>
                </li>
              ))}
            </ul>
            <Link to="/alternatives" className={cn(buttonVariants({ variant: 'dark', size: 'sm' }), 'w-fit')}>See alternatives <ArrowRight /></Link>
          </div>
        )}

        {d.state === 'REOFFER' && (
          <div role="alert" className="rise grid gap-3 rounded-card-sm border border-warning/40 bg-warning-bg p-6 text-warning-fg">
            <h2 className="text-[26px]">{S.status.reofferTitle}</h2>
            <p className="text-[15px]">{S.status.reofferBody}</p>
            <div><Link to="/options" className={buttonVariants({ variant: 'primary' })}>Choose again <ArrowRight /></Link></div>
          </div>
        )}

        {d.state === 'RESOLVED_ALT' && d.resolved_alternative && (
          <div className="rise grid gap-3 rounded-card-sm border border-success/40 bg-success-bg p-6 text-success-fg">
            <h2 className="text-[26px]">{d.resolved_alternative.title}</h2>
            <p className="text-[15px]">{d.resolved_alternative.description}</p>
            {d.resolved_alternative.eta_at && <p className="tnum text-[14px]">Arrives {fmtTime(d.resolved_alternative.eta_at)}</p>}
          </div>
        )}

        {d.state === 'UNRESOLVED' && (
          <div className="rise grid gap-3 rounded-card-sm border border-line p-6">
            <p className="text-[15px] text-muted">An operator is arranging something for you. Meanwhile, see what else could work.</p>
            <div><Link to="/alternatives" className={buttonVariants({ variant: 'dark' })}>See alternatives <ArrowRight /></Link></div>
          </div>
        )}

        {['BOOKED', 'REGISTERED', 'AFFECTED'].includes(d.state) && (
          <div className="rise grid gap-3 rounded-card-sm border border-line p-6">
            <p className="text-[15px] text-muted">{d.state === 'AFFECTED' ? 'Your service was disrupted.' : 'Nothing needs your attention.'}</p>
            <div><Link to={d.state === 'AFFECTED' ? '/options' : '/trip'} className={buttonVariants({ variant: 'dark' })}>{d.state === 'AFFECTED' ? S.trip.chooseCta : 'Back to my trip'} <ArrowRight /></Link></div>
          </div>
        )}
      </div>

      {d.state === 'CONFIRMED' && a && (
        <aside className="grid content-start gap-4" aria-label="Boarding">
          <div className="grid justify-items-center gap-3 rounded-card-sm border border-line p-6">
            <QRPanel value={`revior:ticket:${a.id}`} caption={S.status.boardingPass} size={150} />
          </div>
          <Suspense fallback={<div className="skeleton h-56 rounded-card-sm" />}><MiniMap serviceId={a.service.id} /></Suspense>
        </aside>
      )}

      <ConfirmDialog open={declineOpen} onOpenChange={setDeclineOpen} title={S.status.declineConfirmTitle} description={S.status.declineConfirmBody}
        confirmLabel={S.status.declineConfirm} danger loading={decline.pending} onConfirm={() => decline.run()} />

      <Sheet open={swapOpen} onOpenChange={setSwapOpen} title={S.status.swapTitle} description={S.status.swapBody} tall>
        <ul className="grid gap-3 pb-4">
          {swapChoices.map((o) => (
            <li key={o.option_id} className="flex items-center justify-between gap-3 rounded-panel border border-line p-4">
              <span className="grid"><span className="font-medium">{o.label}</span><span className="tnum text-[13px] text-muted">{fmtTime(o.depart_at)} → {fmtTime(o.eta_at)}</span></span>
              <Button size="sm" variant="dark" loading={swap.pending} onClick={() => swap.run(o.request_service_id)}>{S.status.switchNow}</Button>
            </li>
          ))}
        </ul>
        <Button variant="quiet" onClick={() => setSwapOpen(false)}>{S.status.keepCurrent}</Button>
      </Sheet>
    </div>
  )
}
