import { useQueryClient } from '@tanstack/react-query'
import { Bell, ChevronRight, CircleUserRound, Compass, HelpCircle, MapPinned, Menu, Route, Ticket } from 'lucide-react'
import { AnimatePresence } from 'motion/react'
import * as m from 'motion/react-m'
import { useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { meApi } from '@/api/endpoints'
import { qk } from '@/api/queryKeys'
import { routeForState, shouldAutoNavigate } from '@/app/stateRouter'
import { ReviorLogo } from '@/components/brand/ReviorLogo'
import { LiveDot } from '@/components/common/primitives'
import { Button } from '@/components/ui/button'
import { Sheet, SidePanel } from '@/components/ui/overlays'
import { S } from '@/config/strings'
import { useIsDesktop } from '@/hooks/useMedia'
import { useHealthSync, useMe, useNotifications, useStatus } from '@/hooks/queries'
import { cn, fmtTime } from '@/lib/utils'
import { useRealtime } from '@/realtime/useRealtime'
import type { PassengerState } from '@/api/types'

const NAV = [
  { to: '/trip', label: S.nav.trip, icon: Ticket },
  { to: '/status', label: S.nav.status, icon: Compass },
  { to: '/why', label: S.nav.why, icon: HelpCircle },
  { to: '/alternatives', label: S.nav.alternatives, icon: Route },
  { to: '/profile', label: S.nav.profile, icon: CircleUserRound },
]

/** State router (contract §1.2): navigate on a state CHANGE, never away from /why, /profile, /alternatives by choice. */
function useStateRouter() {
  const nav = useNavigate()
  const loc = useLocation()
  const { data: me } = useMe()
  const { data: st } = useStatus()
  const state: PassengerState | undefined = st?.state ?? me?.state
  const prev = useRef<PassengerState | null>(null)
  const first = useRef(true)
  const [banner, setBanner] = useState<PassengerState | null>(null)
  useEffect(() => {
    if (!state) return
    if (first.current) {
      first.current = false
      prev.current = state
      // on app load: land on the screen the state belongs to (unless the user deep-linked somewhere deliberate)
      if (['/trip', '/'].includes(loc.pathname) && routeForState(state) !== loc.pathname) nav(routeForState(state), { replace: true })
      return
    }
    const verdict = shouldAutoNavigate(loc.pathname, prev.current, state)
    prev.current = state
    if (verdict === 'go') {
      // small delay so the disruption alert on /trip is seen (P-4.3: auto-navigate after 2 s)
      const t = setTimeout(() => nav(routeForState(state)), loc.pathname === '/trip' && state === 'AFFECTED' ? 2000 : 0)
      return () => clearTimeout(t)
    }
    if (verdict === 'banner') setBanner(state)
  }, [state]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (banner && routeForState(banner) === loc.pathname) setBanner(null) }, [loc.pathname, banner])
  return { banner, goBanner: () => { if (banner) { nav(routeForState(banner)); setBanner(null) } } }
}

function NotificationsBell() {
  const [open, setOpen] = useState(false)
  const desktop = useIsDesktop()
  const qc = useQueryClient()
  const { data } = useNotifications()
  const items = data?.items ?? []
  const unread = items.filter((n) => !n.read)
  useEffect(() => {
    if (open && unread.length) meApi.markRead(unread.map((n) => n.id)).then(() => qc.invalidateQueries({ queryKey: qk.notifications })).catch(() => {})
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps
  const list = items.length ? (
    <ul className="grid gap-3">
      {items.map((n) => (
        <li key={n.id} className={cn('rounded-panel border p-4', n.read ? 'border-line' : 'border-accent/40 bg-accent-subtle')}>
          <div className="flex items-baseline justify-between gap-3">
            <p className="font-medium">{n.title}</p>
            <time className="tnum shrink-0 text-[12px] text-faint">{fmtTime(n.created_at)}</time>
          </div>
          <p className="mt-1 text-[14px] text-muted">{n.body}</p>
        </li>
      ))}
    </ul>
  ) : (
    <p className="text-muted">Nothing yet. We'll message you here when something changes.</p>
  )
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} aria-label={`Notifications${unread.length ? `, ${unread.length} unread` : ''}`} className="press relative grid size-11 place-items-center rounded-full hover:bg-ink/6">
        <Bell className="size-5" />
        {unread.length > 0 && <span className="tnum absolute right-1 top-1 grid min-w-5 place-items-center rounded-full bg-accent px-1 text-[11px] text-accent-contrast">{unread.length}</span>}
      </button>
      {desktop ? <SidePanel open={open} onOpenChange={setOpen} title="Notifications">{list}</SidePanel> : <Sheet open={open} onOpenChange={setOpen} title="Notifications" tall>{list}</Sheet>}
    </>
  )
}

export function PassengerShell() {
  useRealtime('passenger')
  useHealthSync()
  const { banner, goBanner } = useStateRouter()
  const [more, setMore] = useState(false)
  const nav = useNavigate()
  const loc = useLocation()
  const { data: me } = useMe()

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[var(--sidebar-w)_1fr]">
      <a href="#main" className="skip-link">{S.common.skip}</a>
      {/* laptop sidebar */}
      <aside className="sticky top-0 hidden h-dvh flex-col justify-between border-r border-line p-6 lg:flex">
        <div className="grid gap-9">
          <ReviorLogo />
          <nav aria-label="Primary" className="grid gap-1">
            {NAV.map(({ to, label, icon: Icon }) => (
              <NavLink key={to} to={to} className={({ isActive }) => cn('press flex h-12 items-center gap-3 rounded-button px-4 text-[14px] uppercase tracking-[0.05em] transition-colors hover:bg-ink/6', isActive && 'bg-inverse text-on-inverse hover:bg-inverse')}>
                <Icon className="size-[18px]" aria-hidden /> {label}
              </NavLink>
            ))}
          </nav>
        </div>
        <div className="grid gap-3 text-[13px]">
          {me && (
            <div className="rounded-panel border border-line p-4">
              <p className="font-medium">{me.name}</p>
              <p className="text-muted">{me.hub.name} <span aria-hidden>→</span> {me.destination.name}</p>
            </div>
          )}
          <LiveDot />
        </div>
      </aside>

      <div className="flex min-h-dvh min-w-0 flex-col pb-[calc(76px+var(--safe-bottom))] lg:pb-0">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-line bg-bg/95 px-4 pt-[var(--safe-top)] backdrop-blur-sm sm:px-6 lg:px-10">
          <div className="lg:hidden"><ReviorLogo size="sm" /></div>
          <div className="hidden lg:block" />
          <div className="flex items-center gap-1">
            <span className="lg:hidden"><LiveDot showLabel={false} /></span>
            <NotificationsBell />
          </div>
        </header>
        <AnimatePresence>
          {banner && (
            <m.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="sticky top-16 z-20 flex flex-wrap items-center justify-between gap-3 border-b border-warning/40 bg-warning-bg px-4 py-3 text-warning-fg sm:px-6 lg:px-10" role="status">
              <span className="text-[14px]">Your trip changed. Your next step is on another screen.</span>
              <Button size="xs" variant="dark" onClick={goBanner}>Go <ChevronRight /></Button>
            </m.div>
          )}
        </AnimatePresence>
        <main id="main" className="mx-auto w-full max-w-[1280px] flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-10">
          <Outlet />
        </main>
      </div>

      {/* mobile bottom nav: Trip · Status · Why · More */}
      <nav aria-label="Primary" className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-bg/95 pb-[var(--safe-bottom)] backdrop-blur-sm lg:hidden">
        <ul className="mx-auto grid max-w-lg grid-cols-4">
          {[NAV[0], NAV[1], NAV[2]].map(({ to, label, icon: Icon }) => (
            <li key={to}>
              <NavLink to={to} className={({ isActive }) => cn('press grid h-[68px] place-items-center content-center gap-1 text-[11px] uppercase tracking-[0.05em]', isActive ? 'text-ink' : 'text-faint')}>
                {({ isActive }) => (<><Icon className={cn('size-6', isActive && 'text-accent')} aria-hidden /> {label}</>)}
              </NavLink>
            </li>
          ))}
          <li>
            <button type="button" onClick={() => setMore(true)} className={cn('press grid h-[68px] w-full place-items-center content-center gap-1 text-[11px] uppercase tracking-[0.05em]', ['/alternatives', '/profile'].includes(loc.pathname) ? 'text-ink' : 'text-faint')}>
              <Menu className="size-6" aria-hidden /> {S.nav.more}
            </button>
          </li>
        </ul>
      </nav>
      <Sheet open={more} onOpenChange={setMore} title={S.nav.more}>
        <div className="grid gap-2">
          {[NAV[3], NAV[4]].map(({ to, label, icon: Icon }) => (
            <button key={to} type="button" onClick={() => { setMore(false); nav(to) }} className="press flex h-14 items-center gap-3 rounded-panel border border-line px-4 text-left uppercase tracking-[0.04em] hover:bg-ink/5">
              <Icon className="size-5" aria-hidden /> {label} <MapPinned className="ml-auto size-4 opacity-0" aria-hidden />
            </button>
          ))}
        </div>
      </Sheet>
    </div>
  )
}
