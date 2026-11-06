import { cn } from '@/lib/utils'

/** Wordmark: typographic only (DESIGN.md serif, weight 400). No generated logo. */
export function ReviorLogo({ className, size = 'md' }: { className?: string; size?: 'sm' | 'md' | 'lg' }) {
  const px = { sm: 'text-[26px]', md: 'text-[32px]', lg: 'text-[44px]' }[size]
  return (
    <span className={cn('inline-flex items-baseline gap-0.5 font-serif leading-none tracking-[-0.02em]', px, className)} aria-label="Revior">
      Revior<span aria-hidden className="text-accent">.</span>
    </span>
  )
}

export function Tagline({ className }: { className?: string }) {
  return <p className={cn('text-[14px] text-muted', className)}>Passengers choose. Revior decides fairly. Every decision is explainable.</p>
}
