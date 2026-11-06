import { Link } from 'react-router-dom'
import { ScoreBars } from '@/components/common/domain'
import { EmptyState, ErrorState, NumberRoll, SkeletonBlocks } from '@/components/common/primitives'
import { buttonVariants } from '@/components/ui/button'
import { S } from '@/config/strings'
import { useWhy } from '@/hooks/queries'

export default function Why() {
  const q = useWhy()
  if (q.isLoading) return <SkeletonBlocks rows={2} rowClass="h-56" />
  if (q.isError || !q.data) {
    const notReady = (q.error as { status?: number } | null)?.status === 404
    return notReady ? (
      <EmptyState
        title="No result to explain yet"
        body="Once you have been placed, this page shows exactly how your priority was worked out."
        action={<Link to="/status" className={buttonVariants({ variant: 'dark', size: 'sm' })}>Go to status</Link>}
      />
    ) : (
      <ErrorState title="We couldn't load the explanation" onRetry={() => q.refetch()} />
    )
  }
  const w = q.data
  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_360px]">
      <div className="grid content-start gap-6">
        <div className="grid gap-2">
          <span className="eyebrow rise">Transparency</span>
          <h1 className="rise rise-1 text-[clamp(2.2rem,1.4rem+3vw,3.5rem)] leading-[1.05]">{S.why.title}</h1>
        </div>
        <section className="rise rise-2 grid gap-6 rounded-card-sm border border-line p-6 sm:p-8" aria-label="Score breakdown">
          <div className="flex items-end justify-between gap-4">
            <div className="grid">
              <span className="eyebrow">{S.why.score}</span>
              <span className="tnum font-serif text-[clamp(4rem,3rem+4vw,6rem)] leading-none"><NumberRoll value={Math.round(w.score)} /></span>
            </div>
            <span className="rounded-full border border-line px-3 py-1 text-[12px] uppercase tracking-[0.06em] text-muted">{S.why.rules(w.rule_version)}</span>
          </div>
          <ScoreBars breakdown={w.breakdown} weights={w.weights} />
        </section>
        <section className="rise rise-3 grid gap-3 rounded-card-sm border border-line p-6 sm:p-8" aria-label="Explanation">
          <p className="text-[15px]">{w.explanation}</p>
          {w.decision_explanation && <p className="text-[15px] text-muted">{w.decision_explanation}</p>}
        </section>
        {w.waitlist.length > 0 && (
          <section className="grid gap-3 rounded-card-sm border border-line p-6 sm:p-8" aria-label="Waitlist positions">
            <span className="eyebrow">Waitlist</span>
            <ul className="grid gap-2">
              {w.waitlist.map((x) => (
                <li key={x.service_id} className="flex justify-between gap-3 text-[14px]"><span>{x.label}</span><span className="tnum">#{x.position} of {x.total}</span></li>
              ))}
            </ul>
          </section>
        )}
        <p className="text-[14px] text-muted">{S.why.footer}</p>
      </div>
      <aside className="grid content-start gap-3 rounded-card-sm border border-line p-6" aria-label="Rule weights">
        <span className="eyebrow">Maximum points per factor</span>
        <table className="w-full text-[14px]">
          <caption className="sr-only">Weights in rules version {w.rule_version}</caption>
          <tbody>
            {Object.entries(w.weights).map(([k, v]) => (
              <tr key={k} className="border-t border-line first:border-0">
                <th scope="row" className="py-2 text-left font-normal text-muted">{S.why.features[k as keyof typeof S.why.features] ?? k}</th>
                <td className="tnum py-2 text-right">{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </aside>
    </div>
  )
}
