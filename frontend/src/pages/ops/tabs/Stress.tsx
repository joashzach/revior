import { Check, Play, X } from 'lucide-react'
import { useState } from 'react'
import { opsApi } from '@/api/endpoints'
import { toastError } from '@/api/errors'
import { NumberRoll } from '@/components/common/primitives'
import { Button } from '@/components/ui/button'
import { Field, Input } from '@/components/ui/form'
import { useLiveStore } from '@/realtime/useRealtime'

export default function Stress() {
  const [requests, setRequests] = useState('1000')
  const [seats, setSeats] = useState('10')
  const { running, progress, result } = useLiveStore((s) => s.stress)
  const setStress = useLiveStore((s) => s.setStress)
  const run = async () => {
    setStress({ running: true, progress: { sent: 0, ok: 0, conflicts: 0, errors: 0 }, result: null })
    try { await opsApi.stressRun(Number(requests), Number(seats)) } catch (e) { setStress({ running: false }); toastError(e) }
  }
  const valid = Number(requests) >= 1 && Number(seats) >= 1
  return (
    <div className="mt-4 grid gap-6 lg:grid-cols-[320px_1fr]">
      <section className="grid content-start gap-4 rounded-card-sm border border-line p-5" aria-label="Stress test settings">
        <p className="text-[13px] text-muted">Fires simultaneous seat claims at a throw-away service and checks the database never over-allocates.</p>
        <Field label="Requests">{(id) => <Input id={id} type="number" inputMode="numeric" min={1} max={5000} value={requests} onChange={(e) => setRequests(e.target.value)} disabled={running} />}</Field>
        <Field label="Seats">{(id) => <Input id={id} type="number" inputMode="numeric" min={1} max={500} value={seats} onChange={(e) => setSeats(e.target.value)} disabled={running} />}</Field>
        <Button variant="primary" disabled={!valid} loading={running} onClick={run}><Play /> Run stress test</Button>
      </section>
      <section className="grid content-start gap-5" aria-live="polite" aria-label="Stress test results">
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {([['Sent', progress?.sent], ['Accepted', progress?.ok], ['Conflicts', progress?.conflicts], ['Errors', progress?.errors]] as const).map(([l, v]) => (
            <div key={l} className="rounded-panel border border-line p-4"><dt className="eyebrow">{l}</dt><dd className="tnum mt-1 font-serif text-[40px] leading-none"><NumberRoll value={v ?? 0} /></dd></div>
          ))}
        </dl>
        {result && (
          <div role="status" className={`grid gap-2 rounded-card-sm p-8 ${result.passed ? 'bg-success-bg text-success-fg' : 'bg-danger-bg text-danger-fg'}`}>
            <p className="flex items-center gap-3 font-serif text-[clamp(1.8rem,1.2rem+2vw,3rem)] leading-tight">{result.passed ? <Check className="size-9 shrink-0" aria-hidden /> : <X className="size-9 shrink-0" aria-hidden />}
              {result.total} requests · {result.capacity} seats · {result.over_allocations} over-allocations · {result.five_xx} errors</p>
            <p className="text-[14px]">{result.confirmed} seats were granted. {result.passed ? 'Exactly the capacity, no more.' : 'This should never happen. Check the invariants tile.'}</p>
          </div>
        )}
      </section>
    </div>
  )
}
