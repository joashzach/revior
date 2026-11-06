import { useQuery } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { opsApi } from '@/api/endpoints'
import { qk } from '@/api/queryKeys'
import { NeedChips } from '@/components/common/domain'
import { EmptyState, ErrorState, SkeletonBlocks } from '@/components/common/primitives'
import { Button } from '@/components/ui/button'

export default function Unresolved({ onAddCapacity }: { onAddCapacity: () => void }) {
  const q = useQuery({ queryKey: qk.ops.unresolved, queryFn: opsApi.unresolved, staleTime: 3_000 })
  return (
    <div className="mt-4 grid gap-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[14px] text-muted">Passengers no service could take, longest wait first.</p>
        <Button size="sm" variant="dark" onClick={onAddCapacity}><Plus /> Add charter bus</Button>
      </div>
      {q.isLoading ? <SkeletonBlocks rows={3} rowClass="h-20" /> : q.isError ? <ErrorState onRetry={() => q.refetch()} /> : q.data!.items.length === 0 ? (
        <EmptyState title="Nobody is unresolved" body="Everyone has a seat, a waitlist place or an alternative." />
      ) : (
        <ul className="grid gap-3 lg:grid-cols-2">
          {[...q.data!.items].sort((a, b) => b.waited_min - a.waited_min).map((r) => (
            <li key={r.passenger.id} className="grid gap-3 rounded-panel border border-line p-4">
              <div className="flex items-baseline justify-between gap-3">
                <span className="font-serif text-[24px] leading-tight">{r.passenger.name}</span>
                <span className="tnum text-[13px] text-muted">waited {r.waited_min} min</span>
              </div>
              <p className="text-[13px] text-muted">To {r.passenger.destination.name} · party of {r.passenger.party_size}</p>
              <NeedChips needs={r.passenger.needs} />
              {r.alternatives.length > 0 && <ul className="grid gap-1 border-t border-line pt-2 text-[13px]">{r.alternatives.map((a) => <li key={a.ref}>{a.title}</li>)}</ul>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
