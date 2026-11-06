"""Network graph, route building, re-routing (PRD §10).

Graphs are built per travel mode (rail / road / walk) as weighted ``networkx.DiGraph``s
(edge weight = ``base_minutes``). Closed edges are excluded unless asked for.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import islice

import networkx as nx

K_PATHS = 3


@dataclass
class EdgeInfo:
    id: int
    from_id: int
    to_id: int
    mode: str
    minutes: float
    km: float
    is_closed: bool
    road_name: str | None = None
    polyline: list | None = None


def build_graph(edges: list[EdgeInfo], modes: set[str], include_closed: bool = False) -> nx.DiGraph:
    g = nx.DiGraph()
    for e in edges:
        if e.mode not in modes or (e.is_closed and not include_closed):
            continue
        if g.has_edge(e.from_id, e.to_id) and g[e.from_id][e.to_id]["weight"] <= e.minutes:
            continue
        g.add_edge(e.from_id, e.to_id, weight=float(e.minutes), edge_id=e.id, km=float(e.km))
    return g


def service_modes(service_mode: str) -> set[str]:
    return {"rail"} if service_mode == "local_train" else {"road"}


def shortest_path(g: nx.DiGraph, a: int, b: int) -> list[int] | None:
    try:
        return nx.shortest_path(g, a, b, weight="weight")
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None


def k_paths(g: nx.DiGraph, a: int, b: int, k: int = K_PATHS, forbidden: set[int] | None = None):
    """First ``k`` simple paths by travel time; paths touching ``forbidden`` interior nodes are
    discarded (a re-routed bus must not revisit other stops of its own route)."""
    forbidden = forbidden or set()
    out = []
    try:
        for p in islice(nx.shortest_simple_paths(g, a, b, weight="weight"), 50):
            if any(n in forbidden for n in p[1:-1]):
                continue
            out.append(p)
            if len(out) >= k:
                break
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        pass
    return out


def path_minutes(g: nx.DiGraph, path: list[int]) -> float:
    return sum(g[u][v]["weight"] for u, v in zip(path, path[1:]))


def path_km(g: nx.DiGraph, path: list[int]) -> float:
    return sum(g[u][v]["km"] for u, v in zip(path, path[1:]))


@dataclass
class RouteStop:
    node_id: int
    is_via: bool
    arrive_at: datetime | None = None
    depart_at: datetime | None = None
    is_skipped: bool = False


def expand_route(g: nx.DiGraph, stop_ids: list[int], stop_all: bool, rail_stop_nodes: set[int]) -> list[RouteStop]:
    """Join consecutive listed stops with shortest paths. Interior nodes become ``via`` unless
    ``stop_all`` and the node is a station (local trains stop everywhere)."""
    route: list[RouteStop] = [RouteStop(stop_ids[0], False)]
    for a, b in zip(stop_ids, stop_ids[1:]):
        p = shortest_path(g, a, b)
        if p is None:
            raise ValueError(f"no path between nodes {a} and {b}")
        for n in p[1:-1]:
            route.append(RouteStop(n, not (stop_all and n in rail_stop_nodes)))
        route.append(RouteStop(b, False))
    return route


def schedule_route(route: list[RouteStop], g: nx.DiGraph, dwell_min: float, origin_depart: datetime) -> None:
    """Fill arrive/depart for every stop from edge minutes starting at ``origin_depart``."""
    t = origin_depart
    for i, s in enumerate(route):
        if i == 0:
            s.arrive_at = t
        else:
            u = route[i - 1].node_id
            t = route[i - 1].depart_at + timedelta(minutes=g[u][s.node_id]["weight"])
            s.arrive_at = t
        last = i == len(route) - 1
        s.depart_at = s.arrive_at if (last or s.is_via) else s.arrive_at + timedelta(minutes=dwell_min)


def offset_for_anchor(route: list[RouteStop], g: nx.DiGraph, dwell_min: float, anchor_node: int) -> float:
    """Minutes between origin departure and departure at ``anchor_node`` (for anchored schedules)."""
    probe = datetime(2000, 1, 1)
    schedule_route(route, g, dwell_min, probe)
    for s in route:
        if s.node_id == anchor_node:
            return (s.depart_at - probe).total_seconds() / 60
    raise ValueError("anchor node not on route")


def polyline_for_route(route_nodes: list[int], edge_geom: dict[tuple[int, int], list], node_xy: dict[int, tuple[float, float]]) -> list:
    """Concatenate edge polylines ([lng, lat]) along ``route_nodes``; straight line fallback."""
    coords: list = []
    for u, v in zip(route_nodes, route_nodes[1:]):
        seg = edge_geom.get((u, v))
        if not seg:
            seg = [[node_xy[u][1], node_xy[u][0]], [node_xy[v][1], node_xy[v][0]]]
        if coords and coords[-1] == seg[0]:
            seg = seg[1:]
        coords.extend(seg)
    if not coords and route_nodes:
        n = route_nodes[0]
        coords = [[node_xy[n][1], node_xy[n][0]]] * 2
    return coords
