import { useStatus } from '@/hooks/queries'
import { MiniMapView } from './ReviorMap'

/** Passenger mini-map. The passenger API exposes no route geometry, so the line is origin → destination (see report). */
export default function MiniMap({ serviceId }: { serviceId: number }) {
  const st = useStatus()
  const s = st.data?.allocation?.service
  if (!s || s.id !== serviceId) return <div className="skeleton h-56 rounded-card-sm" aria-hidden />
  return (
    <figure className="grid gap-2">
      <MiniMapView className="h-56" polyline={null} serviceId={s.id} serviceLabel={s.label} mode={s.mode} hub={s.origin} destination={s.destination} />
      <figcaption className="text-[12px] text-muted">Your vehicle appears here once it is moving. The line is a straight guide, not the road.</figcaption>
    </figure>
  )
}
