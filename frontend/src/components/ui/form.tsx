import * as CheckboxPrimitive from '@radix-ui/react-checkbox'
import * as SwitchPrimitive from '@radix-ui/react-switch'
import * as SliderPrimitive from '@radix-ui/react-slider'
import { Check } from 'lucide-react'
import { forwardRef, useId, type InputHTMLAttributes, type ReactNode, type TextareaHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

const field =
  'w-full rounded-panel border border-line bg-bg px-4 text-ink placeholder:text-faint transition-[border-color,box-shadow] duration-150 ' +
  'hover:border-ink/50 focus-visible:border-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ' +
  'disabled:cursor-not-allowed disabled:opacity-50 aria-[invalid=true]:border-danger aria-[invalid=true]:shake-once'

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(({ className, ...p }, ref) => (
  <input ref={ref} className={cn(field, 'h-12', className)} {...p} />
))
Input.displayName = 'Input'

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(({ className, ...p }, ref) => (
  <textarea ref={ref} className={cn(field, 'min-h-24 py-3', className)} {...p} />
))
Textarea.displayName = 'Textarea'

/** Always-visible label + help + inline error (skill §7: no placeholder-as-label). */
export function Field({ label, hint, error, children, htmlFor, className }: { label: string; hint?: string; error?: unknown; children: (id: string, describedBy?: string) => ReactNode; htmlFor?: string; className?: string }) {
  const auto = useId()
  const id = htmlFor ?? auto
  const desc = error ? `${id}-err` : hint ? `${id}-hint` : undefined
  return (
    <div className={cn('grid gap-1.5', className)}>
      <label htmlFor={id} className="text-[14px] font-medium">
        {label}
      </label>
      {children(id, desc)}
      {error ? (
        <p id={`${id}-err`} role="alert" className="text-[13px] text-danger-fg">
          {String(error)}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-[13px] text-muted">
          {hint}
        </p>
      ) : null}
    </div>
  )
}

export const Switch = forwardRef<HTMLButtonElement, SwitchPrimitive.SwitchProps>(({ className, ...p }, ref) => (
  <SwitchPrimitive.Root
    ref={ref}
    className={cn(
      'press relative h-7 w-12 shrink-0 cursor-pointer rounded-pill border border-ink/30 bg-line transition-colors data-[state=checked]:border-accent data-[state=checked]:bg-accent',
      'disabled:cursor-not-allowed disabled:opacity-50',
      className,
    )}
    {...p}
  >
    <SwitchPrimitive.Thumb className="block size-5 translate-x-1 rounded-full bg-bg shadow-pop transition-transform duration-150 data-[state=checked]:translate-x-[23px]" />
  </SwitchPrimitive.Root>
))
Switch.displayName = 'Switch'

export const Checkbox = forwardRef<HTMLButtonElement, CheckboxPrimitive.CheckboxProps>(({ className, ...p }, ref) => (
  <CheckboxPrimitive.Root
    ref={ref}
    className={cn('grid size-6 shrink-0 place-items-center rounded-lg border border-ink/60 bg-bg data-[state=checked]:border-accent data-[state=checked]:bg-accent data-[state=checked]:text-accent-contrast', className)}
    {...p}
  >
    <CheckboxPrimitive.Indicator>
      <Check className="size-4" strokeWidth={2.5} />
    </CheckboxPrimitive.Indicator>
  </CheckboxPrimitive.Root>
))
Checkbox.displayName = 'Checkbox'

export function Slider({ className, ...p }: SliderPrimitive.SliderProps) {
  return (
    <SliderPrimitive.Root className={cn('relative flex h-8 w-full touch-none select-none items-center', className)} {...p}>
      <SliderPrimitive.Track className="relative h-1.5 grow rounded-full bg-line">
        <SliderPrimitive.Range className="absolute h-full rounded-full bg-ink" />
      </SliderPrimitive.Track>
      <SliderPrimitive.Thumb aria-label={p['aria-label']} className="block size-5 rounded-full border-2 border-ink bg-bg shadow-pop focus-visible:outline-2 focus-visible:outline-accent" />
    </SliderPrimitive.Root>
  )
}
