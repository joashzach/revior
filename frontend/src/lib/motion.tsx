import { LazyMotion } from 'motion/react'
import type { ReactNode } from 'react'

/** Animation features load after first paint (domMax: layout + gestures), so the entry bundle stays small. */
const features = () => import('./motionFeatures').then((m) => m.default)
export const MotionProvider = ({ children }: { children: ReactNode }) => <LazyMotion features={features}>{children}</LazyMotion>
