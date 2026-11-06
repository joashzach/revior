import { cva, type VariantProps } from 'class-variance-authority'
import { Loader2 } from 'lucide-react'
import { forwardRef, type ButtonHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

// DESIGN.md: pill buttons (100px), mono uppercase 14px, 16px/32px padding. Blue = the single primary action per screen.
export const buttonVariants = cva(
  'press inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-button font-mono uppercase tracking-[0.04em] select-none ' +
    'disabled:cursor-not-allowed disabled:opacity-45 [&_svg]:shrink-0 [&_svg]:size-[1.1em]',
  {
    variants: {
      variant: {
        primary: 'bg-accent text-accent-contrast hover:bg-accent-hover active:bg-accent-pressed',
        dark: 'bg-inverse text-on-inverse hover:bg-ink',
        ghost: 'border border-ink bg-transparent text-ink hover:bg-ink/5',
        quiet: 'bg-transparent text-ink hover:bg-ink/6',
        danger: 'bg-danger text-white hover:brightness-95',
        link: 'rounded-md px-0 normal-case tracking-normal underline decoration-line underline-offset-4 hover:decoration-ink',
      },
      size: {
        md: 'h-12 px-8 text-[14px]',
        sm: 'h-10 px-5 text-[13px]',
        xs: 'h-8 px-3.5 text-[12px]',
        lg: 'h-14 px-10 text-[15px]',
        icon: 'size-11 p-0',
        iconSm: 'size-10 p-0',
      },
    },
    defaultVariants: { variant: 'dark', size: 'md' },
  },
)

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  loading?: boolean
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, loading, disabled, children, type = 'button', ...props }, ref) => (
    <button
      ref={ref}
      type={type}
      className={cn(buttonVariants({ variant, size }), className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading && <Loader2 className="animate-spin" aria-hidden />}
      {children}
    </button>
  ),
)
Button.displayName = 'Button'
