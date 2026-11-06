import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useEffect, useState } from 'react'
import { opsApi } from '@/api/endpoints'
import { qk } from '@/api/queryKeys'
import { NeedChips, QRPanel, ScoreBars } from '@/components/common/domain'
import { EmptyState, ErrorState, SkeletonBlocks } from '@/components/common/primitives'
import { StatusPill } from '@/components/common/StatusPill'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/form'
import { Select, SidePanel, Tip } from '@/components/ui/overlays'
import { fmtDateTime, fmtTime } from '@/lib/utils'

const ANY = 'all'

function PassengerDrawer({ id }: { id: number }) {
  const q = useQuery({ queryKey: ['ops', 'passenger', id], queryFn: () => opsApi.passenger(id) })
  const qr = useQuery({ queryKey: ['ops', 'passenger-qr', id], queryFn: () => opsApi.passengerQr(id), staleTime: 60_000 })
  if (q.isLoading) return <SkeletonBlocks rows={3} rowClass="h-24" />
  if (q.isError || !q.data) return <ErrorState onRetry={() => q.refetch()} />
  const { passenger: p, status, why } = q.data
  return (
    <div className="grid gap-6">
      <div className="grid gap-2">
        <span className="eyebrow">Passenger {p.ticket_id}</span>
        <h3 className="text-[30px] leading-tight">{p.name}</h3>
        <p className="text-[14px] text-muted">{p.hub.name} → {p.destination.name} · party of {p.party_size}</p>
        <NeedChips needs={p.needs} />
      </div>
      <div className="grid gap-2 rounded-panel border border-line p-4">
        <StatusPill kind="passenger" value={status.state} />
        <p className="text-[14px]">{status.headline}</p>
        {status.allocation && <p className="tnum text-[13px] text-muted">{status.allocation.service.label} · {fmtTime(status.allocation.service.depart_at)} · seats {status.allocation.seats.join(', ') || status.allocation.seat_count}</p>}
      </div>
      <div className="grid gap-3">
        <span className="eyebrow">Why · priority {Math.round(why.score)}</span>
        <ScoreBars breakdown={why.breakdown} weights={why.weights} />
        <p className="text-[13px] text-muted">{why.explanation}</p>
      </div>
      {qr.data && <div className="grid justify-items-start gap-2"><span className="eyebrow">Login QR</span><QRPanel value={qr.data.url} size={150} /><p className="text-[12px] text-muted">Expires {fmtDateTime(qr.data.expires_at)}</p></div>}
    </div>
  )
}

export default function Allocations() {
  const [status, setStatus] = useState(ANY)
  const [needs, setNeeds] = useState(ANY)
  const [dest, setDest] = useState(ANY)
  const [search, setSearch] = useState('')
  const [debounced, setDebounced] = useState('')
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState<number | null>(null)
  useEffect(() => { const t = setTimeout(() => { setDebounced(search); setPage(1) }, 300); return () => clearTimeout(t) }, [search])
  const map = useQuery({ queryKey: qk.ops.map, queryFn: opsApi.map, staleTime: 60_000 })
  const params = { status: status === ANY ? undefined : status, needs: needs === ANY ? undefined : needs, destination: dest === ANY ? undefined : dest, q: debounced || undefined, page, page_size: 15 }
  const q = useQuery({ queryKey: [...qk.ops.allocations, params], queryFn: () => opsApi.allocations(params), placeholderData: (p) => p, staleTime: 3_000 })
  const pages = q.data ? Math.max(1, Math.ceil(q.data.total / q.data.page_size)) : 1
  return (
    <div className="mt-4 grid gap-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Input aria-label="Search passengers" placeholder="Search name or ticket" value={search} onChange={(e) => setSearch(e.target.value)} />
        <Select label="Status" value={status} onValueChange={(v) => { setStatus(v); setPage(1) }} options={[{ value: ANY, label: 'Any status' }, ...['held', 'confirmed', 'declined', 'expired', 'released'].map((s) => ({ value: s, label: s }))]} />
        <Select label="Needs" value={needs} onValueChange={(v) => { setNeeds(v); setPage(1) }} options={[{ value: ANY, label: 'Any needs' }, { value: 'accessible', label: 'Accessible' }, { value: 'priority', label: 'Priority' }, { value: 'general', label: 'General' }]} />
        <Select label="Destination" value={dest} onValueChange={(v) => { setDest(v); setPage(1) }} options={[{ value: ANY, label: 'Any destination' }, ...(map.data?.nodes ?? []).filter((n) => !n.is_hub).map((n) => ({ value: n.code, label: n.name }))]} />
      </div>
      {q.isLoading ? <SkeletonBlocks rows={5} rowClass="h-12" /> : q.isError ? <ErrorState onRetry={() => q.refetch()} /> : q.data!.items.length === 0 ? <EmptyState title="No matching allocations" /> : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-[14px]">
            <caption className="sr-only">Allocations</caption>
            <thead className="text-left text-[11px] uppercase tracking-[0.06em] text-muted"><tr><th className="py-2 pr-4 font-normal">Passenger</th><th className="pr-4 font-normal">Party</th><th className="pr-4 font-normal">Score</th><th className="pr-4 font-normal">Choice</th><th className="pr-4 font-normal">Service</th><th className="pr-4 font-normal">Status</th><th className="font-normal">Why</th></tr></thead>
            <tbody>
              {q.data!.items.map((r) => (
                <tr key={`${r.passenger.id}-${r.service_label}`} className="cursor-pointer border-t border-line hover:bg-surface-2">
                  <th scope="row" className="py-3 pr-4 text-left font-medium"><button type="button" className="text-left underline decoration-line underline-offset-4 hover:decoration-ink" onClick={() => setOpen(r.passenger.id)}>{r.passenger.name}</button></th>
                  <td className="tnum pr-4">{r.passenger.party_size}</td>
                  <td className="tnum pr-4">{Math.round(r.score)}</td>
                  <td className="pr-4 capitalize">{r.choice_rank}</td>
                  <td className="pr-4">{r.service_label}</td>
                  <td className="pr-4"><StatusPill kind="allocation" value={r.status} size="sm" /></td>
                  <td className="max-w-[320px]"><Tip content={r.explanation}><span className="block truncate text-muted">{r.explanation}</span></Tip></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="flex items-center justify-between text-[13px] text-muted">
        <span className="tnum">{q.data ? `${q.data.total} total` : ''}</span>
        <div className="flex items-center gap-2">
          <Button size="icon" variant="ghost" aria-label="Previous page" disabled={page <= 1} onClick={() => setPage(page - 1)}><ChevronLeft /></Button>
          <span className="tnum">Page {page} of {pages}</span>
          <Button size="icon" variant="ghost" aria-label="Next page" disabled={page >= pages} onClick={() => setPage(page + 1)}><ChevronRight /></Button>
        </div>
      </div>
      <SidePanel open={open !== null} onOpenChange={(o) => !o && setOpen(null)} title="Passenger">{open !== null && <PassengerDrawer id={open} />}</SidePanel>
    </div>
  )
}
