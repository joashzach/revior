import { useEffect, useState } from 'react'

export function useMedia(query: string): boolean {
  const [m, setM] = useState(() => (typeof window !== 'undefined' ? window.matchMedia(query).matches : false))
  useEffect(() => {
    const mq = window.matchMedia(query)
    const on = () => setM(mq.matches)
    on()
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [query])
  return m
}
export const useIsDesktop = () => useMedia('(min-width: 1024px)')
export const useReducedMotion = () => useMedia('(prefers-reduced-motion: reduce)')
