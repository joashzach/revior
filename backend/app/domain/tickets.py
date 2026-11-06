"""Destinations, hub detection and virtual-ticket assignment (PRD F2.1, F3, F4.1, D9)."""
from __future__ import annotations

import math
import secrets
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.snapshot import Snapshot
from app.models import Passenger, Service


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dl = p2 - p1, math.radians(lng2 - lng1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def destinations_from(snap: Snapshot, hub_id: int, q: str | None = None) -> list[int]:
    """Nodes that some service reaches *after* the hub (stop order respected), searchable by ``q``."""
    out: set[int] = set()
    for sid in snap.services:
        served = [s.node_id for s in snap.served(sid)]
        if hub_id in served:
            out.update(served[served.index(hub_id) + 1:])
    nodes = [snap.nodes[i] for i in out if i != hub_id]
    if q:
        ql = q.strip().lower()
        nodes = [n for n in nodes if ql in n.name.lower() or ql in n.code.lower()]
    return [n.id for n in sorted(nodes, key=lambda n: n.name)]


def hub_ids(snap: Snapshot) -> list[int]:
    return [n.id for n in snap.nodes.values() if n.is_hub]


def assign_ticket_service(snap: Snapshot, hub_id: int, dest_id: int, now: datetime) -> Service | None:
    """Featured service if it serves hub -> destination; else the next scheduled local that does;
    else any non-cancelled service that does."""
    sc = snap.scenario
    feat = snap.services.get(sc.featured_service_id) if sc.featured_service_id else None
    if feat and snap.serves_in_order(feat.id, hub_id, dest_id):
        return feat

    def candidates(locals_only: bool):
        out = []
        for sid, sv in snap.services.items():
            if sv.status in ("cancelled", "completed"):
                continue
            if locals_only and not (sv.mode == "local_train" and not sv.has_seat_inventory):
                continue
            pair = snap.serves_in_order(sid, hub_id, dest_id)
            if pair and snap.effective(pair[0].depart_at, sid) >= now:
                out.append((snap.effective(pair[0].depart_at, sid), sid))
        return [snap.services[sid] for _, sid in sorted(out)]

    return next(iter(candidates(True)), None) or next(iter(candidates(False)), None)


async def new_ticket_id(session: AsyncSession, scenario_id: int) -> str:
    while True:
        tid = f"VT-{secrets.token_hex(3).upper()}"
        exists = (await session.execute(
            select(Passenger.id).where(Passenger.scenario_id == scenario_id, Passenger.ticket_id == tid))).first()
        if not exists:
            return tid
