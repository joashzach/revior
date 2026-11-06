import { ArrowRight, Check, Hourglass, ShieldCheck } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { MarketingNav } from '@/components/layout/Shells'
import { buttonVariants } from '@/components/ui/button'
import { Pill } from '@/components/common/StatusPill'
import { S } from '@/config/strings'
import { cn } from '@/lib/utils'

/** A framed, live-rendered passenger status card (real product UI, not a screenshot or blobs). */
function PhoneCard({ step }: { step: number }) {
  const frames = [
    { pill: <Pill tone="danger" icon={Hourglass} size="md">Cancelled</Pill>, title: 'Your train is cancelled', body: 'Waterlogging near Guduvanchery. Choose how to get home.', foot: 'Requests close in 0:24' },
    { pill: <Pill tone="info" size="md">1st · 2nd choice</Pill>, title: 'MTC 570A Potheri → Guindy', body: 'Arrives 19:52 · 3 seats left · accessible seats', foot: 'Your request is in the batch' },
    { pill: <Pill tone="success" icon={Check} size="md">Placed on your 1st choice</Pill>, title: 'Seats 014, 015', body: 'Priority 41 = medical +30, waited 12 min +4, children +7. Ticket price is never used.', foot: 'Hold ends in 1:48' },
    { pill: <Pill tone="success" icon={Check} size="md">Confirmed</Pill>, title: 'You are on your way home', body: 'A decline elsewhere reached the waitlist in 2 seconds. Nobody lost a seat to a faster phone.', foot: 'Boarding pass ready' },
  ]
  const f = frames[step]
  return (
    <div className="relative mx-auto w-[min(100%,340px)] rounded-[44px] border border-ink/70 bg-bg p-3 shadow-pop" aria-hidden>
      <div className="grid min-h-[480px] content-between gap-6 rounded-[34px] border border-line bg-bg p-6">
        <div className="grid gap-3">
          <span className="eyebrow">Revior · Potheri</span>
          <div key={step} className="grid gap-4 [animation:rise_320ms_var(--ease-out)]">
            {f.pill}
            <h3 className="text-[30px] leading-[1.1]">{f.title}</h3>
            <p className="text-[14px] text-muted">{f.body}</p>
          </div>
        </div>
        <div className="grid gap-3">
          <div className="h-1.5 overflow-hidden rounded-full bg-line"><div className="h-full rounded-full bg-accent transition-[width] duration-500" style={{ width: `${(step + 1) * 25}%` }} /></div>
          <p className="tnum text-[12px] uppercase tracking-[0.05em] text-muted">{f.foot}</p>
          <div aria-hidden className="grid h-12 place-items-center rounded-button border border-ink/60 text-[13px] uppercase tracking-[0.04em]">{step === 2 ? 'Accept seat' : step === 0 ? 'See your options' : step === 1 ? 'Send my request' : 'View boarding pass'}</div>
        </div>
      </div>
    </div>
  )
}

function KpiStrip() {
  const k = [['Affected', '386'], ['Placed', '371'], ['Waitlisted', '9'], ['Fill rate', '97%']]
  return (
    <div className="grid grid-cols-4 divide-x divide-line rounded-card-sm border border-line bg-bg" aria-hidden>
      {k.map(([l, v]) => (
        <div key={l} className="grid gap-1 px-3 py-4 sm:px-5">
          <span className="eyebrow">{l}</span>
          <span className="tnum font-serif text-[30px] leading-none sm:text-[36px]">{v}</span>
        </div>
      ))}
    </div>
  )
}

function useActiveStep(count: number) {
  const refs = useRef<(HTMLElement | null)[]>([])
  const [active, setActive] = useState(0)
  useEffect(() => {
    const io = new IntersectionObserver(
      (entries) => entries.forEach((e) => e.isIntersecting && setActive(Number((e.target as HTMLElement).dataset.i))),
      { rootMargin: '-45% 0px -45% 0px' },
    )
    refs.current.forEach((el) => el && io.observe(el))
    return () => io.disconnect()
  }, [count])
  return { active, setRef: (i: number) => (el: HTMLElement | null) => { refs.current[i] = el } }
}

export default function Landing() {
  const L = S.landing
  const { active, setRef } = useActiveStep(L.steps.length)
  return (
    <>
      <MarketingNav />
      <main id="main">
        {/* HERO — one point of view, the product shown, one primary action */}
        <section className="relative overflow-hidden">
          <div aria-hidden className="pointer-events-none absolute -right-24 -top-10 h-[520px] w-[620px] rounded-full opacity-70 blur-[70px]" style={{ background: 'linear-gradient(135deg, color-mix(in oklab, var(--color-coral) 70%, transparent), color-mix(in oklab, var(--color-sky-blue) 80%, transparent))' }} />
          <div className="relative mx-auto grid max-w-[1200px] items-center gap-14 px-5 pb-20 pt-10 sm:px-8 lg:grid-cols-[1.1fr_0.9fr] lg:pb-28 lg:pt-16">
            <div className="grid gap-8">
              <span className="eyebrow">Disruption recovery for suburban rail</span>
              <h1 className="text-[clamp(3rem,1.6rem+5.6vw,5rem)] leading-[1.02]">{L.heroTitle}</h1>
              <p className="max-w-[46ch] text-[18px] text-muted sm:text-[20px]">{L.heroSub}</p>
              <div>
                <Link to="/demo-join" className={buttonVariants({ variant: 'primary', size: 'lg' })}>{L.ctaDemo} <ArrowRight /></Link>
              </div>
            </div>
            <div className="grid gap-6">
              <PhoneCard step={2} />
            </div>
          </div>
          <div className="relative mx-auto max-w-[1200px] px-5 pb-16 sm:px-8"><KpiStrip /></div>
        </section>

        {/* HOW IT WORKS — one scroll-driven narrative: the phone changes as each step enters view (static if reduced motion) */}
        <section aria-labelledby="how" className="border-t border-line">
          <div className="mx-auto grid max-w-[1200px] gap-10 px-5 py-20 sm:px-8 lg:grid-cols-[1fr_380px] lg:gap-20 lg:py-28">
            <div>
              <h2 id="how" className="max-w-[16ch] text-[clamp(2.4rem,1.4rem+3vw,3.5rem)]">{L.howTitle}</h2>
              <ol className="mt-12 grid gap-0">
                {L.steps.map((s, i) => (
                  <li key={s.k} ref={setRef(i)} data-i={i} className={cn('border-t border-line py-10 transition-colors duration-300 lg:min-h-[44vh]', i === active ? 'text-ink' : 'text-muted')}>
                    <span className={cn('tnum font-serif text-[44px] leading-none transition-colors duration-300', i === active ? 'text-accent' : 'text-faint')}>{String(i + 1).padStart(2, '0')}</span>
                    <h3 className={cn('mt-3 text-[28px] transition-colors duration-300', i !== active && 'text-muted')}>{s.k}</h3>
                    <p className="mt-3 max-w-[48ch] text-muted">{s.d}</p>
                  </li>
                ))}
              </ol>
            </div>
            <div className="hidden lg:block">
              <div className="sticky top-24"><PhoneCard step={active} /></div>
            </div>
          </div>
        </section>

        {/* WHY IT IS DIFFERENT — editorial rows, not an icon-card grid; proof over adjectives */}
        <section aria-labelledby="why" className="border-t border-line">
          <div className="mx-auto grid max-w-[1200px] gap-12 px-5 py-20 sm:px-8 lg:grid-cols-[0.8fr_1.2fr] lg:py-28">
            <h2 id="why" className="max-w-[12ch] text-[clamp(2.4rem,1.4rem+3vw,3.5rem)]">{L.whyTitle}</h2>
            <div className="grid gap-0">
              {L.why.map((w, i) => (
                <div key={w.k} className={cn('grid gap-2 border-t border-line py-8 sm:grid-cols-[56px_1fr] sm:gap-6', i === 2 && 'border-b')}>
                  <span className="tnum font-serif text-[32px] leading-none text-faint">{i + 1}</span>
                  <div>
                    <h3 className="text-[26px]">{w.k}</h3>
                    <p className="mt-2 max-w-[52ch] text-muted">{w.d}</p>
                  </div>
                </div>
              ))}
              <div className="mt-8 flex flex-wrap items-center gap-4 rounded-card-sm bg-surface-2 p-6 sm:p-8">
                <ShieldCheck className="size-7 shrink-0 text-accent" aria-hidden />
                <p className="tnum font-serif text-[clamp(1.4rem,1rem+1.6vw,2rem)] leading-tight">1000 requests · 10 seats · <span className="text-success-fg">0 over-allocations</span> · 0 errors</p>
                <p className="w-full text-[13px] text-muted">The stress test the operator runs live from the dashboard. Seats are locked in the database, not in memory.</p>
              </div>
            </div>
          </div>
        </section>

        <footer className="border-t border-line">
          <div className="mx-auto flex max-w-[1200px] flex-wrap items-center justify-between gap-4 px-5 py-10 text-[13px] text-muted sm:px-8">
            <p>{L.footer}</p>
            <p>{L.team}</p>
          </div>
        </footer>
      </main>
    </>
  )
}
