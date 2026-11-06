import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { opsApi } from '@/api/endpoints'
import { toastError } from '@/api/errors'
import { qk } from '@/api/queryKeys'
import type { RulesPreview } from '@/api/types'
import { ErrorState, SkeletonBlocks } from '@/components/common/primitives'
import { Button } from '@/components/ui/button'
import { Input, Slider } from '@/components/ui/form'
import { ConfirmDialog } from '@/components/ui/overlays'
import { S } from '@/config/strings'
import { fmtDateTime, fmtPct } from '@/lib/utils'

const KEYS = ['medical', 'wheelchair', 'elderly', 'with_children', 'deadline_urgency', 'wait_time'] as const

export default function Rules() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: qk.ops.rules, queryFn: opsApi.rules, staleTime: 5_000 })
  const active = q.data?.active.weights
  const [w, setW] = useState<Record<string, number>>({})
  const [preview, setPreview] = useState<RulesPreview | null>(null)
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)
  useEffect(() => { if (active) setW({ ...active }) }, [active])
  const dirty = useMemo(() => !!active && KEYS.some((k) => (w[k] ?? 0) !== (active[k] ?? 0)), [w, active])
  if (q.isLoading) return <SkeletonBlocks rows={4} rowClass="h-12" className="mt-4" />
  if (q.isError || !q.data) return <ErrorState onRetry={() => q.refetch()} />
  const set = (k: string, v: number) => { setW({ ...w, [k]: Math.max(0, Math.min(50, Number.isFinite(v) ? v : 0)) }); setPreview(null) }
  const runPreview = async () => { setBusy(true); try { setPreview(await opsApi.rulesPreview(w)) } catch (e) { toastError(e) } finally { setBusy(false) } }
  const apply = async () => {
    setBusy(true)
    try { const r = await opsApi.rulesApply(w); toast.success(`Rules v${r.version} applied`); setPreview(null); setConfirm(false); qc.invalidateQueries({ queryKey: qk.ops.rules }); qc.invalidateQueries({ queryKey: qk.why }) } catch (e) { toastError(e) } finally { setBusy(false) }
  }
  return (
    <div className="mt-4 grid gap-6 xl:grid-cols-[1.1fr_1fr]">
      <section className="grid content-start gap-4" aria-label="Weights">
        <div className="flex items-center justify-between"><span className="eyebrow">{S.why.rules(q.data.active.version)}</span><span className="text-[12px] text-muted">Ticket price is never a factor.</span></div>
        <ul className="grid gap-4">
          {KEYS.map((k) => {
            const cur = active?.[k] ?? 0
            const changed = (w[k] ?? 0) !== cur
            return (
              <li key={k} className="grid gap-2">
                <div className="flex items-center justify-between gap-3 text-[14px]">
                  <label htmlFor={`w-${k}`}>{S.why.features[k]}</label>
                  <span className="flex items-center gap-2"><span className="tnum text-faint">now {cur}</span>
                    <Input id={`w-${k}`} type="number" inputMode="numeric" min={0} max={50} value={w[k] ?? 0} onChange={(e) => set(k, Number(e.target.value))} className={`h-9 w-20 text-right ${changed ? 'border-accent' : ''}`} /></span>
                </div>
                <Slider value={[w[k] ?? 0]} min={0} max={50} step={1} onValueChange={([v]) => set(k, v)} aria-label={S.why.features[k]} />
              </li>
            )
          })}
        </ul>
        <div className="flex flex-wrap gap-2">
          <Button variant="dark" size="sm" disabled={!dirty} loading={busy && !confirm} onClick={runPreview}>Preview</Button>
          <Button variant="primary" size="sm" disabled={!dirty || !preview} onClick={() => setConfirm(true)}>Apply</Button>
          <Button variant="ghost" size="sm" disabled={!dirty} onClick={() => { setW({ ...active! }); setPreview(null) }}>Reset edits</Button>
        </div>
        <div className="grid gap-2 border-t border-line pt-4">
          <span className="eyebrow">History</span>
          <ul className="grid gap-1 text-[13px]">{q.data.history.map((h) => <li key={h.version} className="flex justify-between"><span>v{h.version}</span><span className="tnum text-muted">{fmtDateTime(h.created_at)}</span></li>)}</ul>
        </div>
      </section>
      <section className="grid content-start gap-4 rounded-card-sm border border-line p-5" aria-label="Preview of changes" aria-live="polite">
        <span className="eyebrow">Preview</span>
        {!preview ? <p className="text-[14px] text-muted">Change a weight and press Preview to see who would move.</p> : (
          <>
            <p className="tnum font-serif text-[40px] leading-none">{preview.placed_delta > 0 ? '+' : ''}{preview.placed_delta}<span className="ml-2 font-mono text-[13px]">placed</span></p>
            <table className="w-full text-[13px]"><thead className="text-left text-[11px] uppercase tracking-[0.06em] text-muted"><tr><th className="py-1 font-normal">Needs class</th><th className="font-normal">Placement rate</th></tr></thead>
              <tbody>{preview.by_needs_class.map((c) => <tr key={c.needs_class} className="border-t border-line"><th scope="row" className="py-2 text-left font-normal capitalize">{c.needs_class}</th><td className="tnum">{fmtPct(c.placement_rate_before)} → {fmtPct(c.placement_rate_after)}</td></tr>)}</tbody></table>
            <div className="grid gap-1"><span className="eyebrow">Top movers</span>
              <ul className="grid gap-1 text-[13px]">{preview.movers.slice(0, 6).map((m) => <li key={m.passenger_id} className="flex justify-between gap-3"><span className="truncate">{m.name} · {m.service_label}</span><span className="tnum">#{m.position_before} → #{m.position_after}</span></li>)}</ul></div>
          </>
        )}
      </section>
      <ConfirmDialog open={confirm} onOpenChange={setConfirm} title="Apply new priority rules?" description="This creates a new rules version. It affects every future allocation run." confirmLabel="Apply rules" loading={busy} onConfirm={apply} />
    </div>
  )
}
