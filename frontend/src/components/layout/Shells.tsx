import { ArrowUpRight } from 'lucide-react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { ReviorLogo } from '@/components/brand/ReviorLogo'
import { buttonVariants } from '@/components/ui/button'
import { S } from '@/config/strings'
import { cn } from '@/lib/utils'

export function MarketingLayout() {
  return (
    <div className="min-h-dvh">
      <a href="#main" className="skip-link">{S.common.skip}</a>
      <Outlet />
    </div>
  )
}

export function MarketingNav() {
  return (
    <header className="mx-auto flex h-[72px] w-full max-w-[1200px] items-center justify-between px-5 sm:px-8">
      <Link to="/" aria-label="Revior home"><ReviorLogo /></Link>
      <nav aria-label="Main" className="flex items-center gap-2 sm:gap-3">
        <NavLink to="/login" className="press hidden h-10 items-center rounded-button px-4 text-[13px] uppercase tracking-[0.05em] hover:bg-ink/6 sm:flex">{S.landing.ctaLogin}</NavLink>
        <Link to="/demo-join" className={buttonVariants({ variant: 'primary', size: 'sm' })}>
          Live demo <ArrowUpRight />
        </Link>
      </nav>
    </header>
  )
}

/** Centered, calm frame for demo-join / join / login / qr-login. */
export function PassengerAuthLayout() {
  return (
    <div className="min-h-dvh">
      <a href="#main" className="skip-link">{S.common.skip}</a>
      <header className="mx-auto flex h-[72px] max-w-[1200px] items-center justify-between px-5 sm:px-8">
        <Link to="/" aria-label="Revior home"><ReviorLogo /></Link>
        <Link to="/login" className="text-[13px] uppercase tracking-[0.05em] text-muted hover:text-ink">{S.landing.ctaLogin}</Link>
      </header>
      <main id="main" className="mx-auto w-full max-w-[1200px] px-5 pb-16 pt-4 sm:px-8">
        <Outlet />
      </main>
    </div>
  )
}

export function OpsAuthLayout() {
  return (
    <div className="grid min-h-dvh place-items-center px-5">
      <main id="main" className={cn('w-full max-w-md')}>
        <Outlet />
      </main>
    </div>
  )
}
