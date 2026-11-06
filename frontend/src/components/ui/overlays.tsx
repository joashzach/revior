import * as DialogPrimitive from '@radix-ui/react-dialog'
import * as PopoverPrimitive from '@radix-ui/react-popover'
import * as SelectPrimitive from '@radix-ui/react-select'
import * as TabsPrimitive from '@radix-ui/react-tabs'
import * as TooltipPrimitive from '@radix-ui/react-tooltip'
import { Check, ChevronDown, X } from 'lucide-react'
import { motion, AnimatePresence } from 'motion/react'
import { forwardRef, type ComponentPropsWithoutRef, type ReactNode } from 'react'
import { Drawer } from 'vaul'
import { cn } from '@/lib/utils'
import { Button } from './button'

// ---------- Dialog (decisions that need focus: confirm reset / decline / apply)
export const Dialog = DialogPrimitive.Root
export const DialogTrigger = DialogPrimitive.Trigger

export function DialogContent({ title, description, children, className, hideClose }: { title: string; description?: string; children: ReactNode; className?: string; hideClose?: boolean }) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-off-black/40 data-[state=open]:animate-[fade-in_var(--dur-base)_var(--ease-out)]" />
      <DialogPrimitive.Content
        className={cn(
          'fixed left-1/2 top-1/2 z-50 w-[min(92vw,520px)] -translate-x-1/2 -translate-y-1/2 rounded-card-sm border border-line bg-bg p-7 shadow-pop outline-none',
          'data-[state=open]:animate-[pop-in_var(--dur-slow)_var(--ease-out)]',
          className,
        )}
      >
        <DialogPrimitive.Title className="font-serif text-[28px] leading-tight">{title}</DialogPrimitive.Title>
        {description ? (
          <DialogPrimitive.Description className="mt-2 text-[14px] text-muted">{description}</DialogPrimitive.Description>
        ) : (
          <DialogPrimitive.Description className="sr-only">{title}</DialogPrimitive.Description>
        )}
        <div className="mt-5">{children}</div>
        {!hideClose && (
          <DialogPrimitive.Close aria-label="Close" className="press absolute right-4 top-4 grid size-10 place-items-center rounded-full hover:bg-ink/6">
            <X className="size-5" />
          </DialogPrimitive.Close>
        )}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  )
}

export function ConfirmDialog({ open, onOpenChange, title, description, confirmLabel, onConfirm, danger, loading }: { open: boolean; onOpenChange: (o: boolean) => void; title: string; description?: string; confirmLabel: string; onConfirm: () => void; danger?: boolean; loading?: boolean }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={title} description={description}>
        <div className="flex flex-wrap justify-end gap-3">
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant={danger ? 'danger' : 'primary'} size="sm" onClick={onConfirm} loading={loading}>
            {confirmLabel}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

// ---------- Bottom sheet (vaul): mobile replacement for side panels
export function Sheet({ open, onOpenChange, title, description, children, tall }: { open: boolean; onOpenChange: (o: boolean) => void; title: string; description?: string; children: ReactNode; tall?: boolean }) {
  return (
    <Drawer.Root open={open} onOpenChange={onOpenChange}>
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-50 bg-off-black/40" />
        <Drawer.Content
          className={cn('fixed inset-x-0 bottom-0 z-50 mx-auto flex max-w-[640px] flex-col rounded-t-card-sm border border-b-0 border-line bg-bg outline-none', tall ? 'h-[92dvh]' : 'max-h-[88dvh]')}
        >
          <div aria-hidden className="mx-auto mt-3 h-1.5 w-12 shrink-0 rounded-full bg-line" />
          <div className="px-6 pb-2 pt-4">
            <Drawer.Title className="font-serif text-[28px] leading-tight">{title}</Drawer.Title>
            {description ? <Drawer.Description className="mt-1 text-[14px] text-muted">{description}</Drawer.Description> : <Drawer.Description className="sr-only">{title}</Drawer.Description>}
          </div>
          <div className="scroll-thin overflow-y-auto px-6 pb-6 safe-bottom">{children}</div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  )
}

/** Side panel on laptop (Radix dialog sliding from the right). */
export function SidePanel({ open, onOpenChange, title, children }: { open: boolean; onOpenChange: (o: boolean) => void; title: string; children: ReactNode }) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <AnimatePresence>
        {open && (
          <DialogPrimitive.Portal forceMount>
            <DialogPrimitive.Overlay asChild forceMount>
              <motion.div className="fixed inset-0 z-50 bg-off-black/30" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
            </DialogPrimitive.Overlay>
            <DialogPrimitive.Content asChild forceMount>
              <motion.aside
                className="scroll-thin fixed bottom-0 right-0 top-0 z-50 w-[min(96vw,560px)] overflow-y-auto border-l border-line bg-bg p-7 outline-none"
                initial={{ x: 48, opacity: 0 }}
                animate={{ x: 0, opacity: 1 }}
                exit={{ x: 24, opacity: 0, transition: { duration: 0.15 } }}
                transition={{ type: 'spring', stiffness: 400, damping: 36 }}
              >
                <DialogPrimitive.Title className="pr-10 font-serif text-[28px]">{title}</DialogPrimitive.Title>
                <DialogPrimitive.Description className="sr-only">{title}</DialogPrimitive.Description>
                <DialogPrimitive.Close aria-label="Close" className="press absolute right-4 top-4 grid size-10 place-items-center rounded-full hover:bg-ink/6">
                  <X className="size-5" />
                </DialogPrimitive.Close>
                <div className="mt-5">{children}</div>
              </motion.aside>
            </DialogPrimitive.Content>
          </DialogPrimitive.Portal>
        )}
      </AnimatePresence>
    </DialogPrimitive.Root>
  )
}

// ---------- Tabs
export const Tabs = TabsPrimitive.Root
export const TabsContent = TabsPrimitive.Content
export const TabsList = forwardRef<HTMLDivElement, ComponentPropsWithoutRef<typeof TabsPrimitive.List>>(({ className, ...p }, ref) => (
  <TabsPrimitive.List ref={ref} className={cn('scroll-thin flex gap-1 overflow-x-auto border-b border-line', className)} {...p} />
))
TabsList.displayName = 'TabsList'
export const TabsTrigger = forwardRef<HTMLButtonElement, ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>>(({ className, ...p }, ref) => (
  <TabsPrimitive.Trigger
    ref={ref}
    className={cn(
      'press relative h-11 shrink-0 px-4 text-[13px] uppercase tracking-[0.05em] text-muted transition-colors hover:text-ink',
      'data-[state=active]:text-ink after:absolute after:inset-x-3 after:-bottom-px after:h-0.5 after:rounded-full after:bg-transparent data-[state=active]:after:bg-ink',
      className,
    )}
    {...p}
  />
))
TabsTrigger.displayName = 'TabsTrigger'

// ---------- Tooltip (pointer devices only via hover-capable media)
export function Tip({ content, children }: { content: ReactNode; children: ReactNode }) {
  return (
    <TooltipPrimitive.Provider delayDuration={200}>
      <TooltipPrimitive.Root>
        <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content sideOffset={6} className="z-[60] max-w-xs rounded-xl bg-inverse px-3 py-2 text-[12px] text-on-inverse shadow-pop">
            {content}
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  )
}

// ---------- Popover
export const Popover = PopoverPrimitive.Root
export const PopoverTrigger = PopoverPrimitive.Trigger
export function PopoverContent({ className, ...p }: ComponentPropsWithoutRef<typeof PopoverPrimitive.Content>) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content sideOffset={8} className={cn('z-50 w-80 rounded-panel border border-line bg-bg p-4 shadow-pop outline-none', className)} {...p} />
    </PopoverPrimitive.Portal>
  )
}

// ---------- Select
export function Select({ value, onValueChange, options, placeholder, label, className }: { value: string | undefined; onValueChange: (v: string) => void; options: { value: string; label: string }[]; placeholder?: string; label?: string; className?: string }) {
  return (
    <SelectPrimitive.Root value={value ?? ''} onValueChange={onValueChange}>
      <SelectPrimitive.Trigger
        aria-label={label}
        className={cn('press flex h-12 w-full whitespace-nowrap items-center justify-between gap-2 rounded-panel border border-line bg-bg px-4 text-left hover:border-ink/50 data-[placeholder]:text-faint', className)}
      >
        <span className="min-w-0 flex-1 truncate"><SelectPrimitive.Value placeholder={placeholder} /></span>
        <SelectPrimitive.Icon>
          <ChevronDown className="size-4" />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content position="popper" sideOffset={6} className="z-[70] max-h-72 w-[var(--radix-select-trigger-width)] overflow-hidden rounded-panel border border-line bg-bg shadow-pop">
          <SelectPrimitive.Viewport className="scroll-thin p-1.5">
            {options.map((o) => (
              <SelectPrimitive.Item key={o.value} value={o.value} className="flex h-10 cursor-pointer select-none items-center justify-between rounded-xl px-3 text-[14px] outline-none data-[highlighted]:bg-accent-subtle">
                <SelectPrimitive.ItemText>{o.label}</SelectPrimitive.ItemText>
                <SelectPrimitive.ItemIndicator>
                  <Check className="size-4" />
                </SelectPrimitive.ItemIndicator>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  )
}
