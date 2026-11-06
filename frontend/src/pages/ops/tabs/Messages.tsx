import { useQuery } from '@tanstack/react-query'
import { Bell, Mail, MessageSquare } from 'lucide-react'
import { useState } from 'react'
import { opsApi } from '@/api/endpoints'
import { qk } from '@/api/queryKeys'
import { EmptyState, ErrorState, SkeletonBlocks } from '@/components/common/primitives'
import { Pill } from '@/components/common/StatusPill'
import { fmtDateTime } from '@/lib/utils'
import { Pager } from './Audit'

const CH = { push: { icon: Bell, label: 'Push' }, email_sim: { icon: Mail, label: 'Email (simulated)' }, sms_sim: { icon: MessageSquare, label: 'SMS (simulated)' } } as const

export default function Messages() {
  const [page, setPage] = useState(1)
  const q = useQuery({ queryKey: [...qk.ops.messages, page], queryFn: () => opsApi.messages(page), placeholderData: (p) => p, staleTime: 3_000 })
  if (q.isLoading) return <SkeletonBlocks rows={5} rowClass="h-10" className="mt-4" />
  if (q.isError || !q.data) return <ErrorState onRetry={() => q.refetch()} />
  if (!q.data.items.length) return <EmptyState title="No messages sent yet" />
  return (
    <div className="mt-4 grid gap-4">
      <ul className="grid gap-2">
        {q.data.items.map((m, i) => {
          const c = CH[m.channel]
          return (
            <li key={`${m.created_at}-${i}`} className="grid gap-1 rounded-panel border border-line p-3 text-[14px] sm:grid-cols-[170px_190px_1fr] sm:items-center sm:gap-4">
              <span className="tnum text-[12px] text-muted">{fmtDateTime(m.created_at)}</span>
              <span className="flex items-center gap-2"><Pill tone="neutral" icon={c.icon} size="sm">{c.label}</Pill></span>
              <span><span className="font-medium">{m.passenger_name}</span> <span className="text-muted">{m.body}</span></span>
            </li>
          )
        })}
      </ul>
      <Pager page={page} total={q.data.total} size={q.data.page_size} onPage={setPage} />
    </div>
  )
}
