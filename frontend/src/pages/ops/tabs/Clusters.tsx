import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, Check } from 'lucide-react'
import { opsApi } from '@/api/endpoints'
import { qk } from '@/api/queryKeys'
import { ErrorState, EmptyState, SkeletonBlocks } from '@/components/common/primitives'
import { Pill } from '@/components/common/StatusPill'
import { fmtTime } from '@/lib/utils'

export default function Clusters() {
  const q = useQuery({ queryKey: qk.ops.clusters, queryFn: opsApi.clusters, staleTime: 3_000 })
  if (q.isLoading) return <SkeletonBlocks rows={4} rowClass="h-12" className="mt-4" />
  if (q.isError) return <ErrorState onRetry={() => q.refetch()} />
  if (!q.data!.items.length) return <EmptyState title="No stranded groups" body="Groups appear here once a disruption affects passengers." />
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="w-full min-w-[760px] text-[14px]">
        <caption className="sr-only">Stranded groups: demand against capacity</caption>
        <thead className="text-left text-[11px] uppercase tracking-[0.06em] text-muted"><tr><th className="py-2 pr-4 font-normal">Destination</th><th className="pr-4 font-normal">From</th><th className="pr-4 font-normal">Needs</th><th className="pr-4 font-normal">People</th><th className="w-[30%] font-normal">Demand vs capacity</th></tr></thead>
        <tbody>
          {q.data!.items.map((c) => {
            const over = c.demand_seats > c.capacity_seats
            const pct = Math.min(100, (c.demand_seats / Math.max(1, Math.max(c.demand_seats, c.capacity_seats))) * 100)
            const cap = Math.min(100, (c.capacity_seats / Math.max(1, Math.max(c.demand_seats, c.capacity_seats))) * 100)
            return (
              <tr key={c.id} className="border-t border-line">
                <th scope="row" className="py-3 pr-4 text-left font-medium">{c.destination.name}</th>
                <td className="tnum pr-4">{fmtTime(c.time_bucket_start)}</td>
                <td className="pr-4 capitalize">{c.needs_class}</td>
                <td className="tnum pr-4">{c.size}</td>
                <td>
                  <div className="flex items-center gap-3">
                    <div className="relative h-2.5 flex-1 overflow-hidden rounded-full bg-line" role="img" aria-label={`Demand ${c.demand_seats} seats, capacity ${c.capacity_seats}`}>
                      <div className={`absolute inset-y-0 left-0 rounded-full ${over ? 'bg-danger' : 'bg-success'}`} style={{ width: `${pct}%` }} />
                      <div className="absolute inset-y-0 w-0.5 bg-ink" style={{ left: `${cap}%` }} />
                    </div>
                    <Pill tone={over ? 'danger' : 'success'} icon={over ? AlertTriangle : Check} size="sm">{c.demand_seats}/{c.capacity_seats}</Pill>
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
