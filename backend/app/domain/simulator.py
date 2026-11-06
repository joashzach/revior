"""Simulator (PRD F20): vehicle positions along polylines + schedule-driven status transitions."""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.domain.snapshot import Snapshot
from app.domain.tickets import haversine_km
from app.models import Allocation, Passenger, Scenario, WaitlistEntry
from app.services.scenarios import cfg
from app.ws.events import Event, ev

LIVE = ("scheduled", "delayed", "rerouted", "running")


def point_at(coords: list[list[float]], frac: float) -> tuple[float, float]:
    """(lat, lng) at ``frac`` (0..1) of the polyline's length; coords are [lng, lat]."""
    if not coords:
        return 0.0, 0.0
    if len(coords) == 1 or frac <= 0:
        return coords[0][1], coords[0][0]
    if frac >= 1:
        return coords[-1][1], coords[-1][0]
    segs = [haversine_km(a[1], a[0], b[1], b[0]) for a, b in zip(coords, coords[1:])]
    total = sum(segs) or 1e-9
    target, acc = frac * total, 0.0
    for (a, b), d in zip(zip(coords, coords[1:]), segs):
        if acc + d >= target:
            t = (target - acc) / d if d else 0.0
            return a[1] + (b[1] - a[1]) * t, a[0] + (b[0] - a[0]) * t
        acc += d
    return coords[-1][1], coords[-1][0]


def progress(sv, now: datetime, sim_speed: float) -> float:
    """Visual progress; movement is accelerated by ``sim_speed`` (ETAs and timers stay real time)."""
    from datetime import timedelta
    dep = sv.depart_at + timedelta(minutes=sv.delay_minutes or 0)
    arr = sv.arrive_at + timedelta(minutes=sv.delay_minutes or 0)
    dur = max(1.0, (arr - dep).total_seconds())
    return max(0.0, min(1.0, ((now - dep).total_seconds() * sim_speed) / dur))


async def transitions(session: AsyncSession, sc: Scenario, snap: Snapshot, now: datetime) -> list[Event]:
    """scheduled -> running at departure, running -> completed at arrival. A departing service drops its
    waitlist and its unclaimed holds expire (F20.2)."""
    from datetime import timedelta
    events: list[Event] = []
    departed: list[int] = []
    for sid, sv in snap.services.items():
        if sv.status in ("cancelled", "completed"):
            continue
        dep = sv.depart_at + timedelta(minutes=sv.delay_minutes or 0)
        arr = sv.arrive_at + timedelta(minutes=sv.delay_minutes or 0)
        new = None
        if now >= arr:
            new = "completed"
        elif now >= dep and sv.status in ("scheduled", "delayed", "rerouted"):
            new = "running"
        if new is None or new == sv.status:
            continue
        if sv.status in ("scheduled", "delayed", "rerouted") and new in ("running", "completed"):
            departed.append(sid)
        sv.status = new
        events.append(ev("service.status_changed", {"service_id": sid, "status": new, "delay_minutes": sv.delay_minutes}, ops=True))
    if departed:
        from app.domain import holds as holds_dom
        # drop waitlists of departed services
        await session.execute(delete(WaitlistEntry).where(WaitlistEntry.service_id.in_(departed)))
        # unclaimed holds on departed services lapse: expire them right away through the normal expiry path
        from sqlalchemy import update
        await session.execute(update(Allocation).where(Allocation.service_id.in_(departed), Allocation.status.in_(("held", "swap_held")))
                              .values(hold_expires_at=now - timedelta(seconds=1)))
        events += await holds_dom.expire_due(session, sc, now)
    return events


async def positions(session: AsyncSession, sc: Scenario, snap: Snapshot, now: datetime,
                    connected_passengers: list[int]) -> list[Event]:
    speed = float(cfg(sc)["sim_speed"])
    items = []
    for sid, sv in snap.services.items():
        if sv.status != "running" or not sv.polyline:
            continue
        pr = progress(sv, now, speed)
        lat, lng = point_at(sv.polyline, pr)
        items.append({"service_id": sid, "lat": round(lat, 6), "lng": round(lng, 6), "progress": round(pr, 4)})
    if not items:
        return []
    events = [ev("vehicle.positions", {"items": items}, ops=True, kpi=False)]
    if connected_passengers:
        by = {i["service_id"]: i for i in items}
        mine: dict[int, set[int]] = defaultdict(set)
        for pid, sid in (await session.execute(select(Allocation.passenger_id, Allocation.service_id).where(
                Allocation.passenger_id.in_(connected_passengers), Allocation.status.in_(("held", "confirmed"))))).all():
            mine[pid].add(sid)
        for pid, sid in (await session.execute(select(Passenger.id, Passenger.ticket_service_id).where(
                Passenger.id.in_(connected_passengers)))).all():
            if sid:
                mine[pid].add(sid)
        for pid, sids in mine.items():
            own = [by[s] for s in sids if s in by]
            if own:
                events.append(ev("vehicle.positions", {"items": own}, to=[pid], kpi=False))
    return events
