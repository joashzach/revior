import type { PassengerState } from '@/api/types'

/** Contract §1.2 / PRD §3.2: where each passenger state belongs. Pure + unit-tested. */
export function routeForState(state: PassengerState): '/trip' | '/options' | '/status' | '/alternatives' {
  switch (state) {
    case 'REGISTERED':
    case 'BOOKED':
      return '/trip'
    case 'AFFECTED':
    case 'REOFFER':
      return '/options'
    case 'UNRESOLVED':
      return '/alternatives'
    default: // REQUESTED, HELD, CONFIRMED, WAITLISTED, RESOLVED_ALT
      return '/status'
  }
}

/** Screens the user may be viewing on purpose: never auto-navigate away from these, show a banner instead. */
export const STICKY_ROUTES = ['/why', '/profile', '/alternatives']

export function shouldAutoNavigate(currentPath: string, from: PassengerState | null, to: PassengerState): 'go' | 'banner' | 'stay' {
  const target = routeForState(to)
  if (currentPath === target) return 'stay'
  if (from === to) return 'stay'
  const onUserScreen = STICKY_ROUTES.includes(currentPath) && !(currentPath === '/alternatives' && target === '/alternatives')
  return onUserScreen ? 'banner' : 'go'
}
