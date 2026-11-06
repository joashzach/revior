import { create } from 'zustand'
import { tokens } from '@/api/http'

/** Mirrors the two token keys in localStorage (kept separate: the presenter laptop may hold both). */
interface Session {
  passenger: string | null
  ops: string | null
  setPassenger: (t: string | null) => void
  setOps: (t: string | null) => void
  refresh: () => void
}

export const useSession = create<Session>((set) => ({
  passenger: tokens.get('passenger'),
  ops: tokens.get('ops'),
  setPassenger: (t) => {
    if (t) tokens.set('passenger', t)
    else tokens.clear('passenger')
    set({ passenger: t })
  },
  setOps: (t) => {
    if (t) tokens.set('ops', t)
    else tokens.clear('ops')
    set({ ops: t })
  },
  refresh: () => set({ passenger: tokens.get('passenger'), ops: tokens.get('ops') }),
}))
