import { lazy, Suspense } from 'react'
import { createBrowserRouter, Navigate, Outlet } from 'react-router-dom'
import { ErrorBoundary } from '@/components/common/primitives'
import { SkeletonBlocks } from '@/components/common/primitives'
import { MarketingLayout, OpsAuthLayout, PassengerAuthLayout } from '@/components/layout/Shells'
import { PassengerShell } from '@/components/layout/PassengerShell'
import { Login, NotFound, OpsLogin, QrLogin } from '@/pages/Login'
import { AuthWatcher, RequireOps, RequirePassenger } from './guards'

const Landing = lazy(() => import('@/pages/Landing'))
const DemoJoin = lazy(() => import('@/pages/DemoJoin'))
const Join = lazy(() => import('@/pages/Join'))
const Trip = lazy(() => import('@/pages/Trip'))
const Options = lazy(() => import('@/pages/Options'))
const Status = lazy(() => import('@/pages/Status'))
const Why = lazy(() => import('@/pages/Why'))
const Alternatives = lazy(() => import('@/pages/Alternatives'))
const Profile = lazy(() => import('@/pages/Profile'))
const OpsDashboard = lazy(() => import('@/pages/ops/OpsDashboard'))

function Page({ children }: { children: React.ReactNode }) {
  return (
    <ErrorBoundary>
      <Suspense fallback={<SkeletonBlocks rows={2} rowClass="h-40" />}>{children}</Suspense>
    </ErrorBoundary>
  )
}
const Root = () => (<><AuthWatcher /><Outlet /></>)

export const routes = [
  {
    element: <Root />,
    children: [
      { element: <MarketingLayout />, children: [{ path: '/', element: <Page><Landing /></Page> }] },
      {
        element: <PassengerAuthLayout />,
        children: [
          { path: '/demo-join', element: <Page><DemoJoin /></Page> },
          { path: '/join', element: <Page><Join /></Page> },
          { path: '/login', element: <Login /> },
          { path: '/qr-login', element: <QrLogin /> },
        ],
      },
      {
        element: <RequirePassenger><PassengerShell /></RequirePassenger>,
        children: [
          { path: '/trip', element: <Page><Trip /></Page> },
          { path: '/options', element: <Page><Options /></Page> },
          { path: '/status', element: <Page><Status /></Page> },
          { path: '/why', element: <Page><Why /></Page> },
          { path: '/alternatives', element: <Page><Alternatives /></Page> },
          { path: '/profile', element: <Page><Profile /></Page> },
        ],
      },
      { element: <OpsAuthLayout />, children: [{ path: '/ops/login', element: <OpsLogin /> }] },
      { path: '/ops', element: <RequireOps><Page><OpsDashboard /></Page></RequireOps> },
      { path: '/app', element: <Navigate to="/trip" replace /> },
      { path: '*', element: <NotFound /> },
    ],
  },
]
export const router = createBrowserRouter(routes)
