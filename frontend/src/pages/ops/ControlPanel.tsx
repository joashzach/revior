import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, Play, Plus, Square, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { opsApi } from '@/api/endpoints'
import { toastError } from '@/api/errors'
import { qk } from '@/api/queryKeys'
import type { DisruptionType } from '@/api/types'
import { Pill } from '@/components/common/StatusPill'
import { NumberRoll } from '@/components/common/primitives'
import { Button } from '@/components/ui/button'
import { Field, Input } from '@/components/ui/form'
import { Select, Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/overlays'
import { fmtTime } from '@/lib/utils'
import { useLiveStore } from '@/realtime/useRealtime'

export interface Prefill { edgeId?: number; openCapacity?: boolean; nonce: number }

function Disruptions({ prefill }: { prefill: Prefill | null }) {
  const qc = useQueryClient()
  const [type, setType] = useState<DisruptionType>('cancellation')
  const [serviceId, setServiceId] = useState<string>('')
  const [edgeId, setEdgeId] = useState<string>('')
  const [minutes, setMinutes] = useState('30')
  const [reason, setReason] = useState('')
  const [filter, setFilter] = useState('')
  const [preview, setPreview] = useState<{ affected_count: number; by_destination: { destination: { name: string }; count: number }[] } | null>(null)
  const [busy, setBusy] = useState(false)
  const services = useQuery({ queryKey: qk.ops.services, queryFn: () => opsApi.services(), staleTime: 10_000 })
  const map = useQuery({ queryKey: qk.ops.map, queryFn: opsApi.map, staleTime: 10_000 })
  const list = useQuery({ queryKey: qk.ops.disruptions, queryFn: opsApi.disruptions })

  const roads = useMemo(() => (map.data?.edges ?? []).filter((e) => e.mode === 'road' && !e.is_closed), [map.data])
  const nodeName = useMemo(() => new Map((map.data?.nodes ?? []).map((n) => [n.id, n.name])), [map.data])
  const svcOptions = (services.data?.items ?? []).filter((s) => s.status !== 'cancelled' && s.label.toLowerCase().includes(filter.toLowerCase())).map((s) => ({ value: String(s.id), label: `${s.label} · ${fmtTime(s.depart_at)}` }))
  const edgeOptions = roads.map((e) => ({ value: String(e.id), label: `${e.road_name ?? 'Road'}: ${nodeName.get(e.from_node_id) ?? '?'} → ${nodeName.get(e.to_node_id) ?? '?'}` }))

  const query = () => ({ type, service_id: type !== 'closure' ? Number(serviceId) || undefined : undefined, edge_id: type === 'closure' ? Number(edgeId) || undefined : undefined, delay_minutes: type === 'delay' ? Number(minutes) || undefined : undefined })
  const valid = type === 'closure' ? !!edgeId : !!serviceId && (type !== 'delay' || Number(minutes) > 0)
  const runPreview = async () => { try { setPreview(await opsApi.disruptionPreview(query())) } catch (e) { toastError(e) } }

  useEffect(() => { // edge click on the map pre-fills a closure and previews it
    if (!prefill?.edgeId) return
    setType('closure'); setEdgeId(String(prefill.edgeId)); setPreview(null)
    opsApi.disruptionPreview({ type: 'closure', edge_id: prefill.edgeId }).then(setPreview).catch(toastError)
  }, [prefill])

  const confirm = async () => {
    setBusy(true)
    try {
      const r = await opsApi.createDisruption({ ...query(), reason: reason.trim() || (type === 'closure' ? 'Road closed' : type === 'delay' ? 'Delay' : 'Service cancelled') })
      toast.success(`Disruption created. ${r.affected_count} passengers affected`, { id: 'disruption', description: r.batch ? undefined : 'No request window opened' })
      setPreview(null); setReason(''); setServiceId(''); setEdgeId('')
      for (const k of [qk.ops.map, qk.ops.services, qk.ops.disruptions, qk.ops.kpis]) qc.invalidateQueries({ queryKey: k })
    } catch (e) { toastError(e) } finally { setBusy(false) }
  }
  const resolve = async (id: number) => { try { await opsApi.resolveDisruption(id); toast('Disruption resolved'); for (const k of [qk.ops.map, qk.ops.disruptions, qk.ops.services]) qc.invalidateQueries({ queryKey: k }) } catch (e) { toastError(e) } }

  return (
    <div className="grid gap-4">
      <div role="radiogroup" aria-label="Disruption type" className="flex rounded-full border border-line p-0.5 text-[12px] uppercase tracking-[0.06em]">
        {([['cancellation', 'Cancel'], ['delay', 'Delay'], ['closure', 'Close edge']] as const).map(([v, l]) => (
          <button key={v} type="button" role="radio" aria-checked={type === v} onClick={() => { setType(v); setPreview(null) }} className={`press min-h-9 flex-1 rounded-full px-3 ${type === v ? 'bg-ink text-bg' : 'text-muted hover:text-ink'}`}>{l}</button>
        ))}
      </div>
      {type !== 'closure' ? (
        <div className="grid gap-3">
          <Field label="Find a service">{(id) => <Input id={id} value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Type to filter" />}</Field>
          <Select label="Service" value={serviceId || undefined} onValueChange={(v) => { setServiceId(v); setPreview(null) }} options={svcOptions} placeholder={`Choose a service (${svcOptions.length})`} />
          {type === 'delay' && <Field label="Delay (minutes)">{(id) => <Input id={id} type="number" inputMode="numeric" min={1} value={minutes} onChange={(e) => setMinutes(e.target.value)} />}</Field>}
        </div>
      ) : (
        <Select label="Road" value={edgeId || undefined} onValueChange={(v) => { setEdgeId(v); setPreview(null) }} options={edgeOptions} placeholder="Choose a road, or click one on the map" />
      )}
      <Field label="Reason">{(id) => <Input id={id} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Shown to passengers" />}</Field>
      <div className="flex flex-wrap gap-2">
        <Button variant="dark" size="sm" disabled={!valid} onClick={runPreview}>Preview</Button>
        <Button variant="primary" size="sm" disabled={!valid || !preview} loading={busy} onClick={confirm}>Confirm</Button>
      </div>
      {preview && (
        <div className="grid gap-2 rounded-panel bg-surface-2 p-4 text-info-fg" role="status">
          <p className="tnum font-serif text-[28px] leading-none"><NumberRoll value={preview.affected_count} /> <span className="font-mono text-[13px]">passengers affected</span></p>
          <ul className="grid gap-0.5 text-[13px]">{preview.by_destination.map((d) => <li key={d.destination.name} className="flex justify-between"><span>{d.destination.name}</span><span className="tnum">{d.count}</span></li>)}</ul>
        </div>
      )}
      <div className="grid gap-2 border-t border-line pt-4">
        <span className="eyebrow">Active disruptions</span>
        {(list.data?.items ?? []).filter((d) => !d.resolved_at).length === 0 && <p className="text-[13px] text-muted">None right now.</p>}
        <ul className="grid gap-2">
          {(list.data?.items ?? []).filter((d) => !d.resolved_at).map((d) => (
            <li key={d.id} className="flex items-center gap-3 rounded-panel border border-line p-3 text-[13px]">
              <Pill tone={d.type === 'delay' ? 'warning' : 'danger'} size="sm">{d.type}</Pill>
              <span className="min-w-0 flex-1 truncate">{d.target_label}</span>
              <span className="tnum text-muted">{d.affected_count}</span>
              <Button size="xs" variant="ghost" onClick={() => resolve(d.id)}>Resolve</Button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

function Allocation({ batchOpen }: { batchOpen: boolean }) {
  const qc = useQueryClient()
  // TODO(contract): the backend does not report whether OR-Tools is installed, so only greedy is offered.
  const mode = 'greedy' as const
  const stats = useLiveStore((s) => s.lastRun)
  const setStats = useLiveStore((s) => s.setLastRun)
  const [busy, setBusy] = useState<'run' | 'close' | null>(null)
  const batch = useQuery({ queryKey: qk.ops.batch, queryFn: opsApi.batchCurrent, refetchInterval: 4_000 })
  const refresh = () => { for (const k of [qk.ops.kpis, qk.ops.batch, qk.ops.capacity, qk.ops.allocations, qk.ops.unresolved, qk.ops.clusters, qk.ops.map]) qc.invalidateQueries({ queryKey: k }) }
  const close = async () => { setBusy('close'); try { await opsApi.closeBatch(); toast('Batch closed'); refresh() } catch (e) { toastError(e) } finally { setBusy(null) } }
  const run = async () => { setBusy('run'); try { const r = await opsApi.runAllocation(mode); setStats(r.stats); toast.success(`Allocation done in ${r.stats.duration_ms} ms`, { id: 'alloc' }); refresh() } catch (e) { toastError(e) } finally { setBusy(null) } }
  const b = batch.data?.batch
  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between gap-3 rounded-panel border border-line p-4">
        <div className="grid gap-0.5"><span className="eyebrow">Batch</span><span className="text-[15px]">{b || batchOpen ? 'Window open' : 'No request window'}</span></div>
        <div className="text-right"><span className="tnum font-serif text-[36px] leading-none"><NumberRoll value={batch.data?.request_count ?? 0} /></span><span className="block text-[11px] uppercase tracking-[0.06em] text-muted">requests</span></div>
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <Button variant="dark" size="sm" disabled={!b} loading={busy === 'close'} onClick={close}><Square /> Close batch now</Button>
        <Button variant="primary" size="sm" loading={busy === 'run'} onClick={run}><Play /> Run allocation</Button>
      </div>
      {stats && (
        <dl className="grid grid-cols-3 gap-3 rounded-panel bg-surface-2 p-4 text-info-fg" aria-label="Last run">
          {([['Placed 1st', stats.placed_choice1], ['Placed 2nd', stats.placed_choice2], ['Auto', stats.placed_auto], ['Waitlisted', stats.waitlisted], ['Unresolved', stats.unresolved], ['ms', stats.duration_ms]] as const).map(([l, v]) => (
            <div key={l}><dt className="text-[10px] uppercase tracking-[0.06em]">{l}</dt><dd className="tnum font-serif text-[28px] leading-none">{v}</dd></div>
          ))}
        </dl>
      )}
    </div>
  )
}

function AddCapacity({ prefill }: { prefill: Prefill | null }) {
  const qc = useQueryClient()
  const map = useQuery({ queryKey: qk.ops.map, queryFn: opsApi.map, staleTime: 30_000 })
  const [label, setLabel] = useState('Charter Potheri → Tambaram')
  const [mode, setMode] = useState<'charter_bus' | 'shuttle'>('charter_bus')
  const [stops, setStops] = useState<number[]>([])
  const [pick, setPick] = useState('')
  const [depart, setDepart] = useState('15')
  const [seats, setSeats] = useState('40')
  const [acc, setAcc] = useState('4')
  const [busy, setBusy] = useState(false)
  const nodes = map.data?.nodes ?? []
  const name = (id: number) => nodes.find((n) => n.id === id)?.name ?? '?'
  useEffect(() => { if (prefill?.openCapacity) document.getElementById('add-capacity')?.scrollIntoView({ block: 'nearest' }) }, [prefill])
  const move = (i: number, d: -1 | 1) => setStops((s) => { const n = [...s]; const j = i + d; if (j < 0 || j >= n.length) return s; [n[i], n[j]] = [n[j], n[i]]; return n })
  const valid = label.trim() && stops.length >= 2 && Number(seats) > 0 && Number(depart) >= 0 && Number(acc) <= Number(seats)
  const submit = async () => {
    setBusy(true)
    try {
      await opsApi.addService({ label: label.trim(), mode, stop_node_ids: stops, depart_in_minutes: Number(depart), total_seats: Number(seats), accessible_seats: Number(acc) })
      toast.success('Capacity added. Re-allocating…')
      for (const k of [qk.ops.services, qk.ops.capacity, qk.ops.map, qk.ops.kpis, qk.ops.unresolved]) qc.invalidateQueries({ queryKey: k })
      setStops([])
    } catch (e) { toastError(e) } finally { setBusy(false) }
  }
  return (
    <div id="add-capacity" className="grid gap-3">
      <Field label="Label">{(id) => <Input id={id} value={label} onChange={(e) => setLabel(e.target.value)} />}</Field>
      <Select label="Vehicle type" value={mode} onValueChange={(v) => setMode(v as 'charter_bus')} options={[{ value: 'charter_bus', label: 'Charter bus' }, { value: 'shuttle', label: 'Shuttle' }]} />
      <div className="grid gap-2">
        <span className="text-[14px] font-medium">Stops, in order</span>
        <ol className="grid gap-1.5">
          {stops.map((s, i) => (
            <li key={`${s}-${i}`} className="flex items-center gap-2 rounded-panel border border-line px-3 py-1.5 text-[13px]">
              <span className="tnum w-5 text-faint">{i + 1}</span><span className="flex-1">{name(s)}</span>
              <Button size="icon" variant="quiet" aria-label={`Move ${name(s)} up`} disabled={i === 0} onClick={() => move(i, -1)}><ArrowUp /></Button>
              <Button size="icon" variant="quiet" aria-label={`Move ${name(s)} down`} disabled={i === stops.length - 1} onClick={() => move(i, 1)}><ArrowDown /></Button>
              <Button size="icon" variant="quiet" aria-label={`Remove ${name(s)}`} onClick={() => setStops(stops.filter((_, j) => j !== i))}><Trash2 /></Button>
            </li>
          ))}
        </ol>
        <div className="flex items-end gap-2">
          <div className="flex-1"><Select label="Add stop" value={pick || undefined} onValueChange={setPick} options={nodes.map((n) => ({ value: String(n.id), label: n.name }))} placeholder="Choose a stop" /></div>
          <Button size="sm" variant="dark" disabled={!pick} onClick={() => { setStops([...stops, Number(pick)]); setPick('') }}><Plus /> Add</Button>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-2">
        <Field label="Departs in (min)">{(id) => <Input id={id} type="number" inputMode="numeric" min={0} value={depart} onChange={(e) => setDepart(e.target.value)} />}</Field>
        <Field label="Seats">{(id) => <Input id={id} type="number" inputMode="numeric" min={1} value={seats} onChange={(e) => setSeats(e.target.value)} />}</Field>
        <Field label="Accessible">{(id) => <Input id={id} type="number" inputMode="numeric" min={0} value={acc} onChange={(e) => setAcc(e.target.value)} />}</Field>
      </div>
      <Button variant="primary" disabled={!valid} loading={busy} onClick={submit}>Add capacity</Button>
    </div>
  )
}

export function ControlPanel({ prefill, batchOpen }: { slug: string; prefill: Prefill | null; batchOpen: boolean }) {
  const [tab, setTab] = useState('disruptions')
  useEffect(() => { if (prefill?.edgeId) setTab('disruptions'); else if (prefill?.openCapacity) setTab('capacity') }, [prefill])
  return (
    <section aria-label="Control panel" className="rounded-card-sm border border-line p-5">
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList aria-label="Controls">
          <TabsTrigger value="disruptions">Disruptions</TabsTrigger>
          <TabsTrigger value="allocation">Allocate</TabsTrigger>
          <TabsTrigger value="capacity">Add capacity</TabsTrigger>
        </TabsList>
        <div className="mt-4">
          <TabsContent value="disruptions"><Disruptions prefill={prefill} /></TabsContent>
          <TabsContent value="allocation"><Allocation batchOpen={batchOpen} /></TabsContent>
          <TabsContent value="capacity"><AddCapacity prefill={prefill} /></TabsContent>
        </div>
      </Tabs>
    </section>
  )
}
