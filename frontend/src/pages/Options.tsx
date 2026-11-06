import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Hourglass, Send, Zap } from 'lucide-react'
import { AnimatePresence } from 'motion/react'
import * as m from 'motion/react-m'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { meApi } from '@/api/endpoints'
import { ApiError } from '@/api/http'
import { describeError, toastError } from '@/api/errors'
import { qk } from '@/api/queryKeys'
import { CountdownRing, ServiceCard } from '@/components/common/domain'
import { EmptyState, ErrorState, SkeletonBlocks } from '@/components/common/primitives'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/form'
import { S } from '@/config/strings'
import { useIdempotentAction } from '@/hooks/useAction'
import { useMe, useOptions, useStatus, useTrip } from '@/hooks/queries'
import { cn } from '@/lib/utils'

export default function Options() {
  const nav = useNavigate()
  const qc = useQueryClient()
  const opts = useOptions()
  const me = useMe()
  const status = useStatus()
  const trip = useTrip()
  const [first, setFirst] = useState<number | null>(null)
  const [second, setSecond] = useState<number | null>(null)
  const [any, setAny] = useState(false)
  const [sending, setSending] = useState(false)
  const [noGrab, setNoGrab] = useState<Set<number>>(new Set())
  const [grabNote, setGrabNote] = useState(false)
  const items = opts.data?.items ?? []
  const batch = opts.data?.batch ?? null
  const hasRequest = status.data?.state === 'REQUESTED'
  const delayed = trip.data?.disruption?.type === 'delay'
  const alts = useQuery({ queryKey: qk.alternatives, queryFn: meApi.alternatives, enabled: !!delayed })
  const waitAlt = alts.data?.items.find((a) => a.type === 'WAIT_DELAYED')
  const allowAuto = me.data?.allow_auto ?? true

  // drop selections that vanished (service filled / cancelled / re-routed)
  useEffect(() => {
    const ids = new Set(items.map((o) => o.request_service_id))
    if (first && !ids.has(first)) setFirst(null)
    if (second && !ids.has(second)) setSecond(null)
  }, [items]) // eslint-disable-line react-hooks/exhaustive-deps

  // TODO(contract): there is no passenger-side open-booking flag. "Seats available now" is shown only once an allocation
  // run has completed (no open batch and this passenger has moved past AFFECTED) and the option still has seats.
  const allocationDone = batch === null && !!status.data && !['AFFECTED', 'REGISTERED', 'BOOKED'].includes(status.data.state)
  const [grabSid, setGrabSid] = useState<number | null>(null)
  const claim = useIdempotentAction((key, sid: number) => meApi.claim(key, sid), {
    onDone: () => nav('/status'),
    onError: (e) => {
      if (e instanceof ApiError && (e.status === 409 || e.code === 'INVALID_STATE') && grabSid !== null) {
        setNoGrab((s) => new Set(s).add(grabSid)); setGrabNote(true); qc.invalidateQueries({ queryKey: qk.options }); return true
      }
      return false
    },
  })

  const toggle = (sid: number) => {
    if (any) return
    if (first === sid) { setFirst(second); setSecond(null) }
    else if (second === sid) setSecond(null)
    else if (first === null) setFirst(sid)
    else setSecond(sid)
  }
  const setAllowAuto = async (v: boolean) => {
    qc.setQueryData(qk.me, (m: any) => (m ? { ...m, allow_auto: v } : m))
    try { await meApi.patch({ allow_auto: v }) } catch (e) { qc.invalidateQueries({ queryKey: qk.me }); const ui = describeError(e); if (ui.message && !(e instanceof ApiError && e.code === 'INVALID_STATE')) toastError(e) }
  }
  const valid = any || first !== null
  const send = async (retried = false): Promise<void> => {
    setSending(true)
    try {
      await meApi.request({ choice1_service_id: any ? null : first, choice2_service_id: any ? null : second, any_fastest: any })
      qc.invalidateQueries({ queryKey: qk.status })
      nav('/status')
    } catch (e) {
      if (e instanceof ApiError && e.code === 'BATCH_CLOSED' && !retried) {
        toast(S.options.nextRound) // P-5.7: auto-resubmit into the next round
        qc.invalidateQueries({ queryKey: qk.options })
        return send(true)
      }
      toastError(e)
    } finally {
      setSending(false)
    }
  }
  const label = (sid: number | null) => items.find((o) => o.request_service_id === sid)?.label
  const rankOf = (sid: number): 1 | 2 | undefined => (first === sid ? 1 : second === sid ? 2 : undefined)
  const summary = useMemo(() => (any ? S.options.anyFastest : first ? `${S.options.first}: ${label(first) ?? ''}${second ? ` · ${S.options.second}: ${label(second) ?? ''}` : ''}` : S.options.pick1), [any, first, second, items]) // eslint-disable-line react-hooks/exhaustive-deps

  if (opts.isLoading) return <SkeletonBlocks rows={4} rowClass="h-40" />
  if (opts.isError) return <ErrorState title="We couldn't load your options" onRetry={() => opts.refetch()} />

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_360px]">
      <div className="grid content-start gap-6 pb-28 lg:pb-0">
        <div className="grid gap-2">
          <h1 className="rise rise-1 text-[clamp(2.2rem,1.4rem+3vw,3.5rem)] leading-[1.05]">{S.options.title}</h1>
        </div>

        {waitAlt && (
          <div className="rounded-card-sm border border-warning/40 bg-warning-bg p-5 text-warning-fg">
            <p className="font-medium">{waitAlt.title}</p>
            <p className="mt-1 text-[14px]">{waitAlt.description}</p>
            <Button className="mt-3" size="sm" variant="dark" onClick={async () => { try { await meApi.acceptAlternative('WAIT_DELAYED', waitAlt.ref); qc.invalidateQueries({ queryKey: qk.status }); nav('/status') } catch (e) { toastError(e) } }}>Keep my train</Button>
          </div>
        )}

        {/* batch banner (P-5.1) */}
        <div className="rise rise-2 flex flex-wrap items-center gap-5 rounded-card-sm border border-line p-5 sm:p-6" role="status">
          {batch ? (
            <>
              <CountdownRing opensAt={batch.opens_at} closesAt={batch.closes_at} size={92} />
              <div className="grid gap-1">
                <p className="font-medium">{S.options.bannerOpen} <span className="sr-only">{batch.closes_at}</span></p>
                <p className="max-w-[46ch] text-[14px] text-muted">Everyone's choices are collected first, then placed together. Tapping fast gives no advantage.</p>
              </div>
            </>
          ) : (
            <p className="flex items-center gap-3 text-[15px]"><Hourglass className="size-5 text-info" aria-hidden /> {S.options.bannerNone}</p>
          )}
        </div>

        {/* "Any, fastest" + auto-placement (P-5.3) */}
        <div className="rise rise-3 grid gap-3 sm:grid-cols-2">
          <label className={cn('flex cursor-pointer items-center justify-between gap-4 rounded-panel border p-4', any ? 'border-accent bg-accent-subtle' : 'border-line')}>
            <span className="grid gap-0.5"><span className="flex items-center gap-2 font-medium"><Zap className="size-4" aria-hidden /> {S.options.anyFastest}</span><span className="text-[13px] text-muted">{S.options.anyFastestHint}</span></span>
            <Switch checked={any} onCheckedChange={(v) => { setAny(v); if (v) { setFirst(null); setSecond(null) } }} aria-label={S.options.anyFastest} />
          </label>
          <label className="flex cursor-pointer items-center justify-between gap-4 rounded-panel border border-line p-4">
            <span className="text-[14px]">{S.options.allowAuto}</span>
            <Switch checked={allowAuto} onCheckedChange={setAllowAuto} aria-label={S.options.allowAuto} />
          </label>
        </div>

        {grabNote && <p role="status" className="text-[13px] text-muted">{S.options.grabClosed}</p>}

        {items.length === 0 ? (
          <EmptyState title="Nothing reaches your stop right now" body={S.options.empty} />
        ) : (
          <ul className="grid gap-3" aria-label="Options sorted by arrival time">
            <AnimatePresence initial={false}>
              {items.map((o) => (
                <m.li key={o.option_id} layout="position" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}>
                  <ServiceCard option={o} rank={rankOf(o.request_service_id)} disabled={any || !o.meets_deadline} onSelect={() => toggle(o.request_service_id)}
                    openBooking={allocationDone && o.seats_left > 0 && !noGrab.has(o.request_service_id)}
                    onGrab={() => { setGrabSid(o.request_service_id); claim.run(o.request_service_id) }} grabbing={claim.pending} />
                </m.li>
              ))}
            </AnimatePresence>
          </ul>
        )}
      </div>

      {/* laptop side panel: request summary */}
      <aside className="hidden content-start gap-4 lg:grid" aria-label="Your request">
        <div className="sticky top-24 grid gap-5 rounded-card-sm border border-line p-6">
          <span className="eyebrow">Your request</span>
          <ol className="grid gap-3">
            {[{ n: 1, sid: first }, { n: 2, sid: second }].map(({ n, sid }) => (
              <li key={n} className="flex items-start gap-3">
                <span className={cn('grid size-9 shrink-0 place-items-center rounded-full border font-serif text-[18px]', sid ? 'border-accent bg-accent text-accent-contrast' : 'border-line text-faint')}>{n}</span>
                <span className={cn('pt-1.5 text-[14px]', !sid && 'text-faint')}>{any ? (n === 1 ? S.options.anyFastest : '—') : label(sid) ?? (n === 1 ? S.options.pick1 : 'Optional second choice')}</span>
              </li>
            ))}
          </ol>
          <Button variant="primary" size="lg" disabled={!valid} loading={sending} onClick={() => send()}><Send /> {hasRequest ? S.options.update : S.options.send}</Button>
          <p className="text-[12px] text-muted">Re-sending while the window is open replaces your request.</p>
        </div>
      </aside>

      {/* mobile sticky bar: thumb-reachable primary action */}
      <div className="fixed inset-x-0 bottom-[calc(68px+var(--safe-bottom))] z-20 border-t border-line bg-bg/95 px-4 py-3 backdrop-blur-sm lg:hidden">
        <div className="mx-auto flex max-w-lg items-center gap-3">
          <p className="min-w-0 flex-1 truncate text-[13px] text-muted">{summary}</p>
          <Button variant="primary" disabled={!valid} loading={sending} onClick={() => send()}>{hasRequest ? S.options.update : S.options.send}</Button>
        </div>
      </div>
    </div>
  )
}
