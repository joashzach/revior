import { useQueryClient } from '@tanstack/react-query'
import * as m from 'motion/react-m'
import { Dices } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { authApi } from '@/api/endpoints'
import { toastError } from '@/api/errors'
import { qk } from '@/api/queryKeys'
import type { Persona } from '@/api/types'
import { EmptyState, ErrorState, SkeletonBlocks } from '@/components/common/primitives'
import { NeedChips } from '@/components/common/domain'
import { Pill } from '@/components/common/StatusPill'
import { Button } from '@/components/ui/button'
import { S } from '@/config/strings'
import { useCompleteLogin } from '@/hooks/useCompleteLogin'
import { usePersonas, useHealthSync } from '@/hooks/queries'
import { cn } from '@/lib/utils'

function PersonaCard({ p, busy, onPick }: { p: Persona; busy: boolean; onPick: () => void }) {
  return (
    <m.li initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.2 }}>
      <button
        type="button"
        disabled={p.is_taken || busy}
        onClick={onPick}
        className={cn(
          'press grid h-full w-full gap-3 rounded-card-sm border p-5 text-left transition-[border-color,background-color] duration-150 sm:p-6',
          p.is_taken ? 'cursor-not-allowed border-line bg-ink/[0.03] opacity-60' : 'border-line hover:border-accent hover:bg-accent-subtle',
        )}
      >
        <div className="flex items-start justify-between gap-3">
          <span className="grid size-12 place-items-center rounded-full border border-line bg-bg text-[26px] leading-none" aria-hidden>{p.emoji}</span>
          {p.is_taken && <Pill tone="neutral" size="sm">{S.common.taken}</Pill>}
        </div>
        <div className="grid gap-1.5">
          <h2 className="text-[24px] leading-tight">{p.title}</h2>
          <p className="text-[14px] text-muted">{p.summary}</p>
        </div>
        <p className="text-[13px] text-faint">To {p.destination.name}{p.party_size > 1 ? ` · party of ${p.party_size}` : ''}</p>
        <NeedChips needs={p.needs} />
      </button>
    </m.li>
  )
}

export default function DemoJoin() {
  useHealthSync()
  const qc = useQueryClient()
  const complete = useCompleteLogin()
  const [busy, setBusy] = useState(false)
  const q = usePersonas(3000) // P-1.5: refresh every 3 s while open
  const claim = async (body: { persona_id?: number; surprise?: boolean }) => {
    setBusy(true)
    try {
      const r = await authApi.demoClaim(body)
      complete(r.token, r.passenger)
    } catch (e) {
      const ui = toastError(e)
      if (ui.refetch === 'personas') qc.invalidateQueries({ queryKey: qk.personas })
    } finally {
      setBusy(false)
    }
  }
  const items = q.data?.items ?? []
  return (
    <div className="grid gap-8 pt-4">
      <div className="grid gap-4 lg:grid-cols-[1fr_auto] lg:items-end">
        <div className="grid max-w-[34ch] gap-3 sm:max-w-[40ch]">
          <span className="eyebrow rise">Live demo</span>
          <h1 className="rise rise-1 text-[clamp(2.4rem,1.4rem+3.4vw,4rem)] leading-[1.04]">{S.persona.title}</h1>
        </div>
        <div className="rise rise-2 flex flex-wrap items-center gap-3">
          <Button variant="primary" size="lg" loading={busy} onClick={() => claim({ surprise: true })}><Dices /> {S.persona.surprise}</Button>
        </div>
      </div>
      <p className="rise rise-2 max-w-[60ch] text-muted">{S.persona.sub}</p>
      {q.isLoading ? (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"><SkeletonBlocks rows={6} className="contents" rowClass="h-52" /></ul>
      ) : q.isError ? (
        <ErrorState title="We couldn't load the personas" onRetry={() => q.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState title="No personas free" body={S.persona.empty} action={<Button variant="primary" onClick={() => claim({ surprise: true })}>{S.persona.surprise}</Button>} />
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((p) => <PersonaCard key={p.id} p={p} busy={busy} onPick={() => claim({ persona_id: p.id })} />)}
        </ul>
      )}
      <p className="text-[14px] text-muted">
        <Link to="/join" className="underline decoration-line underline-offset-4 hover:decoration-ink">{S.persona.register}</Link>
      </p>
    </div>
  )
}
