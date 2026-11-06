"""Add capacity (PRD F15): operator creates a charter/shuttle, then unresolved/waitlisted units are re-allocated."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.dbutil import bulk
from app.domain import batches as batches_dom
from app.domain import routing as rt
from app.domain.disruption import edge_infos, load_edges
from app.domain.snapshot import Snapshot, iso
from app.domain.state import bulk_transition
from app.errors import AppError
from app.models import Passenger, Request, Scenario, Seat, Service, ServiceStop
from app.services import audit
from app.services.scenarios import cfg
from app.ws.events import Event, ev


async def create_service(session: AsyncSession, sc: Scenario, *, label: str, mode: str, stop_node_ids: list[int],
                         depart_in_minutes: int, total_seats: int, accessible_seats: int) -> tuple[Service, list[Event]]:
    now = clock.utcnow()
    snap = await Snapshot.load(session, sc)
    for n in stop_node_ids:
        if n not in snap.nodes:
            raise AppError("VALIDATION_ERROR", "Unknown stop", {"fields": {"stop_node_ids": f"unknown node {n}"}})
    edges = await load_edges(session, sc, polylines=True)
    infos = edge_infos(edges)
    g = rt.build_graph(infos, {"road"})
    station_ids = {n.id for n in snap.nodes.values() if n.kind == "rail_station"}
    try:
        route = rt.expand_route(g, stop_node_ids, False, station_ids)
    except ValueError as exc:
        raise AppError("VALIDATION_ERROR", f"No open road path along those stops ({exc})", {"fields": {"stop_node_ids": "not connected"}})
    rt.schedule_route(route, g, 1.0, now + timedelta(minutes=depart_in_minutes))
    node_xy = {n.id: (n.lat, n.lng) for n in snap.nodes.values()}
    geom = {(e.from_node_id, e.to_node_id): e.polyline for e in edges if e.mode == "road"}
    n_ops = (await session.execute(select(func.count()).select_from(Service).where(
        Service.scenario_id == sc.id, Service.created_by == "operator"))).scalar() or 0
    sv = Service(scenario_id=sc.id, code=f"OPS-{n_ops + 1:03d}", label=label, mode=mode, status="scheduled",
                 has_seat_inventory=True, total_seats=total_seats, accessible_seats=accessible_seats,
                 depart_at=route[0].depart_at, arrive_at=route[-1].arrive_at,
                 polyline=rt.polyline_for_route([r.node_id for r in route], geom, node_xy), created_by="operator", version=1)
    session.add(sv)
    await session.flush()
    await bulk(session, ServiceStop, [dict(service_id=sv.id, seq=i, node_id=r.node_id, arrive_at=r.arrive_at, depart_at=r.depart_at,
                                           is_skipped=False, is_via=r.is_via) for i, r in enumerate(route)])
    seats = [dict(service_id=sv.id, seat_no=f"W{i:02d}", is_accessible=True, status="free") for i in range(1, accessible_seats + 1)]
    seats += [dict(service_id=sv.id, seat_no=f"{i:03d}", is_accessible=False, status="free") for i in range(1, total_seats - accessible_seats + 1)]
    await bulk(session, Seat, seats)
    await audit.write(session, [audit.row(sc.id, "service.added", "service", sv.id,
                                          f"Operator added capacity: {label} ({total_seats} seats, {accessible_seats} accessible).",
                                          actor="operator")])
    return sv, [ev("service.status_changed", {"service_id": sv.id, "status": "scheduled", "delay_minutes": 0}, ops=True)]


async def requeue_unplaced(session: AsyncSession, sc: Scenario) -> tuple[int, list[Event]]:
    """F15.2: open a batch holding every UNRESOLVED unit (existing choices kept; auto allowed) — WAITLISTED
    units are re-tried by the engine automatically. Returns (units queued, events)."""
    now = clock.utcnow()
    unresolved = list((await session.execute(select(Passenger).where(
        Passenger.scenario_id == sc.id, Passenger.state == "UNRESOLVED"))).scalars())
    batch, events = await batches_dom.get_or_open_batch(session, sc, "capacity_add", now,
                                                        audience=[p.id for p in unresolved])
    rows = []
    for p in unresolved:
        last = (await session.execute(select(Request).where(Request.passenger_id == p.id)
                                      .order_by(Request.id.desc()).limit(1))).scalars().first()
        exists = (await session.execute(select(Request.id).where(Request.batch_id == batch.id, Request.passenger_id == p.id))).first()
        if exists:
            continue
        rows.append(dict(scenario_id=sc.id, batch_id=batch.id, passenger_id=p.id,
                         choice1_service_id=last.choice1_service_id if last else None,
                         choice2_service_id=last.choice2_service_id if last else None,
                         any_fastest=True if not last else (last.any_fastest or last.choice1_service_id is None),
                         status="queued", created_at=now))
    if rows:
        await bulk(session, Request, rows)
        await bulk_transition(session, [r["passenger_id"] for r in rows], "REQUESTED", {"UNRESOLVED"})
    return len(unresolved), events
