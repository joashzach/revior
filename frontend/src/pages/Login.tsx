import { zodResolver } from '@hookform/resolvers/zod'
import { Loader2, QrCode } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { z } from 'zod'
import { authApi } from '@/api/endpoints'
import { ApiError } from '@/api/http'
import { toastError } from '@/api/errors'
import { ReviorLogo } from '@/components/brand/ReviorLogo'
import { Button } from '@/components/ui/button'
import { Field, Input } from '@/components/ui/form'
import { Dialog, DialogContent } from '@/components/ui/overlays'
import { useSession } from '@/app/session'
import { S } from '@/config/strings'
import { useCompleteLogin } from '@/hooks/useCompleteLogin'

const schema = z.object({ email: z.string().trim().email('Enter a valid email'), password: z.string().min(1, 'Enter your password') })

export function Login() {
  const [sp] = useSearchParams()
  const complete = useCompleteLogin()
  const [qrInfo, setQrInfo] = useState(false)
  const { register, handleSubmit, setError, formState: { errors, isSubmitting } } = useForm({ resolver: zodResolver(schema), mode: 'onBlur' })
  const submit = handleSubmit(async (v) => {
    try {
      const r = await authApi.login(v.email, v.password)
      complete(r.token, r.passenger, sp.get('next'))
    } catch (e) {
      if (e instanceof ApiError && e.code === 'INVALID_CREDENTIALS') return setError('password', { message: S.errors.invalidCredentials })
      toastError(e)
    }
  })
  return (
    <div className="mx-auto grid max-w-[460px] gap-8 pt-8">
      <div className="grid gap-3">
        <span className="eyebrow">Passenger</span>
        <h1 className="text-[clamp(2.4rem,1.4rem+3vw,3.5rem)]">{S.login.title}</h1>
      </div>
      <form onSubmit={submit} noValidate className="grid gap-5">
        <Field label="Email" error={errors.email?.message}>{(id, d) => <Input id={id} aria-describedby={d} aria-invalid={!!errors.email} type="email" inputMode="email" autoComplete="email" {...register('email')} />}</Field>
        <Field label="Password" error={errors.password?.message}>{(id, d) => <Input id={id} aria-describedby={d} aria-invalid={!!errors.password} type="password" autoComplete="current-password" {...register('password')} />}</Field>
        <Button type="submit" variant="primary" size="lg" loading={isSubmitting}>{S.login.submit}</Button>
      </form>
      <div className="grid gap-3 border-t border-line pt-6 text-[14px]">
        <button type="button" onClick={() => setQrInfo(true)} className="press inline-flex items-center gap-2 text-left underline decoration-line underline-offset-4 hover:decoration-ink"><QrCode className="size-4" aria-hidden /> {S.login.qrTitle}</button>
        <p className="text-muted">New here? <Link className="underline decoration-line underline-offset-4 hover:decoration-ink" to="/join">Create an account</Link> or <Link className="underline decoration-line underline-offset-4 hover:decoration-ink" to="/demo-join">try the live demo</Link>.</p>
      </div>
      <Dialog open={qrInfo} onOpenChange={setQrInfo}>
        <DialogContent title={S.login.qrTitle} description={S.login.qrBody}><Button variant="dark" size="sm" onClick={() => setQrInfo(false)}>Got it</Button></DialogContent>
      </Dialog>
    </div>
  )
}

export function QrLogin() {
  const [sp] = useSearchParams()
  const complete = useCompleteLogin()
  const [failed, setFailed] = useState(false)
  const ran = useRef(false)
  useEffect(() => {
    if (ran.current) return
    ran.current = true
    const t = sp.get('t')
    if (!t) return setFailed(true)
    authApi.qrLogin(t).then((r) => complete(r.token, r.passenger)).catch(() => setFailed(true))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  if (failed)
    return (
      <div role="alert" className="mx-auto grid max-w-[460px] gap-5 pt-16 text-center">
        <h1 className="text-[clamp(2.2rem,1.4rem+2.6vw,3rem)]">{S.login.qrFailTitle}</h1>
        <p className="text-muted">{S.login.qrFailBody}</p>
        <div><Link to="/login" className="inline-flex"><Button variant="primary">Log in with email</Button></Link></div>
      </div>
    )
  return (
    <div role="status" className="grid min-h-[60dvh] place-items-center text-center">
      <div className="grid justify-items-center gap-4"><Loader2 className="size-8 animate-spin text-accent" aria-hidden /><p className="font-serif text-[28px]">{S.login.qrBusy}</p></div>
    </div>
  )
}

export function OpsLogin() {
  const nav = useNavigate()
  const setOps = useSession((s) => s.setOps)
  const { register, handleSubmit, setError, formState: { errors, isSubmitting } } = useForm<{ password: string }>({ mode: 'onSubmit' })
  const submit = handleSubmit(async (v) => {
    try {
      const r = await authApi.opsLogin(v.password)
      setOps(r.token)
      nav('/ops', { replace: true })
    } catch (e) {
      if (e instanceof ApiError && e.code === 'INVALID_CREDENTIALS') return setError('password', { message: 'Wrong operator password.' })
      if (e instanceof ApiError && e.code === 'RATE_LIMITED') return setError('password', { message: S.errors.rateLimited })
      toastError(e)
    }
  })
  return (
    <div className="grid gap-8">
      <ReviorLogo size="lg" />
      <div className="grid gap-2">
        <h1 className="text-[40px]">{S.ops.loginTitle}</h1>
        <p className="text-[14px] text-muted">Operator access only.</p>
      </div>
      <form onSubmit={submit} className="grid gap-5" noValidate>
        <Field label="Operator password" error={errors.password?.message}>{(id, d) => <Input id={id} aria-describedby={d} aria-invalid={!!errors.password} type="password" autoComplete="current-password" autoFocus {...register('password', { required: 'Enter the operator password' })} />}</Field>
        <Button type="submit" variant="primary" size="lg" loading={isSubmitting}>{S.ops.loginSubmit}</Button>
      </form>
    </div>
  )
}

export function NotFound() {
  return (
    <div className="grid min-h-dvh place-items-center px-5 text-center">
      <div className="grid justify-items-center gap-5">
        <ReviorLogo />
        <h1 className="text-[clamp(2.4rem,1.4rem+3vw,3.5rem)]">This stop doesn't exist</h1>
        <p className="text-muted">The page you wanted isn't on this line.</p>
        <Link to="/"><Button variant="primary">Back to Revior</Button></Link>
      </div>
    </div>
  )
}
