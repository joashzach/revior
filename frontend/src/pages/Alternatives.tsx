import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, Car, Clock, Plus, Route, Users, Waypoints } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { meApi } from '@/api/endpoints'
import { toastError } from '@/api/errors'
import { qk } from '@/api/queryKeys'
import type { Alternative, AlternativeType, Pod } from '@/api/types'
import { EmptyState, ErrorState, SkeletonBlocks } from '@/components/common/primitives'
import { Pill } from '@/components/common/StatusPill'
import { Button } from '@/components/ui/button'
import { ConfirmDialog, Select, Sheet } from '@/components/ui/overlays'
import { useMe } from '@/hooks/queries'
import { useIdempotentAction } from '@/hooks/useAction'
import { fmtInr, fmtTime } from '@/lib/utils'

const TYPE_LABEL: Record<AlternativeType, string> = { LATER_SERVICE: 'Later service', MULTI_LEG: 'Multi-leg', POD: 'Shared cab', ALT_HUB: 'Nearby hub', WAIT_DELAYED: 'Wait for delayed train' }
const TYPE_ICON = { LATER_SERVICE: Clock, MULTI_LEG: Route, POD: Car, ALT_HUB: Waypoints, WAIT_DELAYED: Clock } as const

function PodCard({ pod, mine, onJoin, joining, onLeave, onConfirm }: { pod: Pod; mine: boolean; onJoin: () => void; joining: boolean; onLeave: () => void; onConfirm: () => void }) {
  const left = pod.capacity - pod.seats_taken
  return (
    <article className="grid gap-4 rounded-card-sm border border-line p-5 sm:p-6" aria-label={`Shared ${pod.mode} to ${pod.destination.name}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-[13px] uppercase tracking-[0.05em] text-muted"><Car className="size-4" aria-hidden /> Shared {pod.mode}</span>
        <Pill tone={pod.status === 'confirmed' ? 'success' : pod.status === 'full' ? 'warning' : 'info'} icon={Users}>{pod.seats_taken}/{pod.capacity} seats</Pill>
      </div>
      <h3 className="text-[24px] leading-tight">{pod.origin.name} → {pod.destination.name}</h3>
      <p className="tnum text-[14px] text-muted">{pod.route_km.toFixed(1)} km · {fmtInr(pod.fare_per_seat)} per seat · {fmtInr(pod.fare_total)} split {pod.seats_taken} ways</p>
      <ul className="flex flex-wrap gap-2 text-[13px]" aria-label="Members">
        {pod.members.map((m) => <li key={m.passenger_id} className="rounded-full border border-line px-3 py-1">{m.name}</li>)}
      </ul>
      <div className="flex flex-wrap gap-3">
        {mine ? (
          <>
            <Button variant="dark" size="sm" disabled={pod.seats_taken < 2 || pod.status === 'confirmed'} onClick={onConfirm}>Confirm cab</Button>
            <Button variant="ghost" size="sm" onClick={onLeave}>Leave</Button>
          </>
        ) : (
          <Button variant="dark" size="sm" disabled={left <= 0} loading={joining} onClick={onJoin}>{left <= 0 ? 'Full' : 'Join'}</Button>
        )}
      </div>
    </article>
  )
}

export default function Alternatives() {
  const nav = useNavigate()
  const qc = useQueryClient()
  const me = useMe()
  const alts = useQuery({ queryKey: qk.alternatives, queryFn: meApi.alternatives, staleTime: 5_000 })
  const pods = useQuery({ queryKey: qk.pods, queryFn: meApi.podsSuggested, staleTime: 5_000 })
  const [confirm, setConfirm] = useState<Alternative | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [mode, setMode] = useState<'cab' | 'auto'>('cab')
  const [busy, setBusy] = useState(false)
  const join = useIdempotentAction((k, id: number) => meApi.joinPod(id, k), { onDone: () => qc.invalidateQueries({ queryKey: qk.pods }) })
  const [joiningId, setJoiningId] = useState<number | null>(null)

  const refreshAll = () => { for (const k of [qk.alternatives, qk.pods, qk.status, qk.me]) qc.invalidateQueries({ queryKey: k }) }
  const run = async (fn: () => Promise<unknown>, ok?: string) => {
    setBusy(true)
    try { await fn(); if (ok) toast.success(ok); refreshAll() } catch (e) { toastError(e); refreshAll() } finally { setBusy(false) }
  }
  const choose = (a: Alternative) => run(async () => { await meApi.acceptAlternative(a.type, a.ref); setConfirm(null); nav('/status') })
  const request = (a: Alternative) => run(async () => {
    await meApi.request({ any_fastest: false, choice1_service_id: a.legs[0]?.service.id ?? null })
    nav('/status')
  })

  if (alts.isLoading) return <SkeletonBlocks rows={3} rowClass="h-40" />
  if (alts.isError) return <ErrorState title="We couldn't load alternatives" onRetry={() => alts.refetch()} />
  const items = (alts.data?.items ?? []).filter((a) => a.type !== 'POD')
  const dest = me.data?.destination
  const myId = me.data?.id
  const podItems = pods.data?.items ?? []
  const myPod = podItems.find((p) => p.members.some((m) => m.passenger_id === myId))

  return (
    <div className="grid gap-8">
      <div className="grid gap-2">
        <h1 className="rise text-[clamp(2.2rem,1.4rem+3vw,3.5rem)] leading-[1.05]">Other ways home</h1>
      </div>

      {items.length === 0 ? (
        <EmptyState title="No alternatives right now" body="New options appear here as services change. Shared cabs are below." />
      ) : (
        <ul className="grid gap-3 lg:grid-cols-2">
          {items.map((a) => {
            const Icon = TYPE_ICON[a.type]
            return (
              <li key={a.ref} className="grid content-between gap-4 rounded-card-sm border border-line p-5 sm:p-6">
                <div className="grid gap-2">
                  <span className="flex items-center gap-2 text-[13px] uppercase tracking-[0.05em] text-muted"><Icon className="size-4" aria-hidden /> {TYPE_LABEL[a.type]}</span>
                  <h2 className="text-[24px] leading-tight">{a.title}</h2>
                  <p className="text-[14px] text-muted">{a.description}</p>
                  {a.eta_at && <p className="tnum text-[14px]">Arrives {fmtTime(a.eta_at)}</p>}
                  {a.legs.length > 1 && (
                    <ol className="grid gap-1 text-[13px] text-muted">
                      {a.legs.map((l, i) => <li key={i} className="tnum">{l.from.name} {fmtTime(l.depart_at)} → {l.to.name} {fmtTime(l.arrive_at)}</li>)}
                    </ol>
                  )}
                </div>
                <div>
                  {a.requires_allocation
                    ? <Button size="sm" variant="dark" loading={busy} onClick={() => request(a)}>Request a seat <ArrowRight /></Button>
                    : <Button size="sm" variant="dark" onClick={() => setConfirm(a)}>Choose this</Button>}
                </div>
              </li>
            )
          })}
        </ul>
      )}

      <section className="grid gap-4" aria-label="Shared cabs">
        <div className="flex flex-wrap items-end justify-between gap-3 border-t border-line pt-8">
          <div className="grid gap-1">
            <span className="eyebrow">Share the ride</span>
            <h2 className="text-[clamp(1.8rem,1.3rem+1.6vw,2.4rem)]">Shared cabs{dest ? ` to ${dest.name}` : ''}</h2>
          </div>
          {!myPod && <Button variant="dark" size="sm" onClick={() => setCreateOpen(true)}><Plus /> Start a cab</Button>}
        </div>
        {pods.isLoading ? <SkeletonBlocks rows={1} rowClass="h-40" /> : podItems.length === 0 ? (
          <EmptyState title="No shared cabs yet" body="Start one and others heading your way can join." />
        ) : (
          <ul className="grid gap-3 lg:grid-cols-2">
            {podItems.map((p) => (
              <li key={p.id}>
                <PodCard
                  pod={p}
                  mine={myPod?.id === p.id}
                  joining={joiningId === p.id && join.pending}
                  onJoin={() => { setJoiningId(p.id); join.run(p.id) }}
                  onLeave={() => run(() => meApi.leavePod(p.id))}
                  onConfirm={() => run(() => meApi.confirmPod(p.id))}
                />
              </li>
            ))}
          </ul>
        )}
      </section>

      <ConfirmDialog
        open={!!confirm}
        onOpenChange={(o) => !o && setConfirm(null)}
        title="Choose this option?"
        description={confirm ? `${confirm.title}. ${confirm.description}` : undefined}
        confirmLabel="Yes, choose it"
        loading={busy}
        onConfirm={() => confirm && choose(confirm)}
      />

      <Sheet open={createOpen} onOpenChange={setCreateOpen} title="Start a shared cab" description={dest ? `Heading to ${dest.name}. Others going the same way can join and split the fare.` : undefined}>
        <div className="grid gap-4 pb-4">
          <Select label="Vehicle" value={mode} onValueChange={(v) => setMode(v as 'cab' | 'auto')} options={[{ value: 'cab', label: 'Cab · up to 4 seats' }, { value: 'auto', label: 'Auto · up to 3 seats' }]} />
          <Button variant="primary" loading={busy} onClick={() => dest && run(async () => { await meApi.createPod(dest.id, mode); setCreateOpen(false) })}>Start cab</Button>
        </div>
      </Sheet>
    </div>
  )
}
