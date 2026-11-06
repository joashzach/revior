import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery } from '@tanstack/react-query'
import { Eye, EyeOff, Minus, Plus, MapPin } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { Link } from 'react-router-dom'
import { z } from 'zod'
import { authApi, publicApi } from '@/api/endpoints'
import { ApiError } from '@/api/http'
import { toastError } from '@/api/errors'
import { qk } from '@/api/queryKeys'
import type { HubsNearby, NodeRef, RegisterResult } from '@/api/types'
import { Pill } from '@/components/common/StatusPill'
import { Button } from '@/components/ui/button'
import { Checkbox, Field, Input, Switch } from '@/components/ui/form'
import { Dialog, DialogContent } from '@/components/ui/overlays'
import { S } from '@/config/strings'
import { useCompleteLogin } from '@/hooks/useCompleteLogin'
import { cn, fmtTime } from '@/lib/utils'

const schema = z.object({
  name: z.string().trim().min(1, 'Tell us your name'),
  email: z.string().trim().email('Enter a valid email'),
  password: z.string().min(6, 'At least 6 characters'),
  phone: z.string().trim().optional(),
  destination: z.number({ required_error: 'Choose where you are going', invalid_type_error: 'Choose where you are going' }),
  party_size: z.number().min(1).max(6),
  wheelchair: z.boolean(),
  elderly: z.boolean(),
  with_children: z.boolean(),
  medical: z.boolean(),
  deadline: z.string().optional(),
  allow_auto: z.boolean(),
})
type Form = z.infer<typeof schema>

function getPosition(): Promise<GeolocationPosition> {
  return new Promise((res, rej) => {
    if (!('geolocation' in navigator)) return rej(new Error('unsupported'))
    navigator.geolocation.getCurrentPosition(res, rej, { timeout: 8000, maximumAge: 60_000 })
  })
}

function LocationStep({ onDone }: { onDone: (hub: NodeRef) => void }) {
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState<HubsNearby | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [pick, setPick] = useState<number | null>(null)
  const applyDefault = async (why?: string) => {
    const r = await publicApi.hubsNearby()
    setRes(r)
    setPick(r.selected_hub_id)
    setNote(why ?? S.join.locDefault)
  }
  const ask = async () => {
    setBusy(true)
    try {
      const pos = await getPosition()
      const r = await publicApi.hubsNearby(pos.coords.latitude, pos.coords.longitude)
      setRes(r)
      setPick(r.selected_hub_id)
      setNote(r.reason === 'default' ? S.join.locDefault : null)
    } catch {
      await applyDefault() // denied, timed out (8 s) or unsupported → Potheri
    } finally {
      setBusy(false)
    }
  }
  const chosen = res?.hubs.find((h) => h.hub.id === pick)?.hub
  return (
    <div className="grid gap-6 rounded-card-sm border border-line p-6 sm:p-8">
      <div className="flex items-start gap-4">
        <span className="grid size-12 shrink-0 place-items-center rounded-full border border-line"><MapPin className="size-5" aria-hidden /></span>
        <div className="grid gap-1.5">
          <h2 className="text-[28px]">{S.join.locTitle}</h2>
          <p className="max-w-[52ch] text-[14px] text-muted">{S.join.locBody}</p>
        </div>
      </div>
      {!res ? (
        <div className="flex flex-wrap gap-3">
          <Button variant="primary" loading={busy} onClick={ask}>{S.join.locAllow}</Button>
          <Button variant="ghost" disabled={busy} onClick={() => applyDefault().catch(() => toastError(new ApiError(0, 'NETWORK', '')))}>{S.join.locSkip}</Button>
        </div>
      ) : (
        <div className="grid gap-4">
          {note && <p className="text-[13px] text-muted" role="status">{note}</p>}
          <ul className="grid gap-2" aria-label="Nearby hubs">
            {res.hubs.map((h) => (
              <li key={h.hub.id}>
                <button type="button" onClick={() => setPick(h.hub.id)} aria-pressed={pick === h.hub.id} className={cn('press flex min-h-14 w-full items-center justify-between gap-3 rounded-panel border px-4 text-left', pick === h.hub.id ? 'border-accent bg-accent-subtle' : 'border-line hover:border-ink/40')}>
                  <span><span className="font-medium">{h.hub.name}</span>{h.is_default && <span className="ml-2 text-[12px] uppercase tracking-[0.05em] text-muted">default</span>}</span>
                  <span className="tnum text-[13px] text-muted">{h.distance_km != null ? `${h.distance_km} km` : '—'}</span>
                </button>
              </li>
            ))}
          </ul>
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="primary" disabled={!chosen} onClick={() => chosen && onDone(chosen)}>Continue from {chosen?.name ?? 'hub'}</Button>
            <Button variant="quiet" size="sm" onClick={() => setRes(null)}>{S.join.changeHub}</Button>
          </div>
        </div>
      )}
    </div>
  )
}

function deadlineIso(hhmm?: string): string | null {
  if (!hhmm) return null
  const [h, m] = hhmm.split(':').map(Number)
  const d = new Date()
  d.setHours(h, m, 0, 0)
  if (d.getTime() < Date.now()) d.setDate(d.getDate() + 1)
  return d.toISOString()
}

function RegisterForm({ hub }: { hub: NodeRef }) {
  const complete = useCompleteLogin()
  const [show, setShow] = useState(false)
  const [done, setDone] = useState<RegisterResult | null>(null)
  const [q, setQ] = useState('')
  const dests = useQuery({ queryKey: qk.destinations(hub.id, q), queryFn: () => publicApi.destinations(hub.id, q), staleTime: 30_000 })
  const f = useForm<Form>({ resolver: zodResolver(schema), mode: 'onBlur', defaultValues: { name: '', email: '', password: '', phone: '', party_size: 1, wheelchair: false, elderly: false, with_children: false, medical: false, deadline: '', allow_auto: true } })
  const { register, control, handleSubmit, setError, formState: { errors, isSubmitting }, watch } = f
  const party = watch('party_size')
  const onSubmit = handleSubmit(async (v) => {
    try {
      const r = await authApi.register({
        name: v.name, email: v.email, password: v.password, phone: v.phone || undefined, hub_node_id: hub.id, destination_node_id: v.destination, party_size: v.party_size,
        allow_auto: v.allow_auto, needs: { wheelchair: v.wheelchair, elderly: v.elderly, with_children: v.with_children, medical: v.medical, connection_deadline_at: deadlineIso(v.deadline) },
      })
      setDone(r)
    } catch (e) {
      if (e instanceof ApiError && e.code === 'EMAIL_TAKEN') return setError('email', { message: S.errors.emailTaken })
      if (e instanceof ApiError && e.code === 'VALIDATION_ERROR') {
        for (const [k, msg] of Object.entries(e.fields)) setError((k === 'destination_node_id' ? 'destination' : k) as keyof Form, { message: msg })
        return
      }
      toastError(e)
    }
  })
  const dest = watch('destination')
  return (
    <>
      <form onSubmit={onSubmit} noValidate className="grid gap-6 rounded-card-sm border border-line p-6 sm:p-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-[28px]">Your details</h2>
          <Pill tone="info" size="sm" icon={MapPin}>Hub: {hub.name}</Pill>
        </div>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Name" error={errors.name?.message}>{(id, d) => <Input id={id} aria-describedby={d} aria-invalid={!!errors.name} autoComplete="name" {...register('name')} />}</Field>
          <Field label="Email" error={errors.email?.message}>{(id, d) => <Input id={id} aria-describedby={d} aria-invalid={!!errors.email} type="email" inputMode="email" autoComplete="email" {...register('email')} />}</Field>
          <Field label="Password" hint="At least 6 characters" error={errors.password?.message}>
            {(id, d) => (
              <div className="relative">
                <Input id={id} aria-describedby={d} aria-invalid={!!errors.password} type={show ? 'text' : 'password'} autoComplete="new-password" className="pr-12" {...register('password')} />
                <button type="button" onClick={() => setShow((s) => !s)} aria-label={show ? 'Hide password' : 'Show password'} className="absolute right-1 top-1 grid size-10 place-items-center rounded-full hover:bg-ink/6">{show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}</button>
              </div>
            )}
          </Field>
          <Field label="Phone (optional)">{(id) => <Input id={id} type="tel" inputMode="tel" autoComplete="tel" {...register('phone')} />}</Field>
        </div>

        <Controller control={control} name="destination" render={({ field }) => (
          <Field label="Where are you going?" error={errors.destination?.message}>
            {(id, d) => (
              <div className="grid gap-2">
                <Input id={id} aria-describedby={d} aria-invalid={!!errors.destination} role="combobox" aria-expanded aria-controls={`${id}-list`} autoComplete="off" placeholder="Search stations, e.g. Guindy" value={q} onChange={(e) => { setQ(e.target.value); field.onChange(undefined) }} />
                <ul id={`${id}-list`} role="listbox" className="scroll-thin flex max-h-40 flex-wrap gap-2 overflow-y-auto">
                  {(dests.data?.items ?? []).map((n) => (
                    <li key={n.id} role="option" aria-selected={dest === n.id}>
                      <button type="button" onClick={() => { field.onChange(n.id); setQ(n.name) }} className={cn('press h-10 rounded-pill border px-4 text-[14px]', dest === n.id ? 'border-accent bg-accent text-accent-contrast' : 'border-line hover:border-ink/50')}>{n.name}</button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Field>
        )} />

        <div className="grid gap-5 sm:grid-cols-2">
          <Controller control={control} name="party_size" render={({ field }) => (
            <Field label="Travelling together">
              {() => (
                <div className="inline-flex items-center gap-3">
                  <Button variant="ghost" size="icon" aria-label="One fewer" disabled={field.value <= 1} onClick={() => field.onChange(field.value - 1)}><Minus /></Button>
                  <span className="tnum w-10 text-center font-serif text-[32px] leading-none" aria-live="polite">{field.value}</span>
                  <Button variant="ghost" size="icon" aria-label="One more" disabled={field.value >= 6} onClick={() => field.onChange(field.value + 1)}><Plus /></Button>
                  <span className="text-[13px] text-muted">{party > 1 ? 'Kept together on one service' : 'person'}</span>
                </div>
              )}
            </Field>
          )} />
          <Field label="Connection deadline (optional)" hint="e.g. a flight at the Airport. We only offer options that arrive in time.">{(id, d) => <Input id={id} aria-describedby={d} type="time" {...register('deadline')} />}</Field>
        </div>

        <fieldset className="grid gap-3">
          <legend className="mb-1 text-[14px] font-medium">Anything we should know?</legend>
          <div className="grid gap-2 sm:grid-cols-2">
            {([['wheelchair', 'I use a wheelchair'], ['elderly', 'Senior citizen'], ['with_children', 'Travelling with children'], ['medical', 'Medical need']] as const).map(([k, label]) => (
              <Controller key={k} control={control} name={k} render={({ field }) => (
                <label className="press flex min-h-12 cursor-pointer items-center gap-3 rounded-panel border border-line px-4 hover:border-ink/40">
                  <Checkbox checked={field.value} onCheckedChange={(v) => field.onChange(v === true)} aria-label={label} />
                  <span className="text-[14px]">{label}</span>
                </label>
              )} />
            ))}
          </div>
        </fieldset>

        <Controller control={control} name="allow_auto" render={({ field }) => (
          <label className="flex items-center justify-between gap-4 rounded-panel border border-line px-4 py-3">
            <span className="text-[14px]">{S.options.allowAuto}</span>
            <Switch checked={field.value} onCheckedChange={field.onChange} aria-label={S.options.allowAuto} />
          </label>
        )} />

        <div className="flex flex-wrap items-center gap-4">
          <Button type="submit" variant="primary" size="lg" loading={isSubmitting}>{S.join.submit}</Button>
          <p className="text-[13px] text-muted">Have an account? <Link to="/login" className="underline decoration-line underline-offset-4 hover:decoration-ink">{S.landing.ctaLogin}</Link></p>
        </div>
      </form>

      <Dialog open={!!done} onOpenChange={() => {}}>
        <DialogContent title={S.join.ticketTitle} description={S.join.ticketBody} hideClose>
          {done && (
            <div className="grid gap-5">
              <div className="grid gap-1 rounded-panel border border-line p-5">
                <span className="eyebrow">Ticket ID</span>
                <span className="tnum font-serif text-[40px] leading-none">{done.ticket.ticket_id}</span>
                <span className="mt-2 text-[14px] text-muted">{done.ticket.service.label} · departs {fmtTime(done.ticket.service.depart_at)}</span>
              </div>
              <Button variant="primary" onClick={() => complete(done.token, done.passenger)}>{S.join.continue}</Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}

export default function Join() {
  const [hub, setHub] = useState<NodeRef | null>(null)
  useEffect(() => { document.title = 'Join Revior' }, [])
  return (
    <div className="mx-auto grid max-w-[860px] gap-8 pt-4">
      <div className="grid gap-3">
        <span className="eyebrow">Step {hub ? 2 : 1} of 2</span>
        <h1 className="text-[clamp(2.4rem,1.4rem+3vw,3.5rem)]">{S.join.title}</h1>
      </div>
      {hub ? <RegisterForm hub={hub} /> : <LocationStep onDone={setHub} />}
    </div>
  )
}
