// Mock world: a compact Potheri corridor with OSM-verified station positions. Shapes follow contracts/examples.
import type { LineString, NetworkEdge, NodeRef, Needs, ServiceMode } from '@/api/types'

const mk = (id: number, code: string, name: string, lat: number, lng: number, hub = false, def = false, kind: NodeRef['kind'] = 'rail_station'): NodeRef => ({
  id, code, name, lat, lng, kind, is_hub: hub, is_default_hub: def,
})

export const NODES: NodeRef[] = [
  mk(1, 'POT', 'Potheri', 12.8208, 80.0369, true, true),
  mk(2, 'KTM', 'Kattankulathur', 12.8056, 80.0266, true),
  mk(3, 'GUD', 'Guduvanchery', 12.8452, 80.0577, true),
  mk(4, 'URP', 'Urapakkam', 12.8674, 80.072),
  mk(5, 'VAN', 'Vandalur', 12.8916, 80.085),
  mk(6, 'PER', 'Perungalathur', 12.9066, 80.0963),
  mk(7, 'TAM', 'Tambaram', 12.9254, 80.1169),
  mk(8, 'CHR', 'Chromepet', 12.9522, 80.1412),
  mk(9, 'PLV', 'Pallavaram', 12.9676, 80.1521),
  mk(10, 'TIR', 'Tirusulam (Airport)', 12.9805, 80.1658),
  mk(11, 'GND', 'Guindy', 13.008, 80.2131),
  mk(12, 'EGM', 'Egmore', 13.0794, 80.2628),
  mk(13, 'BCH', 'Chennai Beach', 13.0919, 80.2921),
  mk(14, 'NED', 'Nedungundram Jn', 12.8796, 80.1089, false, false, 'bus_stop'),
  mk(15, 'MUD', 'Mudichur Jn', 12.915, 80.0688, false, false, 'bus_stop'),
]
export const nodeById = (id: number) => NODES.find((n) => n.id === id)!
export const nodeByCode = (c: string) => NODES.find((n) => n.code === c)!

export const CHAIN = ['POT', 'GUD', 'URP', 'VAN', 'PER', 'TAM', 'CHR', 'PLV', 'TIR', 'GND', 'EGM', 'BCH']

const line = (codes: string[]): LineString => ({ type: 'LineString', coordinates: codes.map((c) => [nodeByCode(c).lng, nodeByCode(c).lat] as [number, number]) })
export { line as lineOf }

export function buildEdges(): NetworkEdge[] {
  const out: NetworkEdge[] = []
  let id = 1
  const add = (a: string, b: string, mode: NetworkEdge['mode'], road: string | null) =>
    out.push({ id: id++, from_node_id: nodeByCode(a).id, to_node_id: nodeByCode(b).id, mode, road_name: road, is_closed: false, polyline: line([a, b]) })
  for (let i = 0; i < CHAIN.length - 1; i++) add(CHAIN[i], CHAIN[i + 1], 'road', i > 8 ? 'Anna Salai' : 'GST Road')
  add('URP', 'NED', 'road', 'Outer Ring Road')
  add('NED', 'MUD', 'road', 'Vandalur-Kelambakkam Road')
  add('MUD', 'PER', 'road', 'Vandalur-Kelambakkam Road')
  for (let i = 0; i < CHAIN.length - 1; i++) add(CHAIN[i], CHAIN[i + 1], 'rail', null)
  return out
}

export interface MockService {
  id: number
  code: string
  label: string
  mode: ServiceMode
  stops: string[] // node codes in order
  departMin: number // minutes from t0 at origin
  durationMin: number
  seats: number
  accessibleSeats: number
  heldInit: number
  inventory: boolean
}

export const SERVICES: MockService[] = [
  { id: 1, code: 'EMU-CGL-BCH-1810', label: '6:10 PM Chengalpattu → Chennai Beach local', mode: 'local_train', stops: CHAIN, departMin: 20, durationMin: 52, seats: 0, accessibleSeats: 0, heldInit: 0, inventory: false },
  { id: 2, code: 'MTC-570A', label: 'MTC 570A Potheri → Guindy', mode: 'bus', stops: CHAIN.slice(0, 10), departMin: 15, durationMin: 62, seats: 48, accessibleSeats: 3, heldInit: 46, inventory: true },
  { id: 3, code: 'MTC-570B', label: 'MTC 570B Potheri → Guindy', mode: 'bus', stops: CHAIN.slice(0, 10), departMin: 25, durationMin: 62, seats: 40, accessibleSeats: 2, heldInit: 37, inventory: true },
  { id: 4, code: 'EXP-TAM', label: 'Express Potheri → Tambaram', mode: 'bus', stops: ['POT', 'TAM'], departMin: 20, durationMin: 34, seats: 34, accessibleSeats: 3, heldInit: 31, inventory: true },
  { id: 5, code: 'MTC-599', label: 'MTC 599 Potheri → Tambaram', mode: 'bus', stops: CHAIN.slice(0, 6), departMin: 18, durationMin: 41, seats: 14, accessibleSeats: 2, heldInit: 14, inventory: true },
  { id: 6, code: 'SHT-AIR', label: 'Airport Shuttle Potheri → Tirusulam', mode: 'shuttle', stops: ['POT', 'TAM', 'TIR'], departMin: 30, durationMin: 52, seats: 28, accessibleSeats: 3, heldInit: 25, inventory: true },
  { id: 7, code: 'CHR-EGM', label: 'Charter Potheri → Egmore', mode: 'charter_bus', stops: ['POT', 'GND', 'EGM'], departMin: 45, durationMin: 74, seats: 26, accessibleSeats: 2, heldInit: 24, inventory: true },
  { id: 8, code: 'EMU-SEAT-1945', label: '7:45 PM Potheri → Chennai Beach local (seats assured)', mode: 'local_train', stops: ['POT', 'GUD', 'URP', 'VAN', 'PER', 'TAM', 'CHR', 'PLV', 'TIR', 'GND', 'EGM', 'BCH'], departMin: 75, durationMin: 62, seats: 38, accessibleSeats: 4, heldInit: 37, inventory: true },
]

export interface PersonaDef {
  id: number
  title: string
  emoji: string
  summary: string
  name: string
  email: string
  dest: string
  party: number
  needs: Partial<Needs>
  deadlineMin?: number
}

export const PERSONAS: PersonaDef[] = [
  { id: 101, title: 'Wheelchair user → Guindy', emoji: '♿', summary: 'Needs accessible seat · travelling alone', name: 'Asha Wheeler', email: 'wheelchair-guindy@demo.revior.test', dest: 'GND', party: 1, needs: { wheelchair: true } },
  { id: 102, title: 'Family of 4 → Tambaram', emoji: '👨‍👩‍👧‍👦', summary: 'Must stay together · with children', name: 'Rao Family', email: 'family-tambaram@demo.revior.test', dest: 'TAM', party: 4, needs: { with_children: true } },
  { id: 103, title: 'Airport deadline → Tirusulam', emoji: '✈️', summary: 'Flight check-in closes soon', name: 'Nikhil Flyer', email: 'airport-deadline@demo.revior.test', dest: 'TIR', party: 1, needs: {}, deadlineMin: 95 },
  { id: 104, title: 'Elderly commuter → Chromepet', emoji: '👵', summary: 'Senior citizen · travelling alone', name: 'Kamala Devi', email: 'elderly-chromepet@demo.revior.test', dest: 'CHR', party: 1, needs: { elderly: true } },
  { id: 105, title: 'Medical appointment → Egmore', emoji: '🏥', summary: 'Hospital visit · medical priority', name: 'Imran Care', email: 'medical-egmore@demo.revior.test', dest: 'EGM', party: 1, needs: { medical: true } },
  { id: 106, title: 'Student → Chennai Beach', emoji: '🎒', summary: 'Exam in the evening · general', name: 'Sneha Student', email: 'student-beach@demo.revior.test', dest: 'BCH', party: 1, needs: {}, deadlineMin: 170 },
  { id: 107, title: 'Office commuter → Guindy', emoji: '💼', summary: 'Heading home · general', name: 'Rohit Commuter', email: 'commuter-guindy@demo.revior.test', dest: 'GND', party: 1, needs: {} },
  { id: 108, title: 'Parent with toddler → Tambaram', emoji: '👩‍🍼', summary: 'Travelling with a young child', name: 'Meera Parent', email: 'parent-tambaram@demo.revior.test', dest: 'TAM', party: 1, needs: { with_children: true } },
  { id: 109, title: 'Two friends → Chromepet', emoji: '🧑‍🤝‍🧑', summary: 'Party of 2 · general', name: 'Dev and Kiran', email: 'friends-chromepet@demo.revior.test', dest: 'CHR', party: 2, needs: {} },
  { id: 110, title: 'Night-shift worker → Chennai Beach', emoji: '🌙', summary: 'Shift starts soon · general', name: 'Farhan Shift', email: 'night-shift-beach@demo.revior.test', dest: 'BCH', party: 1, needs: {}, deadlineMin: 160 },
]
