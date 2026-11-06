import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { toast } from 'sonner'
import { opsApi } from '@/api/endpoints'
import { toastError } from '@/api/errors'
import { qk } from '@/api/queryKeys'
import { EmptyState, ErrorState, SkeletonBlocks } from '@/components/common/primitives'
import { StatusPill } from '@/components/common/StatusPill'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/overlays'
import { fmtDateTime } from '@/lib/utils'

export default function Personas() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: qk.ops.personas, queryFn: opsApi.demoPersonas, staleTime: 2_000, refetchInterval: 5_000 })
  const [all, setAll] = useState(false)
  const [busy, setBusy] = useState<number | 'all' | null>(null)
  const refresh = () => { qc.invalidateQueries({ queryKey: qk.ops.personas }); qc.invalidateQueries({ queryKey: qk.personas }) }
  const release = async (id: number) => { setBusy(id); try { await opsApi.releasePersona(id); toast('Persona released'); refresh() } catch (e) { toastError(e) } finally { setBusy(null) } }
  const releaseAll = async () => { setBusy('all'); try { await opsApi.releaseAll(); toast('All personas released'); setAll(false); refresh() } catch (e) { toastError(e) } finally { setBusy(null) } }
  if (q.isLoading) return <SkeletonBlocks rows={4} rowClass="h-12" className="mt-4" />
  if (q.isError || !q.data) return <ErrorState onRetry={() => q.refetch()} />
  if (!q.data.items.length) return <EmptyState title="No demo personas" />
  return (
    <div className="mt-4 grid gap-4">
      <div className="flex justify-end"><Button size="sm" variant="ghost" onClick={() => setAll(true)}>Release all</Button></div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[700px] text-[14px]">
          <caption className="sr-only">Demo personas</caption>
          <thead className="text-left text-[11px] uppercase tracking-[0.06em] text-muted"><tr><th className="py-2 pr-4 font-normal">Persona</th><th className="pr-4 font-normal">Claimed</th><th className="pr-4 font-normal">State</th><th className="text-right font-normal">Action</th></tr></thead>
          <tbody>
            {q.data.items.map((p) => (
              <tr key={p.id} className="border-t border-line">
                <th scope="row" className="py-3 pr-4 text-left font-medium"><span aria-hidden>{p.emoji}</span> {p.title}</th>
                <td className="tnum pr-4 text-muted">{p.claimed_at ? fmtDateTime(p.claimed_at) : 'Free'}</td>
                <td className="pr-4"><StatusPill kind="passenger" value={p.state} size="sm" /></td>
                <td className="text-right"><Button size="xs" variant="ghost" disabled={!p.is_taken} loading={busy === p.id} onClick={() => release(p.id)}>Release</Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ConfirmDialog open={all} onOpenChange={setAll} title="Release every persona?" description="Anyone currently using a persona will lose it." confirmLabel="Release all" danger loading={busy === 'all'} onConfirm={releaseAll} />
    </div>
  )
}
