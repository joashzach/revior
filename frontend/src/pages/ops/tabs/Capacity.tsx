import { useQuery } from '@tanstack/react-query'
import { Accessibility } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { opsApi } from '@/api/endpoints'
import { qk } from '@/api/queryKeys'
import type { CapacityRow } from '@/api/types'
import { CapacityBar, MODE_LABEL } from '@/components/common/domain'
import { ErrorState, SkeletonBlocks } from '@/components/common/primitives'
import { Pill, StatusPill } from '@/components/common/StatusPill'
import { fmtTime } from '@/lib/utils'

function useCapacity() {
  return useQuery({ queryKey: qk.ops.capacity, queryFn: opsApi.capacity, staleTime: 3_000 })
}

/** A row flashes once whenever its free seat count goes UP (a seat was released). */
function useReleaseFlash(rows: CapacityRow[] | undefined) {
  const prev = useRef(new Map<number, number>())
  const [flash, setFlash] = useState<Set<number>>(new Set())
  useEffect(() => {
    if (!rows) return
    const hit = new Set<number>()
    for (const r of rows) {
      const before = prev.current.get(r.service.id)
      if (before !== undefined && r.free > before) hit.add(r.service.id)
      prev.current.set(r.service.id, r.free)
    }
    if (!hit.size) return
    setFlash(hit)
    const t = setTimeout(() => setFlash(new Set()), 900)
    return () => clearTimeout(t)
  }, [rows])
  return flash
}

export function CapacityTab({ onSelect }: { onSelect?: (id: number) => void }) {
  const q = useCapacity()
  const flash = useReleaseFlash(q.data?.items)
  if (q.isLoading) return <SkeletonBlocks rows={4} rowClass="h-12" className="mt-4" />
  if (q.isError) return <ErrorState onRetry={() => q.refetch()} />
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="w-full min-w-[820px] text-[14px]">
        <caption className="sr-only">Capacity by service</caption>
        <thead className="text-left text-[11px] uppercase tracking-[0.06em] text-muted">
          <tr><th className="py-2 pr-4 font-normal">Service</th><th className="pr-4 font-normal">Mode</th><th className="pr-4 font-normal">Departs</th><th className="w-[28%] pr-4 font-normal">Seats</th><th className="pr-4 font-normal">Taken</th><th className="pr-4 font-normal">Accessible free</th><th className="pr-4 font-normal">Waitlist</th><th className="font-normal">Status</th></tr>
        </thead>
        <tbody>
          {q.data!.items.map((r) => (
            <tr key={r.service.id} onClick={() => onSelect?.(r.service.id)} className={`cursor-pointer border-t border-line hover:bg-surface-2 ${flash.has(r.service.id) ? 'flash-once' : ''}`}>
              <th scope="row" className="py-3 pr-4 text-left font-medium">{r.service.label}</th>
              <td className="pr-4 text-muted">{MODE_LABEL[r.service.mode]}</td>
              <td className="tnum pr-4">{fmtTime(r.service.depart_at)}</td>
              <td className="pr-4"><CapacityBar total={r.total_seats} confirmed={r.confirmed} held={r.held} /></td>
              <td className="tnum pr-4">{Math.min(r.total_seats, r.confirmed + r.held)}/{r.total_seats}</td>
              <td className="pr-4"><Pill tone={r.accessible_free > 0 ? 'info' : 'neutral'} icon={Accessibility} size="sm">{r.accessible_free}</Pill></td>
              <td className="tnum pr-4">{r.waitlist_len}</td>
              <td><StatusPill kind="service" value={r.service.status} size="sm" /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function ServiceDetail({ id }: { id: number }) {
  const q = useCapacity()
  const row = q.data?.items.find((r) => r.service.id === id)
  if (!row) return <SkeletonBlocks rows={2} rowClass="h-20" />
  const s = row.service
  return (
    <div className="grid gap-5">
      <div className="grid gap-2"><span className="eyebrow">{MODE_LABEL[s.mode]}</span><h3 className="text-[28px] leading-tight">{s.label}</h3><StatusPill kind="service" value={s.status} /></div>
      <dl className="grid grid-cols-2 gap-4">
        <div><dt className="eyebrow">Departs</dt><dd className="tnum font-serif text-[26px] leading-none">{fmtTime(s.depart_at)}</dd></div>
        <div><dt className="eyebrow">Arrives</dt><dd className="tnum font-serif text-[26px] leading-none">{fmtTime(s.arrive_at)}</dd></div>
        <div><dt className="eyebrow">Confirmed</dt><dd className="tnum font-serif text-[26px] leading-none">{row.confirmed}</dd></div>
        <div><dt className="eyebrow">Held</dt><dd className="tnum font-serif text-[26px] leading-none">{row.held}</dd></div>
        <div><dt className="eyebrow">Free</dt><dd className="tnum font-serif text-[26px] leading-none">{row.free}</dd></div>
        <div><dt className="eyebrow">Waitlist</dt><dd className="tnum font-serif text-[26px] leading-none">{row.waitlist_len}</dd></div>
      </dl>
      <CapacityBar total={row.total_seats} confirmed={row.confirmed} held={row.held} />
    </div>
  )
}
