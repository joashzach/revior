import { useQuery } from '@tanstack/react-query'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { opsApi } from '@/api/endpoints'
import { qk } from '@/api/queryKeys'
import { ErrorState, SkeletonBlocks } from '@/components/common/primitives'

const axis = { stroke: 'var(--text-muted)', fontSize: 12, fontFamily: 'var(--font-mono)' } as const
const tip = { contentStyle: { background: 'var(--surface-inverse)', color: 'var(--on-inverse)', border: 0, borderRadius: 12, fontFamily: 'var(--font-mono)', fontSize: 12 }, cursor: { fill: 'var(--surface-2)' } }

function Card({ title, caption, children }: { title: string; caption?: string; children: React.ReactNode }) {
  return <section className="grid gap-3 rounded-card-sm border border-line p-5"><div><h3 className="text-[22px] leading-tight">{title}</h3>{caption && <p className="text-[12px] text-muted">{caption}</p>}</div><div className="h-60">{children}</div></section>
}

export default function Fairness() {
  const q = useQuery({ queryKey: qk.ops.fairness, queryFn: opsApi.fairness, staleTime: 5_000 })
  if (q.isLoading) return <SkeletonBlocks rows={2} rowClass="h-64" className="mt-4" />
  if (q.isError || !q.data) return <ErrorState onRetry={() => q.refetch()} />
  const f = q.data
  const cls = f.by_needs_class.map((c) => ({ name: c.needs_class, rate: Math.round(c.placement_rate * 100), p50: c.wait_p50, p90: c.wait_p90 }))
  const dest = f.by_destination.map((d) => ({ name: d.destination.name, rate: Math.round(d.placement_rate * 100) }))
  return (
    <div className="mt-4 grid gap-4 lg:grid-cols-2">
      <Card title="Placement rate by needs class" caption="Percent of each group with a seat or place">
        <ResponsiveContainer><BarChart data={cls}><CartesianGrid stroke="var(--border)" vertical={false} /><XAxis dataKey="name" {...axis} /><YAxis domain={[0, 100]} unit="%" {...axis} /><Tooltip {...tip} /><Bar dataKey="rate" name="Placed" fill="var(--surface-inverse)" radius={[8, 8, 0, 0]} /></BarChart></ResponsiveContainer>
      </Card>
      <Card title="Wait time by needs class" caption="Minutes: median (p50) and 90th percentile">
        <ResponsiveContainer><BarChart data={cls}><CartesianGrid stroke="var(--border)" vertical={false} /><XAxis dataKey="name" {...axis} /><YAxis {...axis} /><Tooltip {...tip} /><Legend wrapperStyle={{ fontSize: 12, fontFamily: 'var(--font-mono)' }} /><Bar dataKey="p50" name="p50" fill="var(--info)" radius={[8, 8, 0, 0]} /><Bar dataKey="p90" name="p90" fill="var(--warning)" radius={[8, 8, 0, 0]} /></BarChart></ResponsiveContainer>
      </Card>
      <Card title="Placement by destination">
        <ResponsiveContainer><BarChart data={dest}><CartesianGrid stroke="var(--border)" vertical={false} /><XAxis dataKey="name" {...axis} interval={0} angle={-20} textAnchor="end" height={54} /><YAxis domain={[0, 100]} unit="%" {...axis} /><Tooltip {...tip} /><Bar dataKey="rate" name="Placed" fill="var(--success)" radius={[8, 8, 0, 0]} /></BarChart></ResponsiveContainer>
      </Card>
      <section className="grid content-center justify-items-start gap-2 rounded-card-sm bg-surface-2 p-8 text-info-fg">
        <span className="eyebrow !text-info-fg">Wait-time Gini</span>
        <span className="tnum font-serif text-[clamp(4rem,3rem+4vw,6rem)] leading-none">{f.wait_gini.toFixed(2)}</span>
        <p className="text-[14px]">Lower is fairer. 0 means everyone waited the same.</p>
      </section>
    </div>
  )
}
