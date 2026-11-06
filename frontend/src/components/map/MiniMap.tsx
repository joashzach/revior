// Temporary stand-in; the real Leaflet mini map replaces this when the map layer is built.
export default function MiniMap(_props: { serviceId: number }) {
  return <div className="skeleton h-56 rounded-card-sm" aria-hidden />
}
