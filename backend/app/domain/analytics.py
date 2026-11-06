"""Ops analytics (PRD F18): clusters, capacity board, allocations table, unresolved queue, fairness, map."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.domain import alternatives as alt_dom
from app.domain import simulator
from app.domain.snapshot import Snapshot, iso, linestring, seat_counts
from app.models import Allocation, Edge, Passenger, Scenario, WaitlistEntry
from app.serializers import needs_dict, passenger_out
from app.services.scenarios import cfg


def needs_class(p) -> str:
    if p.wheelchair:
        return "accessible"
    if p.medical or p.elderly or p.with_children:
        return "priority"
    return "general"


# ---------------------------------------------------------------------------------------- clusters (F18.2)
async def clusters(session: AsyncSession, sc: Scenario, snap: Snapshot) -> list[dict[str, Any]]:
    window = max(1, int(cfg(sc).get("cluster_window_minutes", 30)))
    pax = (await session.execute(select(Passenger).where(Passenger.scenario_id == sc.id, Passenger.affected_at.is_not(None)))).scalars().all()
    # capacity of options serving hub -> destination (all seat-bearing, non-cancelled services)
    cap: dict[tuple[int, int], int] = {}
    groups: dict[tuple, list[Passenger]] = defaultdict(list)
    for p in pax:
        sv = snap.services.get(p.ticket_service_id) if p.ticket_service_id else None
        stop = snap.stop_at(sv.id, p.hub_node_id) if sv else None
        base = stop.depart_at if stop else (p.affected_at or sc.t0)
        minutes = (base - sc.t0).total_seconds() / 60
        bucket = sc.t0 + timedelta(minutes=(minutes // window) * window)
        groups[(p.destination_node_id, bucket, needs_class(p))].append(p)
        key = (p.hub_node_id, p.destination_node_id)
        if key not in cap:
            cap[key] = sum(v.total_seats for sid, v in snap.services.items()
                           if v.has_seat_inventory and v.status != "cancelled" and snap.serves_in_order(sid, *key))
    out = []
    for (dest, bucket, cls), ps in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0][0], kv[0][1], kv[0][2])):
        out.append({"id": f"{dest}-{iso(bucket)}-{cls}", "destination": snap.node_ref(dest), "time_bucket_start": iso(bucket),
                    "needs_class": cls, "size": len(ps), "demand_seats": sum(p.party_size for p in ps),
                    "capacity_seats": cap.get((ps[0].hub_node_id, dest), 0)})
    return out


# ----------------------------------------------------------------------------------- capacity board (F18.3)
async def capacity_rows(session: AsyncSession, sc: Scenario, snap: Snapshot) -> list[dict[str, Any]]:
    inv = [sid for sid, v in snap.services.items() if v.has_seat_inventory]
    counts = await seat_counts(session, inv)
    wl = dict((await session.execute(select(WaitlistEntry.service_id, func.count()).where(
        WaitlistEntry.scenario_id == sc.id, WaitlistEntry.status == "active").group_by(WaitlistEntry.service_id))).all())
    rows = []
    for sid in sorted(inv, key=lambda i: (snap.services[i].depart_at, i)):
        c = counts[sid]
        rows.append({"service": snap.summary(sid), "total_seats": snap.services[sid].total_seats, "held": c["held"],
                     "confirmed": c["confirmed"], "free": max(0, c["free"]), "accessible_free": max(0, c["accessible_free"]),
                     "waitlist_len": wl.get(sid, 0)})
    return rows


# ---------------------------------------------------------------------------------- allocations table (F18.4)
async def allocations_page(session: AsyncSession, sc: Scenario, snap: Snapshot, *, status: str | None, destination: str | None,
                           needs: str | None, q: str | None, page: int, page_size: int) -> dict[str, Any]:
    stmt = select(Allocation, Passenger).join(Passenger, Passenger.id == Allocation.passenger_id).where(Allocation.scenario_id == sc.id)
    if status and status != "all":
        stmt = stmt.where(Allocation.status == status)
    elif not status:
        stmt = stmt.where(Allocation.status.in_(("held", "swap_held", "confirmed")))
    if destination:
        node = snap.nodes.get(int(destination)) if destination.isdigit() else snap.code_to_node(destination.upper())
        stmt = stmt.where(Passenger.destination_node_id == (node.id if node else -1))
    if needs:
        flag = {"wheelchair": Passenger.wheelchair, "elderly": Passenger.elderly, "medical": Passenger.medical,
                "with_children": Passenger.with_children}.get(needs)
        if flag is not None:
            stmt = stmt.where(flag)
        elif needs == "accessible":
            stmt = stmt.where(Passenger.wheelchair)
        elif needs == "priority":
            stmt = stmt.where(~Passenger.wheelchair, Passenger.medical | Passenger.elderly | Passenger.with_children)
        elif needs == "general":
            stmt = stmt.where(~Passenger.wheelchair, ~Passenger.medical, ~Passenger.elderly, ~Passenger.with_children)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(Passenger.name.ilike(like) | Passenger.ticket_id.ilike(like) | Passenger.email.ilike(like))
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar()
    rows = (await session.execute(stmt.order_by(Allocation.score.desc(), Allocation.id).offset((page - 1) * page_size).limit(page_size))).all()
    items = [{"passenger": {"id": p.id, "name": p.name, "party_size": p.party_size, "needs": needs_dict(p)},
              "score": float(a.score), "choice_rank": a.choice_rank, "service_label": snap.services[a.service_id].label,
              "status": a.status, "hold_expires_at": iso(a.hold_expires_at), "explanation": a.explanation} for a, p in rows]
    return {"items": items, "page": page, "page_size": page_size, "total": total}


# --------------------------------------------------------------------------------------- unresolved (F18.5)
async def unresolved_queue(session: AsyncSession, sc: Scenario, snap: Snapshot, limit: int = 50) -> list[dict[str, Any]]:
    now = clock.utcnow()
    pax = (await session.execute(select(Passenger).where(Passenger.scenario_id == sc.id, Passenger.state == "UNRESOLVED")
                                 .order_by(Passenger.affected_at.nulls_last(), Passenger.id).limit(limit))).scalars().all()
    out = []
    for p in pax:
        waited = (now - p.affected_at).total_seconds() / 60 if p.affected_at else 0.0
        out.append({"passenger": passenger_out(p, snap), "waited_min": round(waited, 1),
                    "alternatives": await alt_dom.generate(session, sc, snap, p)})
    return out


# ----------------------------------------------------------------------------------------- fairness (F18.6)
_FAIR = """
SELECT p.id, p.wheelchair, p.medical, p.elderly, p.with_children, p.destination_node_id, p.state,
       EXTRACT(EPOCH FROM (COALESCE(a.first_at, now()) - p.affected_at)) / 60 AS wait_min
FROM passengers p
LEFT JOIN (SELECT passenger_id, min(created_at) AS first_at FROM allocations WHERE scenario_id = :sid GROUP BY passenger_id) a
       ON a.passenger_id = p.id
WHERE p.scenario_id = :sid AND p.affected_at IS NOT NULL
"""


def _pct(xs: list[float], q: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    k = (len(xs) - 1) * q
    f, c = int(k), min(int(k) + 1, len(xs) - 1)
    return round(xs[f] + (xs[c] - xs[f]) * (k - f), 1)


def gini(xs: list[float]) -> float:
    xs = sorted(max(0.0, x) for x in xs)
    n, total = len(xs), sum(xs)
    if n == 0 or total == 0:
        return 0.0
    return round(sum((2 * (i + 1) - n - 1) * x for i, x in enumerate(xs)) / (n * total), 3)


async def fairness(session: AsyncSession, sc: Scenario, snap: Snapshot) -> dict[str, Any]:
    rows = (await session.execute(text(_FAIR), {"sid": sc.id})).mappings().all()
    placed_states = {"HELD", "CONFIRMED", "RESOLVED_ALT"}
    by_cls: dict[str, list] = defaultdict(list)
    by_dest: dict[int, list] = defaultdict(list)
    waits = []
    for r in rows:
        cls = "accessible" if r["wheelchair"] else "priority" if (r["medical"] or r["elderly"] or r["with_children"]) else "general"
        w = float(r["wait_min"] or 0)
        by_cls[cls].append((r["state"], w))
        by_dest[r["destination_node_id"]].append(r["state"])
        waits.append(w)

    def rate(states: list[str]) -> float:                # placement rate among passengers who checked in
        chk = [s for s in states if s != "AFFECTED"]
        return round(sum(1 for s in chk if s in placed_states) / len(chk), 3) if chk else 0.0
    return {
        "by_needs_class": [{"needs_class": c, "placement_rate": rate([s for s, _ in by_cls.get(c, [])]),
                            "wait_p50": _pct([w for _, w in by_cls.get(c, [])], 0.5), "wait_p90": _pct([w for _, w in by_cls.get(c, [])], 0.9)}
                           for c in ("accessible", "priority", "general")],
        "by_destination": [{"destination": snap.node_ref(d), "placement_rate": rate(sts), "unresolved": sum(1 for s in sts if s == "UNRESOLVED")}
                           for d, sts in sorted(by_dest.items(), key=lambda kv: snap.nodes[kv[0]].name)],
        "wait_gini": gini(waits),
    }


# ------------------------------------------------------------------------------------------- map (F18.7)
async def map_snapshot(session: AsyncSession, sc: Scenario, snap: Snapshot, edges: list[Edge], canonical, edge_out) -> dict[str, Any]:
    now, speed = clock.utcnow(), float(cfg(sc)["sim_speed"])
    vehicles = []
    for sid, sv in snap.services.items():
        if sv.status == "running" and sv.polyline:
            pr = simulator.progress(sv, now, speed)
            lat, lng = simulator.point_at(sv.polyline, pr)
            vehicles.append({"service_id": sid, "lat": round(lat, 6), "lng": round(lng, 6), "progress": round(pr, 4)})
    cl = Counter()
    for c in await clusters(session, sc, snap):
        cl[c["destination"]["id"]] += c["size"]
    return {"nodes": [snap.node_ref(i) for i in sorted(snap.nodes)],
            "edges": [edge_out(e) for e in canonical(edges)],
            "services": [{"id": sid, "label": sv.label, "mode": sv.mode, "status": sv.status, "polyline": linestring(sv.polyline)}
                         for sid, sv in snap.services.items()],
            "vehicles": vehicles, "clusters": [{"node_id": n, "size": s} for n, s in sorted(cl.items())]}
