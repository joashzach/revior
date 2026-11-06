import { useQuery } from '@tanstack/react-query'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { Bus, BusFront, TrainFront, X } from 'lucide-react'
import { memo, useEffect, useMemo, useRef, useState } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MapContainer, Marker, Polyline, Popup, TileLayer, Tooltip, useMap } from 'react-leaflet'
import { opsApi } from '@/api/endpoints'
import { qk } from '@/api/queryKeys'
import type { NetworkEdge, NodeRef, OpsMap, ServiceMode } from '@/api/types'
import { Button } from '@/components/ui/button'
import { env } from '@/config/env'
import { toLatLngs, midpoint, type LatLng } from '@/lib/geo'
import { cn } from '@/lib/utils'
import { useVehicleStore } from '@/realtime/bus'

type Layers = { stations: boolean; routes: boolean; vehicles: boolean; clusters: boolean }
const REDUCED = () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

const modeIcon = (mode: ServiceMode) =>
  renderToStaticMarkup(mode === 'local_train' ? <TrainFront strokeWidth={2} /> : mode === 'bus' ? <Bus strokeWidth={2} /> : <BusFront strokeWidth={2} />)
const vehicleIcon = (mode: ServiceMode) => L.divIcon({ className: '', html: `<div class="revior-vehicle">${modeIcon(mode)}</div>`, iconSize: [28, 28], iconAnchor: [14, 14] })
const pinIcon = (n: NodeRef) =>
  L.divIcon({
    className: '',
    html: `<div class="revior-pin ${n.kind === 'rail_station' ? '' : 'sq'} ${n.is_hub ? 'hub' : ''} ${n.is_default_hub ? 'default-hub' : ''}"></div>`,
    iconSize: n.is_hub ? [20, 20] : [14, 14],
    iconAnchor: n.is_hub ? [10, 10] : [7, 7],
  })
const edgeXIcon = L.divIcon({ className: '', html: '<div class="revior-edge-x" aria-label="Closed road">×</div>', iconSize: [22, 22], iconAnchor: [11, 11] })

/** Fit to the network once, and again whenever the node set changes (scenario switch). */
function FitOnce({ points }: { points: LatLng[] }) {
  const map = useMap()
  const sig = useRef('')
  useEffect(() => {
    if (points.length < 2) return
    const s = `${points.length}:${points[0]}:${points[points.length - 1]}`
    if (s === sig.current) return
    sig.current = s
    map.fitBounds(L.latLngBounds(points), { padding: [40, 40] })
  }, [map, points])
  return null
}

/** Enable wheel zoom only after the map is clicked (avoids scroll traps). */
function WheelOnFocus() {
  const map = useMap()
  useEffect(() => {
    map.scrollWheelZoom.disable()
    const on = () => map.scrollWheelZoom.enable()
    const off = () => map.scrollWheelZoom.disable()
    map.on('click', on)
    map.getContainer().addEventListener('mouseleave', off)
    return () => { map.off('click', on); map.getContainer().removeEventListener('mouseleave', off) }
  }, [map])
  return null
}

/** Vehicle markers are updated imperatively; positions glide between 1 Hz updates (no per-tick React render). */
function Vehicles({ modes, onSelect, onlyService }: { modes: Record<number, { mode: ServiceMode; label: string }>; onSelect?: (id: number) => void; onlyService?: number }) {
  const map = useMap()
  const markers = useRef(new Map<number, { m: L.Marker; from: LatLng; to: LatLng; t0: number }>())
  const modesRef = useRef(modes)
  modesRef.current = modes
  const select = useRef(onSelect)
  select.current = onSelect

  useEffect(() => {
    const reduced = REDUCED()
    const apply = (positions: Record<number, { lat: number; lng: number }>) => {
      const now = performance.now()
      for (const [k, p] of Object.entries(positions)) {
        const id = Number(k)
        if (onlyService != null && id !== onlyService) continue
        const meta = modesRef.current[id]
        if (!meta) continue
        const cur = markers.current.get(id)
        const to: LatLng = [p.lat, p.lng]
        if (!cur) {
          const m = L.marker(to, { icon: vehicleIcon(meta.mode), keyboard: false, zIndexOffset: 800 })
          m.bindTooltip(meta.label, { direction: 'top', offset: [0, -14] })
          m.on('click', () => select.current?.(id))
          m.addTo(map)
          markers.current.set(id, { m, from: to, to, t0: now })
        } else {
          const ll = cur.m.getLatLng()
          cur.from = reduced ? to : [ll.lat, ll.lng]
          cur.to = to
          cur.t0 = now
          if (reduced) cur.m.setLatLng(to)
        }
      }
    }
    apply(useVehicleStore.getState().positions)
    const unsub = useVehicleStore.subscribe((s) => apply(s.positions))
    let raf = 0
    const ease = (t: number) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2)
    const tick = () => {
      const now = performance.now()
      markers.current.forEach((v) => {
        const t = Math.min(1, (now - v.t0) / 1000)
        if (t < 1 && !reduced) v.m.setLatLng([v.from[0] + (v.to[0] - v.from[0]) * ease(t), v.from[1] + (v.to[1] - v.from[1]) * ease(t)])
        else if (t >= 1) v.m.setLatLng(v.to)
      })
      raf = requestAnimationFrame(tick)
    }
    if (!reduced) raf = requestAnimationFrame(tick)
    const live = markers.current
    return () => { unsub(); cancelAnimationFrame(raf); live.forEach((v) => v.m.remove()); live.clear() }
  }, [map, onlyService])
  return null
}

/** One service route. When the geometry changes (re-route) the old line fades and the new one draws in. */
const ServiceLine = memo(function ServiceLine({ id, status, label, positions, onSelect }: { id: number; status: string; label: string; positions: LatLng[]; onSelect?: (id: number) => void }) {
  const key = positions.length + ':' + positions[0]?.join() + ':' + positions[positions.length - 1]?.join() + ':' + positions[Math.floor(positions.length / 2)]?.join()
  const prev = useRef<{ key: string; pos: LatLng[] }>({ key, pos: positions })
  const [ghost, setGhost] = useState<LatLng[] | null>(null)
  const [drawing, setDrawing] = useState(false)
  const ref = useRef<L.Polyline | null>(null)
  useEffect(() => {
    if (prev.current.key === key) return
    setGhost(prev.current.pos)
    setDrawing(true)
    prev.current = { key, pos: positions }
    const a = setTimeout(() => setGhost(null), 500)
    const b = setTimeout(() => setDrawing(false), 750)
    return () => { clearTimeout(a); clearTimeout(b) }
  }, [key, positions])
  useEffect(() => { ref.current?.getElement()?.setAttribute('pathLength', '1') }, [drawing, positions, status])
  return (
    <>
      {ghost && <Polyline positions={ghost} pathOptions={{ className: 'rv-line rv-line-ghost rv-line-rerouted' }} interactive={false} />}
      <Polyline key={`${status}-${drawing ? 'draw' : 'still'}`} ref={ref} positions={positions} pathOptions={{ className: `rv-line rv-line-${status} ${drawing ? 'rv-line-draw' : ''}` }} eventHandlers={{ click: () => onSelect?.(id) }}>
        <Tooltip sticky>{label} · {status}</Tooltip>
      </Polyline>
    </>
  )
})

const Edge = memo(function Edge({ e, names, onClose }: { e: NetworkEdge; names: Map<number, string>; onClose?: (id: number) => void }) {
  const pos = useMemo(() => toLatLngs(e.polyline), [e.polyline])
  const mid = midpoint(pos)
  if (e.mode === 'walk') return null
  return (
    <>
      {/* Leaflet reads className only when a path is created, so the key remounts it when the edge opens or closes */}
      <Polyline key={e.is_closed ? 'closed' : 'open'} positions={pos} pathOptions={{ className: e.is_closed ? 'rv-edge-closed' : 'rv-edge' }} interactive={false} />
      {!e.is_closed && e.mode === 'road' && (
        <Polyline positions={pos} pathOptions={{ className: 'rv-edge-hit' }}>
          <Popup>
            <div className="grid gap-2 p-1">
              <p className="font-medium">{e.road_name ?? 'Road'}</p>
              <p className="text-[12px] text-muted">{names.get(e.from_node_id) ?? '?'} → {names.get(e.to_node_id) ?? '?'}</p>
              <Button size="xs" variant="danger" onClick={() => onClose?.(e.id)}>Close this road</Button>
            </div>
          </Popup>
        </Polyline>
      )}
      {e.is_closed && mid && <Marker position={mid} icon={edgeXIcon} interactive={false} />}
    </>
  )
})

export const LEGEND: { cls: string; label: string }[] = [
  { cls: 'bg-info', label: 'Scheduled' },
  { cls: 'bg-accent', label: 'Running' },
  { cls: 'bg-warning', label: 'Delayed' },
  { cls: 'bg-danger', label: 'Cancelled or road closed' },
  { cls: 'bg-success', label: 'Re-routed' },
]

function Legend({ layers, setLayers }: { layers: Layers; setLayers: (l: Layers) => void }) {
  const [open, setOpen] = useState(true)
  const names: [keyof Layers, string][] = [['stations', 'Stations'], ['routes', 'Routes'], ['vehicles', 'Vehicles'], ['clusters', 'Stranded groups']]
  return (
    <div className="absolute bottom-3 left-3 z-[500] max-w-[260px] rounded-panel border border-line bg-bg/95 p-3 text-[12px] backdrop-blur-sm">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex w-full items-center justify-between gap-3 text-left uppercase tracking-[0.06em] text-muted">
        Legend {open ? <X className="size-3.5" aria-hidden /> : <span aria-hidden>+</span>}
      </button>
      {open && (
        <>
          <ul className="mt-2 grid gap-1">{LEGEND.map((l) => <li key={l.label} className="flex items-center gap-2"><span className={cn('h-1 w-5 rounded-full', l.cls)} aria-hidden />{l.label}</li>)}</ul>
          <div className="mt-3 grid gap-1 border-t border-line pt-2">
            {names.map(([k, n]) => (
              <label key={k} className="flex min-h-6 cursor-pointer items-center gap-2"><input type="checkbox" checked={layers[k]} onChange={(e) => setLayers({ ...layers, [k]: e.target.checked })} className="accent-[var(--accent)]" />{n}</label>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

export function ReviorMap({ onSelectService, onCloseEdge, className, children }: { onSelectService?: (id: number) => void; onCloseEdge?: (id: number) => void; className?: string; children?: React.ReactNode }) {
  const q = useQuery({ queryKey: qk.ops.map, queryFn: opsApi.map, staleTime: 10_000 })
  const [layers, setLayers] = useState<Layers>({ stations: true, routes: true, vehicles: true, clusters: true })
  const data: OpsMap | undefined = q.data
  const points = useMemo(() => (data?.nodes ?? []).map((n): LatLng => [n.lat, n.lng]), [data?.nodes])
  const modes = useMemo(() => Object.fromEntries((data?.services ?? []).map((s) => [s.id, { mode: s.mode, label: s.label }])), [data?.services])
  const nodeName = useMemo(() => new Map((data?.nodes ?? []).map((n) => [n.id, n.name])), [data?.nodes])
  const nodeById = useMemo(() => new Map((data?.nodes ?? []).map((n) => [n.id, n])), [data?.nodes])
  const lines = useMemo(() => (data?.services ?? []).map((s) => ({ ...s, positions: toLatLngs(s.polyline) })), [data?.services])
  return (
    <div className={cn('revior-map relative isolate overflow-hidden rounded-card-sm border border-line', className)}>
      <MapContainer center={[12.9, 80.1]} zoom={10} className="h-full w-full" zoomControl attributionControl>
        <TileLayer url={env.tileUrl} attribution={env.attribution} />
        <WheelOnFocus />
        <FitOnce points={points} />
        {data?.edges.map((e) => <Edge key={e.id} e={e} names={nodeName} onClose={onCloseEdge} />)}
        {layers.routes && lines.map((s) => <ServiceLine key={s.id} id={s.id} status={s.status} label={s.label} positions={s.positions} onSelect={onSelectService} />)}
        {layers.stations && data?.nodes.map((n) => (
          <Marker key={n.id} position={[n.lat, n.lng]} icon={pinIcon(n)} keyboard={false}>
            <Tooltip direction="top" offset={[0, -8]} permanent={n.is_default_hub} className={n.is_default_hub ? 'revior-label' : undefined}>{n.name}</Tooltip>
          </Marker>
        ))}
        {layers.clusters && data?.clusters.map((c) => {
          const n = nodeById.get(c.node_id)
          if (!n || c.size <= 0) return null
          const r = Math.min(34, 12 + Math.sqrt(c.size) * 2.2)
          return (
            <Marker key={c.node_id} position={[n.lat, n.lng]} interactive={false}
              icon={L.divIcon({ className: '', html: `<div class="revior-cluster" style="width:${r * 2}px;height:${r * 2}px" aria-label="${c.size} stranded at ${n.name}">${c.size}</div>`, iconSize: [r * 2, r * 2], iconAnchor: [r, r] })} />
          )
        })}
        {layers.vehicles && <Vehicles modes={modes} onSelect={onSelectService} />}
      </MapContainer>
      <Legend layers={layers} setLayers={setLayers} />
      {children}
      {q.isLoading && <div className="absolute inset-0 z-[600] grid place-items-center bg-bg/60 text-[13px] text-muted">Loading map…</div>}
    </div>
  )
}

/** Passenger mini-map (PRD §10.6): own route + own vehicle + hub/destination, static unless opened full-screen. */
export function MiniMapView({ polyline, serviceId, serviceLabel, mode, hub, destination, interactive, className }: { polyline: [number, number][] | null; serviceId: number; serviceLabel: string; mode: ServiceMode; hub: NodeRef; destination: NodeRef; interactive?: boolean; className?: string }) {
  const positions = useMemo(() => toLatLngs(polyline ? { coordinates: polyline } : null), [polyline])
  const pts = useMemo<LatLng[]>(() => (positions.length ? positions : [[hub.lat, hub.lng], [destination.lat, destination.lng]]), [positions, hub, destination])
  const modes = useMemo(() => ({ [serviceId]: { mode, label: serviceLabel } }), [serviceId, mode, serviceLabel])
  return (
    <div className={cn('revior-map relative isolate overflow-hidden rounded-card-sm border border-line', className)}>
      <MapContainer bounds={L.latLngBounds(pts)} boundsOptions={{ padding: [28, 28] }} className="h-full w-full" zoomControl={!!interactive} dragging={!!interactive} scrollWheelZoom={false} doubleClickZoom={!!interactive} touchZoom={!!interactive} keyboard={!!interactive}>
        <TileLayer url={env.tileUrl} attribution={env.attribution} />
        <Polyline positions={pts} pathOptions={{ className: 'rv-line rv-line-approx' }} interactive={false} />
        {[hub, destination].map((n) => <Marker key={n.id} position={[n.lat, n.lng]} icon={pinIcon({ ...n, is_hub: true })} keyboard={false}><Tooltip permanent direction="top" offset={[0, -8]} className="revior-label">{n.name}</Tooltip></Marker>)}
        <Vehicles modes={modes} onlyService={serviceId} />
      </MapContainer>
    </div>
  )
}
