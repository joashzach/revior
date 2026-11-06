import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useEffect, useState } from 'react'
import { opsApi } from '@/api/endpoints'
import { qk } from '@/api/queryKeys'
import { EmptyState, ErrorState, SkeletonBlocks } from '@/components/common/primitives'
import { Pill } from '@/components/common/StatusPill'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/form'
import { fmtDateTime } from '@/lib/utils'

export function Pager({ page, total, size, onPage }: { page: number; total: number; size: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / size))
  return (
    <div className="flex items-center justify-between text-[13px] text-muted">
      <span className="tnum">{total} total</span>
      <div className="flex items-center gap-2">
        <Button size="icon" variant="ghost" aria-label="Previous page" disabled={page <= 1} onClick={() => onPage(page - 1)}><ChevronLeft /></Button>
        <span className="tnum">Page {page} of {pages}</span>
        <Button size="icon" variant="ghost" aria-label="Next page" disabled={page >= pages} onClick={() => onPage(page + 1)}><ChevronRight /></Button>
      </div>
    </div>
  )
}

export default function Audit() {
  const [pid, setPid] = useState('')
  const [debounced, setDebounced] = useState('')
  const [page, setPage] = useState(1)
  useEffect(() => { const t = setTimeout(() => { setDebounced(pid); setPage(1) }, 300); return () => clearTimeout(t) }, [pid])
  const params = { passenger_id: Number(debounced) || undefined, page }
  const q = useQuery({ queryKey: [...qk.ops.audit, params], queryFn: () => opsApi.audit(params), placeholderData: (p) => p, staleTime: 3_000 })
  return (
    <div className="mt-4 grid gap-4">
      <div className="max-w-xs"><Input aria-label="Filter by passenger ID" inputMode="numeric" placeholder="Filter by passenger ID" value={pid} onChange={(e) => setPid(e.target.value.replace(/\D/g, ''))} /></div>
      {q.isLoading ? <SkeletonBlocks rows={5} rowClass="h-10" /> : q.isError ? <ErrorState onRetry={() => q.refetch()} /> : q.data!.items.length === 0 ? <EmptyState title="No audit entries" /> : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[820px] text-[14px]">
            <caption className="sr-only">Audit log</caption>
            <thead className="text-left text-[11px] uppercase tracking-[0.06em] text-muted"><tr><th className="py-2 pr-4 font-normal">Time</th><th className="pr-4 font-normal">Actor</th><th className="pr-4 font-normal">Action</th><th className="pr-4 font-normal">Entity</th><th className="font-normal">Explanation</th></tr></thead>
            <tbody>
              {q.data!.items.map((r) => (
                <tr key={r.id} className="border-t border-line align-top">
                  <td className="tnum whitespace-nowrap py-2.5 pr-4 text-muted">{fmtDateTime(r.created_at)}</td>
                  <td className="pr-4"><Pill tone={r.actor === 'operator' ? 'info' : r.actor === 'passenger' ? 'neutral' : 'warning'} size="sm">{r.actor}</Pill></td>
                  <td className="pr-4">{r.action}</td>
                  <td className="tnum whitespace-nowrap pr-4 text-muted">{r.entity_type}{r.entity_id != null ? ` #${r.entity_id}` : ''}</td>
                  <td>{r.explanation}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {q.data && <Pager page={page} total={q.data.total} size={q.data.page_size} onPage={setPage} />}
    </div>
  )
}
