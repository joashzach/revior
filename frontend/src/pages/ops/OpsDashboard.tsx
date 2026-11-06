import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, LogOut, RotateCcw, X } from 'lucide-react'
import { lazy, Suspense, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { opsApi, publicApi } from '@/api/endpoints'
import { toastError } from '@/api/errors'
import { qk } from '@/api/queryKeys'
import { useSession } from '@/app/session'
import { ReviorLogo } from '@/components/brand/ReviorLogo'
import { ErrorBoundary, LiveDot, NumberRoll } from '@/components/common/primitives'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/form'
import { ConfirmDialog, SidePanel, Tabs, TabsContent, TabsList, TabsTrigger, Select } from '@/components/ui/overlays'
import { useCountdown } from '@/hooks/useCountdown'
import { cn } from '@/lib/utils'
import { useRealtime } from '@/realtime/useRealtime'
import { syncServerTime } from '@/lib/clock'
import { ControlPanel, type Prefill } from './ControlPanel'
import { JoinQr } from './JoinQr'
import { ServiceDetail } from './tabs/Capacity'

const ReviorMap = lazy(() => import('@/components/map/ReviorMap').then((m) => ({ default: m.ReviorMap })))
const TabCapacity = lazy(() => import('./tabs/Capacity').then((m) => ({ default: m.CapacityTab })))
const TabClusters = lazy(() => import('./tabs/Clusters'))
const TabAllocations = lazy(() => import('./tabs/Allocations'))
const TabUnresolved = lazy(() => import('./tabs/Unresolved'))
const TabRules = lazy(() => import('./tabs/Rules'))
const TabFairness = lazy(() => import('./tabs/Fairness'))
const TabAudit = lazy(() => import('./tabs/Audit'))
const TabMessages = lazy(() => import('./tabs/Messages'))
const TabPersonas = lazy(() => import('./tabs/Personas'))
const TabStress = lazy(() => import('./tabs/Stress'))

const TABS = [
  ['capacity', 'Capacity'], ['clusters', 'Clusters'], ['allocations', 'Allocations'], ['unresolved', 'Unresolved'], ['rules', 'Rules'],
  ['fairness', 'Fairness'], ['audit', 'Audit'], ['messages', 'Messages'], ['personas', 'Demo personas'], ['stress', 'Stress test'],
] as const

function Kpi({ label, value, suffix, tone }: { label: string; value: number | string; suffix?: string; tone?: 'danger' | 'success' }) {
  return (
    <div className="grid min-w-0 gap-1 border-l border-line px-4 py-3 first:border-l-0">
      <span className="truncate text-[11px] uppercase tracking-[0.06em] text-muted">{label}</span>
      <span className={cn('tnum font-serif text-[clamp(1.8rem,1.2rem+1vw,2.6rem)] leading-none', tone === 'danger' && 'text-danger-fg', tone === 'success' && 'text-success-fg')}><NumberRoll value={value} suffix={suffix} /></span>
    </div>
  )
}

function BatchChip({ closesAt }: { closesAt: string | null }) {
  const secs = useCountdown(closesAt)
  if (!closesAt) return <span className="hidden text-[12px] uppercase tracking-[0.06em] text-muted xl:inline">No open batch</span>
  return <span className="tnum rounded-full border border-warning/50 bg-warning-bg px-3 py-1 text-[13px] text-warning-fg" role="timer">Batch closes {Math.floor(secs / 60)}:{String(secs % 60).padStart(2, '0')}</span>
}

export default function OpsDashboard() {
  const nav = useNavigate()
  const qc = useQueryClient()
  const setOps = useSession((s) => s.setOps)
  useRealtime('ops')
  const [tab, setTab] = useState<(typeof TABS)[number][0]>('capacity')
  const [prefill, setPrefill] = useState<Prefill | null>(null)
  const [service, setService] = useState<number | null>(null)
  const [resetOpen, setResetOpen] = useState(false)
  const [scenarioPick, setScenarioPick] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const active = useQuery({ queryKey: qk.scenario, queryFn: publicApi.activeScenario })
  const slug = active.data?.slug ?? 'potheri-demo'
  const scenarios = useQuery({ queryKey: qk.ops.scenarios, queryFn: opsApi.scenarios })
  const config = useQuery({ queryKey: qk.ops.config(slug), queryFn: () => opsApi.config(slug), enabled: !!active.data })
  const kpis = useQuery({ queryKey: qk.ops.kpis, queryFn: async () => { const k = await opsApi.kpis(); return k }, refetchInterval: 15_000 })
  const inv = useQuery({ queryKey: qk.ops.invariants, queryFn: opsApi.invariants, refetchInterval: 5_000 })
  const health = useQuery({ queryKey: qk.health, queryFn: publicApi.health, staleTime: 60_000 })
  useEffect(() => { if (health.data) syncServerTime(health.data.server_time) }, [health.data])

  const k = kpis.data
  const patchCfg = async (body: Parameters<typeof opsApi.patchConfig>[1]) => {
    try { qc.setQueryData(qk.ops.config(slug), await opsApi.patchConfig(slug, body)) } catch (e) { toastError(e); qc.invalidateQueries({ queryKey: qk.ops.config(slug) }) }
  }
  const doReset = async () => {
    setBusy(true)
    try {
      await opsApi.reset(slug)
      await qc.invalidateQueries()
      toast.success('Scenario reset')
      setResetOpen(false)
    } catch (e) { toastError(e) } finally { setBusy(false) }
  }
  const doActivate = async () => {
    if (!scenarioPick) return
    setBusy(true)
    try { await opsApi.activate(scenarioPick); await qc.invalidateQueries(); toast.success('Scenario switched'); setScenarioPick(null) } catch (e) { toastError(e) } finally { setBusy(false) }
  }
  const logout = () => { setOps(null); qc.clear(); nav('/ops/login', { replace: true }) }
  const qrMode = config.data?.join_qr_mode ?? 'corner'

  return (
    <div className="min-h-dvh bg-bg">
      <a className="skip-link" href="#ops-main">Skip to content</a>
      <header className="sticky top-0 z-40 border-b border-line bg-bg/95 backdrop-blur-sm">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 px-5 py-3">
          <ReviorLogo />
          <span className="rounded-full border border-line px-2.5 py-0.5 text-[11px] uppercase tracking-[0.06em] text-muted">Operations</span>
          <div className="w-56">
            <Select label="Scenario" value={scenarios.data?.items.find((s) => s.is_active)?.slug} onValueChange={(v) => v !== active.data?.slug && setScenarioPick(v)}
              options={(scenarios.data?.items ?? []).map((s) => ({ value: s.slug, label: s.name }))} placeholder="Scenario" />
          </div>
          <LiveDot />
          <BatchChip closesAt={k?.batch?.closes_at ?? null} />
          <div className="ml-auto flex flex-wrap items-center gap-4">
            <div role="radiogroup" aria-label="Join QR" className="flex rounded-full border border-line p-0.5 text-[11px] uppercase tracking-[0.06em]">
              {(['corner', 'fullscreen', 'hidden'] as const).map((m) => (
                <button key={m} type="button" role="radio" aria-checked={qrMode === m} onClick={() => patchCfg({ join_qr_mode: m })}
                  className={cn('press min-h-8 rounded-full px-3', qrMode === m ? 'bg-ink text-bg' : 'text-muted hover:text-ink')}>{m === 'fullscreen' ? 'Full' : m}</button>
              ))}
            </div>
            <label className="flex items-center gap-2 text-[12px] uppercase tracking-[0.06em]">Open booking
              <Switch checked={!!config.data?.open_booking_enabled} disabled={!config.data} aria-label="Open booking"
                onCheckedChange={async (v) => { try { await opsApi.openBooking(v); qc.invalidateQueries({ queryKey: qk.ops.config(slug) }); toast(v ? 'Open booking on' : 'Open booking off') } catch (e) { toastError(e) } }} />
            </label>
            <Button size="sm" variant="ghost" onClick={() => setResetOpen(true)}><RotateCcw /> Reset</Button>
            <Button size="sm" variant="quiet" onClick={logout}><LogOut /> Logout</Button>
          </div>
        </div>
        <div className="grid grid-cols-5 border-t border-line xl:grid-cols-10" aria-label="Key figures">
          <Kpi label="Affected" value={k?.affected ?? 0} />
          <Kpi label="Checked in" value={k?.checked_in ?? 0} />
          <Kpi label="Requested" value={k?.requested ?? 0} />
          <Kpi label="Held" value={k?.held ?? 0} />
          <Kpi label="Confirmed" value={k?.confirmed ?? 0} />
          <Kpi label="Waitlisted" value={k?.waitlisted ?? 0} />
          <Kpi label="Unresolved" value={k?.unresolved ?? 0} tone={k && k.unresolved > 0 ? 'danger' : undefined} />
          <Kpi label="Avg wait" value={k ? Math.round(k.avg_wait_min) : 0} suffix=" min" />
          <Kpi label="Fill rate" value={k ? Math.round(k.fill_rate * 100) : 0} suffix="%" />
          <div className="grid gap-1 border-l border-line px-4 py-3">
            <span className="text-[11px] uppercase tracking-[0.06em] text-muted">Invariants</span>
            <span className={cn('flex items-center gap-2 font-serif text-[clamp(1.4rem,1rem+0.8vw,2rem)] leading-none', inv.data?.ok === false ? 'text-danger-fg' : 'text-success-fg')} role="status">
              {inv.data?.ok === false ? <><X className="size-6" aria-hidden /> Broken</> : <><Check className="size-6" aria-hidden /> Holding</>}
            </span>
          </div>
        </div>
      </header>

      <main id="ops-main" className="grid gap-6 p-5">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,3fr)_minmax(420px,2fr)]">
          <div className="relative h-[clamp(420px,62vh,760px)]">
            <ErrorBoundary>
              <Suspense fallback={<div className="skeleton h-full rounded-card-sm" />}>
                <ReviorMap className="h-full" onSelectService={setService} onCloseEdge={(id) => setPrefill({ edgeId: id, nonce: Date.now() })}>
                  <JoinQr url={active.data?.join_url} mode={qrMode} onMode={(m) => patchCfg({ join_qr_mode: m })} />
                </ReviorMap>
              </Suspense>
            </ErrorBoundary>
          </div>
          <ControlPanel slug={slug} prefill={prefill} batchOpen={!!k?.batch} />
        </div>

        <Tabs value={tab} onValueChange={(v) => setTab(v as typeof tab)}>
          <TabsList aria-label="Details" className="flex-wrap">
            {TABS.map(([v, l]) => <TabsTrigger key={v} value={v}>{l}</TabsTrigger>)}
          </TabsList>
          <ErrorBoundary>
            <Suspense fallback={<div className="skeleton mt-4 h-48 rounded-card-sm" />}>
              <TabsContent value="capacity"><TabCapacity onSelect={setService} /></TabsContent>
              <TabsContent value="clusters"><TabClusters /></TabsContent>
              <TabsContent value="allocations"><TabAllocations /></TabsContent>
              <TabsContent value="unresolved"><TabUnresolved onAddCapacity={() => setPrefill({ openCapacity: true, nonce: Date.now() })} /></TabsContent>
              <TabsContent value="rules"><TabRules /></TabsContent>
              <TabsContent value="fairness"><TabFairness /></TabsContent>
              <TabsContent value="audit"><TabAudit /></TabsContent>
              <TabsContent value="messages"><TabMessages /></TabsContent>
              <TabsContent value="personas"><TabPersonas /></TabsContent>
              <TabsContent value="stress"><TabStress /></TabsContent>
            </Suspense>
          </ErrorBoundary>
        </Tabs>
      </main>

      <SidePanel open={service !== null} onOpenChange={(o) => !o && setService(null)} title="Service">
        {service !== null && <ServiceDetail id={service} />}
      </SidePanel>

      <ConfirmDialog open={resetOpen} onOpenChange={setResetOpen} title="Reset the scenario?" description="This reseeds the scenario, frees every persona and clears all requests and seats." confirmLabel="Reset everything" danger loading={busy} onConfirm={doReset} />
      <ConfirmDialog open={!!scenarioPick} onOpenChange={(o) => !o && setScenarioPick(null)} title="Switch scenario?" description="Passengers will land in the newly active scenario." confirmLabel="Switch" loading={busy} onConfirm={doActivate} />
    </div>
  )
}
