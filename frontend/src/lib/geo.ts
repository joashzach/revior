import type { LineString } from '@/api/types'

export type LatLng = [number, number]

/**
 * GeoJSON LineString coordinates from the backend are [lng, lat]; Leaflet wants [lat, lng].
 * This is the ONLY place that conversion happens (unit-tested).
 */
export function toLatLngs(line: LineString | { coordinates: number[][] } | null | undefined): LatLng[] {
  if (!line?.coordinates) return []
  return line.coordinates.filter((c) => c.length >= 2).map(([lng, lat]) => [lat, lng] as LatLng)
}

export const nodeLatLng = (n: { lat: number; lng: number }): LatLng => [n.lat, n.lng]

/** Midpoint along the vertex list (good enough for an icon on an edge). */
export function midpoint(points: LatLng[]): LatLng | null {
  if (!points.length) return null
  return points[Math.floor(points.length / 2)]
}

/** Length of a [lat,lng] polyline in metres (for dash animation). */
export function approxLength(points: LatLng[]): number {
  let d = 0
  for (let i = 1; i < points.length; i++) {
    const [a, b] = [points[i - 1], points[i]]
    d += Math.hypot((b[0] - a[0]) * 111_000, (b[1] - a[1]) * 111_000 * Math.cos((a[0] * Math.PI) / 180))
  }
  return d
}
