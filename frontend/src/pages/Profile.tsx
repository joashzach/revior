import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Expand, LogOut, Shuffle, Users } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { authApi, meApi, publicApi } from '@/api/endpoints'
import { toastError } from '@/api/errors'
import { qk } from '@/api/queryKeys'
import type { Needs } from '@/api/types'
import { useSession } from '@/app/session'
import { NeedChips, QRPanel } from '@/components/common/domain'
import { ErrorState, SkeletonBlocks } from '@/components/common/primitives'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/form'
import { Dialog, DialogContent, Select, Sheet } from '@/components/ui/overlays'
import { S } from '@/config/strings'
import { useMe } from '@/hooks/queries'
import { useCompleteLogin } from '@/hooks/useCompleteLogin'
import { fmtDateTime } from '@/lib/utils'

const EDITABLE = ['REGISTERED', 'BOOKED', 'AFFECTED']
const NEED_ROWS: { key: keyof Omit<Needs, 'connection_deadline_at'>; label: string }[] = [
  { key: 'wheelchair', label: 'Wheelchair user' },
  { key: 'elderly', label: 'Senior citizen' },
  { key: 'with_children', label: 'Travelling with children' },
  { key: 'medical', label: 'Medical need' },
]

export default function Profile() {
  const nav = useNavigate()
  const qc = useQueryClient()
  const me = useMe()
  const setPassenger = useSession((s) => s.setPassenger)
  const complete = useCompleteLogin()
  const [full, setFull] = useState(false)
  const [pickOpen, setPickOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const qr = useQuery({ queryKey: ['login-qr'], queryFn: meApi.loginQr, staleTime: 60_000 })
  const personas = useQuery({ queryKey: qk.personas, queryFn: publicApi.personas, enabled: pickOpen, refetchInterval: pickOpen ? 4000 : false })
  const dests = useQuery({ queryKey: qk.destinations(me.data?.hub.id), queryFn: () => publicApi.destinations(me.data?.hub.id), enabled: !!me.data })

  if (me.isLoading) return <SkeletonBlocks rows={2} rowClass="h-48" />
  if (me.isError || !me.data) return <ErrorState title="We couldn't load your profile" onRetry={() => me.refetch()} />
  const p = me.data
  const editable = EDITABLE.includes(p.state)

  const save = async (body: Parameters<typeof meApi.patch>[0]) => {
    try { qc.setQueryData(qk.me, await meApi.patch(body)); qc.invalidateQueries({ queryKey: qk.trip }); qc.invalidateQueries({ queryKey: qk.options }) } catch (e) { toastError(e); qc.invalidateQueries({ queryKey: qk.me }) }
  }
  const demoSwitch = async (mode: 'next' | 'pick', id?: number) => {
    setBusy(true)
    try {
      const r = await meApi.demoSwitch(mode, id)
      setPickOpen(false)
      complete(r.token, r.passenger, '/trip')
    } catch (e) { toastError(e); qc.invalidateQueries({ queryKey: qk.personas }) } finally { setBusy(false) }
  }
  const logout = async () => {
    try { await authApi.logout() } catch { /* the token is cleared either way */ }
    setPassenger(null)
    qc.clear()
    nav('/', { replace: true })
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_360px]">
      <div className="grid content-start gap-6">
        <div className="grid gap-2">
          <h1 className="rise rise-1 text-[clamp(2.2rem,1.4rem+3vw,3.5rem)] leading-[1.05]">{S.profile.title}</h1>
        </div>

        <section className="rise rise-2 grid gap-5 rounded-card-sm border border-line p-6 sm:p-8" aria-label="Details">
          <dl className="grid gap-5 sm:grid-cols-2">
            <div><dt className="eyebrow">Name</dt><dd className="mt-1 font-serif text-[26px] leading-tight">{p.name}</dd></div>
            <div><dt className="eyebrow">Email</dt><dd className="mt-1 break-all text-[15px]">{p.email ?? 'Demo persona'}</dd></div>
            <div><dt className="eyebrow">Hub</dt><dd className="mt-1 text-[15px]">{p.hub.name}</dd></div>
            <div>
              <dt className="eyebrow">Destination</dt>
              <dd className="mt-1 text-[15px]">
                {editable && dests.data ? (
                  <Select label="Destination" value={String(p.destination.id)} onValueChange={(v) => save({ destination_node_id: Number(v) })} options={dests.data.items.map((d) => ({ value: String(d.id), label: d.name }))} />
                ) : p.destination.name}
              </dd>
            </div>
            <div>
              <dt className="eyebrow">Party size</dt>
              <dd className="mt-1 flex items-center gap-3">
                {editable ? (
                  <>
                    <Button size="icon" variant="ghost" aria-label="Fewer travellers" disabled={p.party_size <= 1} onClick={() => save({ party_size: p.party_size - 1 })}>−</Button>
                    <span className="tnum font-serif text-[26px]" aria-live="polite">{p.party_size}</span>
                    <Button size="icon" variant="ghost" aria-label="More travellers" disabled={p.party_size >= 6} onClick={() => save({ party_size: p.party_size + 1 })}>+</Button>
                  </>
                ) : <span className="tnum font-serif text-[26px]">{p.party_size}</span>}
              </dd>
            </div>
          </dl>
          <div className="grid gap-3 border-t border-line pt-5">
            <span className="eyebrow">Needs</span>
            {editable ? (
              <ul className="grid gap-2 sm:grid-cols-2">
                {NEED_ROWS.map((n) => (
                  <li key={n.key}>
                    <label className="flex min-h-11 cursor-pointer items-center justify-between gap-3 rounded-panel border border-line px-4 py-2 text-[14px]">
                      {n.label}
                      <Switch checked={p.needs[n.key]} onCheckedChange={(v) => save({ needs: { ...p.needs, [n.key]: v } })} aria-label={n.label} />
                    </label>
                  </li>
                ))}
              </ul>
            ) : (
              <>
                <NeedChips needs={p.needs} />
                <p className="text-[13px] text-muted">{S.profile.locked}</p>
              </>
            )}
            {p.needs.connection_deadline_at && <p className="tnum text-[14px] text-muted">Connection deadline {fmtDateTime(p.needs.connection_deadline_at)}</p>}
          </div>
        </section>

        <div className="flex flex-wrap gap-3">
          <Button variant="ghost" onClick={logout}><LogOut /> {S.profile.logout}</Button>
        </div>
      </div>

      <aside className="grid content-start gap-4">
        <section className="rise rise-3 grid justify-items-start gap-4 rounded-card-sm border border-line p-6" aria-label={S.profile.qrTitle}>
          <span className="eyebrow">{S.profile.qrTitle}</span>
          {qr.data ? (
            <>
              <QRPanel value={qr.data.url} size={176} />
              <p className="text-[13px] text-muted">Expires {fmtDateTime(qr.data.expires_at)}. {S.profile.qrBody}</p>
              <Button size="sm" variant="dark" onClick={() => setFull(true)}><Expand /> {S.profile.qrFull}</Button>
            </>
          ) : qr.isError ? <p className="text-[14px] text-danger-fg">Couldn't create a QR right now.</p> : <div className="skeleton size-44 rounded-panel" />}
        </section>

        {p.is_demo_persona && (
          <section className="grid gap-3 rounded-card-sm border border-line p-6" aria-label={S.profile.switchTitle}>
            <span className="eyebrow">{S.profile.switchTitle}</span>
            <p className="text-[13px] text-muted">{S.profile.switchBody}</p>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="dark" loading={busy} onClick={() => demoSwitch('next')}><Shuffle /> {S.profile.next}</Button>
              <Button size="sm" variant="ghost" onClick={() => setPickOpen(true)}><Users /> {S.profile.pick}</Button>
            </div>
          </section>
        )}
      </aside>

      <Dialog open={full} onOpenChange={setFull}>
        <DialogContent title={S.profile.qrTitle} description="Point another device's camera here.">
          {qr.data && <div className="grid justify-items-center py-2"><QRPanel value={qr.data.url} size={Math.min(320, typeof window === 'undefined' ? 320 : window.innerWidth - 96)} /></div>}
        </DialogContent>
      </Dialog>

      <Sheet open={pickOpen} onOpenChange={setPickOpen} title={S.profile.pick} description="Free personas only." tall>
        <ul className="grid gap-3 pb-4 sm:grid-cols-2">
          {(personas.data?.items ?? []).map((x) => (
            <li key={x.id}>
              <button type="button" disabled={x.is_taken || busy} onClick={() => demoSwitch('pick', x.id)}
                className="press grid min-h-11 w-full gap-1 rounded-panel border border-line p-4 text-left enabled:hover:border-ink disabled:opacity-50">
                <span className="font-medium"><span aria-hidden>{x.emoji}</span> {x.title}</span>
                <span className="text-[13px] text-muted">{x.is_taken ? 'Taken right now' : x.summary}</span>
              </button>
            </li>
          ))}
        </ul>
      </Sheet>
    </div>
  )
}
