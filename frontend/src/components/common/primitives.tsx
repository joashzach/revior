import { AlertCircle, Inbox, RefreshCw } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { Component, type ErrorInfo, type ReactNode } from 'react'
import { S } from '@/config/strings'
import { useConnStore } from '@/realtime/bus'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'

// ---------- LiveDot
export function LiveDot({ className, showLabel = true }: { className?: string; showLabel?: boolean }) {
  const state = useConnStore((s) => s.state)
  const map = {
    connected: { c: 'bg-success', t: S.common.connected },
    connecting: { c: 'bg-warning', t: S.common.reconnecting },
    reconnecting: { c: 'bg-warning', t: S.common.reconnecting },
    offline: { c: 'bg-danger', t: S.common.offline },
  }[state]
  return (
    <span className={cn('inline-flex items-center gap-2 text-[12px] uppercase tracking-[0.06em] text-muted', className)} role="status" aria-live="polite">
      <span className="relative flex size-2.5">
        {state === 'connected' && <span className="absolute inline-flex size-full animate-ping rounded-full bg-success opacity-40 motion-reduce:hidden" />}
        <span className={cn('relative inline-flex size-2.5 rounded-full', map.c)} />
      </span>
      {showLabel ? map.t : <span className="sr-only">{map.t}</span>}
    </span>
  )
}

// ---------- NumberRoll (digit pop-in, tabular nums). Batches visual change; respects reduced motion via CSS tokens.
export function NumberRoll({ value, className, suffix }: { value: number | string; className?: string; suffix?: string }) {
  const text = typeof value === 'number' ? value.toLocaleString('en-IN') : value
  return (
    <span className={cn('tnum relative inline-flex overflow-hidden align-baseline', className)}>
      <span className="sr-only">{text}{suffix}</span>
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.span
          key={text}
          initial={{ y: 10, opacity: 0, filter: 'blur(3px)' }}
          animate={{ y: 0, opacity: 1, filter: 'blur(0px)' }}
          exit={{ y: -8, opacity: 0, filter: 'blur(2px)', transition: { duration: 0.12 } }}
          transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          aria-hidden
       >
          {text}
          {suffix}
        </motion.span>
      </AnimatePresence>
    </span>
  )
}

// ---------- Skeletons
export const Skeleton = ({ className }: { className?: string }) => <div aria-hidden className={cn('skeleton', className)} />
export function SkeletonBlocks({ rows = 3, className, rowClass = 'h-24' }: { rows?: number; className?: string; rowClass?: string }) {
  return (
    <div className={cn('grid gap-3', className)} role="status" aria-label={S.common.loading}>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className={cn('w-full rounded-card-sm', rowClass)} />
      ))}
    </div>
  )
}

// ---------- Empty / Error
export function EmptyState({ title, body, action, icon: Icon = Inbox, className }: { title: string; body?: string; action?: ReactNode; icon?: typeof Inbox; className?: string }) {
  return (
    <div className={cn('grid place-items-center gap-3 rounded-card-sm border border-dashed border-line px-6 py-12 text-center', className)}>
      <Icon className="size-7 text-faint" aria-hidden />
      <h3 className="text-[24px]">{title}</h3>
      {body && <p className="max-w-[46ch] text-[14px] text-muted">{body}</p>}
      {action}
    </div>
  )
}

export function ErrorState({ title = 'Could not load this', body, onRetry, className }: { title?: string; body?: string; onRetry?: () => void; className?: string }) {
  return (
    <div role="alert" className={cn('grid place-items-center gap-3 rounded-card-sm border border-danger/30 bg-danger-bg px-6 py-10 text-center text-danger-fg', className)}>
      <AlertCircle className="size-7" aria-hidden />
      <h3 className="text-[24px]">{title}</h3>
      {body && <p className="max-w-[46ch] text-[14px]">{body}</p>}
      {onRetry && (
        <Button variant="dark" size="sm" onClick={onRetry}>
          <RefreshCw /> {S.common.retry}
        </Button>
      )}
    </div>
  )
}

export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }
  static getDerivedStateFromError(error: Error) {
    return { error }
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack)
  }
  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="mx-auto grid min-h-[60dvh] max-w-xl place-items-center p-6">
        <div role="alert" className="grid gap-4 text-center">
          <h2 className="text-[40px]">{S.errors.boundaryTitle}</h2>
          <p className="text-muted">{S.errors.boundaryBody}</p>
          <div>
            <Button variant="dark" onClick={() => window.location.reload()}>
              {S.common.reload}
            </Button>
          </div>
        </div>
      </div>
    )
  }
}

// ---------- Section heading used across screens
export function SectionHeading({ eyebrow, title, right, className }: { eyebrow?: string; title: string; right?: ReactNode; className?: string }) {
  return (
    <div className={cn('flex flex-wrap items-end justify-between gap-3', className)}>
      <div className="grid gap-1">
        {eyebrow && <span className="eyebrow">{eyebrow}</span>}
        <h2 className="text-[32px] sm:text-[40px]">{title}</h2>
      </div>
      {right}
    </div>
  )
}
