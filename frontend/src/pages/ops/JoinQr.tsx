import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { Button } from '@/components/ui/button'
import { QRPanel } from '@/components/common/domain'
import { S } from '@/config/strings'
import { useLiveStore } from '@/realtime/useRealtime'

type Mode = 'corner' | 'fullscreen' | 'hidden'

/** Join QR (PRD O-4.1): corner card over the map, fullscreen overlay with live judge counter, or hidden. */
export function JoinQr({ url, mode, onMode }: { url?: string; mode: Mode; onMode: (m: Mode) => void }) {
  const judges = useLiveStore((s) => s.judgesJoined)
  useEffect(() => {
    if (mode !== 'fullscreen') return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onMode('corner')
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [mode, onMode])
  if (!url || mode === 'hidden') return null
  if (mode === 'corner')
    return (
      <div className="absolute bottom-3 right-3 z-[500] grid justify-items-center gap-2 rounded-panel border border-line bg-bg p-3 shadow-md" aria-label="Join QR">
        <QRPanel value={url} size={140} />
        <p className="max-w-[160px] text-center text-[11px] leading-snug text-muted">{S.ops.joinQr}</p>
      </div>
    )
  return createPortal(
    <div role="dialog" aria-modal="true" aria-label="Join the demo" className="fixed inset-0 z-[2000] grid place-items-center bg-bg p-6">
      <div className="grid justify-items-center gap-6 text-center">
        <h2 className="text-[clamp(2rem,1.4rem+2vw,3.5rem)]">{S.ops.joinQr}</h2>
        <QRPanel value={url} size={Math.round(Math.min(window.innerHeight * 0.62, window.innerWidth - 64))} />
        <p className="tnum text-[20px]" aria-live="polite">Judges joined: <span className="font-serif text-[32px]">{judges}</span></p>
        <Button variant="primary" size="lg" autoFocus onClick={() => onMode('corner')}>Start demo</Button>
      </div>
    </div>,
    document.body,
  )
}
