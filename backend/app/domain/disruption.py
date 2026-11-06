"""Disruptions: affected detection, cancel / delay / closure incl. re-routing (PRD F5, F12.1, F12.3, §10.3)."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import defer
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.dbutil import bulk
from app.domain import routing as rt
from app.domain.options import compute_options, requestable
from app.domain.snapshot import Snapshot, iso, linestring, seat_counts
from app.domain.state import bulk_transition, transition
from app.errors import AppError
from app.models import (Allocation, Disruption, Edge, Passenger, PassengerDisruption, Request, Scenario, Seat,
                        Service, ServiceStop, WaitlistEntry)
from app.serializers import batch_out
from app.services import audit
from app.services import notifications as notif
from app.services.scenarios import cfg
from app.ws.events import Event, ev

ACTIVE_ALLOC = ("held", "swap_held", "confirmed")


# ------------------------------------------------------------------------------------------------
# registration / persona helpers (F2.5)
# ------------------------------------------------------------------------------------------------
async def service_is_disrupting(session: AsyncSession, sc: Scenario, svc: Service, p: Passenger) -> bool:
    if svc.status == "cancelled":
        return True
    if svc.delay_minutes and svc.delay_minutes > 0:
        if svc.delay_minutes >= int(cfg(sc)["delay_threshold_minutes"]):
            return True
        if p.connection_deadline_at is not None:
            arr = (await session.execute(select(ServiceStop.arrive_at).where(
                ServiceStop.service_id == svc.id, ServiceStop.node_id == p.destination_node_id))).scalar()
            if arr and arr + timedelta(minutes=svc.delay_minutes) > p.connection_deadline_at:
                return True
    return False


async def initial_state_for(session: AsyncSession, sc: Scenario, p: Passenger) -> bool:
    """F2.5: a passenger whose ticket service is already disrupted starts out AFFECTED (not BOOKED)."""
    if p.ticket_service_id is None:
        return False
    svc = await session.get(Service, p.ticket_service_id)
    if svc is None or not await service_is_disrupting(session, sc, svc, p):
        return False
    transition(p, "AFFECTED", force=True)
    p.affected_at = clock.utcnow()
    d = (await session.execute(select(Disruption).where(
        Disruption.scenario_id == sc.id, Disruption.service_id == svc.id, Disruption.resolved_at.is_(None))
        .order_by(Disruption.id.desc()))).scalars().first()
    if d is not None and await session.get(PassengerDisruption, (p.id, d.id)) is None:
        session.add(PassengerDisruption(passenger_id=p.id, disruption_id=d.id, affected_at=p.affected_at))
    return True


# ------------------------------------------------------------------------------------------------
# impact model
# ------------------------------------------------------------------------------------------------
@dataclass
class Change:
    sid: int
    kind: str                                   # cancel | delay | short | reroute
    delay: int = 0
    new_route: list[rt.RouteStop] | None = None  # full stop list incl. skipped flags
    skipped: set[int] = field(default_factory=set)    # served node ids no longer served
    arrivals: dict[int, datetime] = field(default_factory=dict)  # node -> new arrival (served nodes)


@dataclass
class Impact:
    ticket_affected: list[Passenger] = field(default_factory=list)       # BOOKED -> AFFECTED
    lost_seat: list[tuple[Passenger, Allocation]] = field(default_factory=list)   # seat gone -> AFFECTED
    reoffer: list[tuple[Passenger, Allocation]] = field(default_factory=list)     # keeps seat -> REOFFER
    lost_swap: list[Allocation] = field(default_factory=list)       # swap offers on the changed service
    eta: list[tuple[Passenger, int, datetime]] = field(default_factory=list)      # passenger, service, new eta
    holders: dict[int, set[int]] = field(default_factory=lambda: defaultdict(set))  # service -> passenger ids

    @property
    def count(self) -> int:
        return len(self.ticket_affected) + len(self.lost_seat) + len(self.reoffer)

    def passenger_ids(self) -> list[int]:
        ids = [p.id for p in self.ticket_affected] + [p.id for p, _ in self.lost_seat] + [p.id for p, _ in self.reoffer]
        return list(dict.fromkeys(ids))


async def compute_impact(session: AsyncSession, sc: Scenario, snap: Snapshot, changes: list[Change]) -> Impact:
    imp = Impact()
    thr = int(cfg(sc)["delay_threshold_minutes"])
    seen_t: set[int] = set()
    for ch in changes:
        sid = ch.sid
        sv = snap.services[sid]
        stops = {s.node_id: s for s in snap.stops[sid]}
        # ---- ticket holders on this service
        tickets = (await session.execute(select(Passenger).where(
            Passenger.ticket_service_id == sid, Passenger.scenario_id == sc.id))).scalars().all()
        for p in tickets:
            imp.holders[sid].add(p.id)
            if p.state not in ("REGISTERED", "BOOKED") or p.id in seen_t:
                continue
            hit = False
            dest_stop = stops.get(p.destination_node_id)
            if ch.kind == "cancel":
                hit = True
            elif ch.kind == "delay":
                hit = ch.delay >= thr or (p.connection_deadline_at is not None and dest_stop is not None and
                                          dest_stop.arrive_at + timedelta(minutes=ch.delay) > p.connection_deadline_at)
            else:
                hit = p.hub_node_id in ch.skipped or p.destination_node_id in ch.skipped
                if not hit and p.connection_deadline_at is not None and p.destination_node_id in ch.arrivals:
                    hit = ch.arrivals[p.destination_node_id] > p.connection_deadline_at
            if hit:
                imp.ticket_affected.append(p)
                seen_t.add(p.id)
        # ---- seat holders (inventory services)
        if not sv.has_seat_inventory:
            continue
        rows = (await session.execute(select(Allocation, Passenger).join(Passenger, Passenger.id == Allocation.passenger_id)
                                      .where(Allocation.service_id == sid, Allocation.status.in_(ACTIVE_ALLOC)))).all()
        for a, p in rows:
            imp.holders[sid].add(p.id)
            if a.status == "swap_held":
                if ch.kind == "cancel" or (ch.kind in ("short", "reroute") and
                                           (p.hub_node_id in ch.skipped or p.destination_node_id in ch.skipped)):
                    imp.lost_swap.append(a)
                continue
            if ch.kind == "cancel":
                imp.lost_seat.append((p, a))
                continue
            if ch.kind in ("short", "reroute") and p.hub_node_id in ch.skipped:
                imp.lost_seat.append((p, a))
                continue
            old_stop = stops.get(p.destination_node_id)
            if ch.kind in ("short", "reroute") and p.destination_node_id in ch.skipped:
                imp.reoffer.append((p, a))
                continue
            if ch.kind == "delay":
                new_eta = (old_stop.arrive_at + timedelta(minutes=ch.delay)) if old_stop else None
            else:
                new_eta = ch.arrivals.get(p.destination_node_id)
            if new_eta is None or old_stop is None:
                continue
            if p.connection_deadline_at is not None and new_eta > p.connection_deadline_at:
                imp.reoffer.append((p, a))
            elif abs((new_eta - (old_stop.arrive_at + timedelta(minutes=sv.delay_minutes or 0))).total_seconds()) >= 60:
                imp.eta.append((p, sid, new_eta))
    return imp


# ------------------------------------------------------------------------------------------------
# closure planning (rail short-termination, road re-route)
# ------------------------------------------------------------------------------------------------
async def load_edges(session: AsyncSession, sc: Scenario, *, polylines: bool = False) -> list[Edge]:
    q = select(Edge).where(Edge.scenario_id == sc.id).order_by(Edge.id)
    if not polylines:
        q = q.options(defer(Edge.polyline))
    return list((await session.execute(q)).scalars())


def edge_infos(edges: list[Edge], extra_closed: set[int] = frozenset()) -> list[rt.EdgeInfo]:
    return [rt.EdgeInfo(e.id, e.from_node_id, e.to_node_id, e.mode, float(e.base_minutes), float(e.distance_km),
                        e.is_closed or e.id in extra_closed, e.road_name, None) for e in edges]


def twin_ids(edges: list[Edge], e: Edge) -> set[int]:
    return {x.id for x in edges if x.mode == e.mode and {x.from_node_id, x.to_node_id} == {e.from_node_id, e.to_node_id}}


def plan_closure(snap: Snapshot, edges: list[Edge], closing: set[int]) -> list[Change]:
    infos = edge_infos(edges, closing)
    closed_pairs = {(i.mode, i.from_id, i.to_id) for i in infos if i.is_closed}
    node_xy = {n.id: (n.lat, n.lng) for n in snap.nodes.values()}
    changes: list[Change] = []
    for sid, sv in snap.services.items():
        if sv.status in ("cancelled", "completed"):
            continue
        mode = "rail" if sv.mode == "local_train" else "road"
        full = [s for s in snap.stops[sid] if not s.is_skipped]
        nodes = [s.node_id for s in full]
        hit = [i for i in range(len(nodes) - 1) if (mode, nodes[i], nodes[i + 1]) in closed_pairs]
        if not hit:
            continue
        g = rt.build_graph(infos, {mode})
        served = [s for s in full if not s.is_via]
        if mode == "rail":                                    # short-terminate at the last reachable station
            i = hit[0]
            keep = full[: i + 1]
            skipped_nodes = {s.node_id for s in full[i + 1:] if not s.is_via}
            if len([s for s in keep if not s.is_via]) < 2:
                changes.append(Change(sid, "cancel"))
                continue
            route = [rt.RouteStop(s.node_id, s.is_via, s.arrive_at, s.depart_at) for s in keep] + \
                    [rt.RouteStop(s.node_id, s.is_via, keep[-1].depart_at, keep[-1].depart_at, True) for s in full[i + 1:]]
            changes.append(Change(sid, "short", new_route=route, skipped=skipped_nodes,
                                  arrivals={s.node_id: s.arrive_at for s in keep if not s.is_via}))
            continue
        # ---- road service: rebuild each segment that crosses a closed edge (k-shortest paths, k=3)
        seg_nodes: list[list[int]] = []
        for a, b in zip(served, served[1:]):
            ia = next(i for i, s in enumerate(full) if s.seq == a.seq)
            ib = next(i for i, s in enumerate(full) if s.seq == b.seq)
            seg_nodes.append(nodes[ia: ib + 1])
        served_ids = [s.node_id for s in served]
        route: list[rt.RouteStop] = [rt.RouteStop(served_ids[0], False)]
        skipped: set[int] = set()
        pending_skipped: list[int] = []
        i = 0
        visited = {served_ids[0]}
        while i < len(served_ids) - 1:
            seg = seg_nodes[i]
            if not any((mode, u, v) in closed_pairs for u, v in zip(seg, seg[1:])) and not pending_skipped:
                for n in seg[1:-1]:
                    route.append(rt.RouteStop(n, True))
                    visited.add(n)
                route.append(rt.RouteStop(served_ids[i + 1], False))
                visited.add(served_ids[i + 1])
                i += 1
                continue
            placed = False
            for j in range(i + 1, len(served_ids)):
                forbidden = (set(served_ids) | visited) - {served_ids[i], served_ids[j]}
                paths = rt.k_paths(g, served_ids[i], served_ids[j], rt.K_PATHS, forbidden)
                if paths:
                    best = min(paths, key=lambda p: rt.path_minutes(g, p))
                    for k in range(i + 1, j):               # stops that are no longer served
                        skipped.add(served_ids[k])
                        route.append(rt.RouteStop(served_ids[k], False, is_skipped=True))
                    for n in best[1:-1]:
                        route.append(rt.RouteStop(n, True))
                        visited.add(n)
                    route.append(rt.RouteStop(served_ids[j], False))
                    visited.add(served_ids[j])
                    i = j
                    placed = True
                    break
            if not placed:                                   # nothing further reachable: terminate here
                for k in range(i + 1, len(served_ids)):
                    skipped.add(served_ids[k])
                    route.append(rt.RouteStop(served_ids[k], False, is_skipped=True))
                break
        if len([r for r in route if not r.is_via and not r.is_skipped]) < 2:
            changes.append(Change(sid, "cancel"))
            continue
        _schedule_with_skips(route, g, full[0].depart_at)
        arrivals = {r.node_id: r.arrive_at for r in route if not r.is_via and not r.is_skipped}
        changes.append(Change(sid, "reroute", new_route=route, skipped=skipped, arrivals=arrivals))
    return changes


def _schedule_with_skips(route: list[rt.RouteStop], g, origin: datetime, dwell: float = 1.0) -> None:
    """Schedule only the active nodes; skipped stops inherit the previous node's time."""
    active = [r for r in route if not r.is_skipped]
    rt.schedule_route(active, g, dwell, origin)
    prev = None
    for r in route:
        if r.is_skipped:
            r.arrive_at = r.depart_at = prev.depart_at if prev else origin
        else:
            prev = r


# ------------------------------------------------------------------------------------------------
# preview / create / resolve
# ------------------------------------------------------------------------------------------------
def _target_changes(snap: Snapshot, edges: list[Edge] | None, type_: str, service_id: int | None,
                    edge_id: int | None, delay_minutes: int | None) -> list[Change]:
    if type_ in ("cancellation", "delay"):
        if service_id is None or service_id not in snap.services:
            raise AppError("VALIDATION_ERROR", "service_id is required", {"fields": {"service_id": "unknown service"}})
        sv = snap.services[service_id]
        if sv.status in ("cancelled", "completed"):
            raise AppError("INVALID_STATE", f"Service is already {sv.status}")
        if type_ == "cancellation":
            return [Change(service_id, "cancel")]
        if not delay_minutes or delay_minutes <= 0:
            raise AppError("VALIDATION_ERROR", "delay_minutes must be > 0", {"fields": {"delay_minutes": "required"}})
        return [Change(service_id, "delay", delay=delay_minutes)]
    if edge_id is None:
        raise AppError("VALIDATION_ERROR", "edge_id is required", {"fields": {"edge_id": "required"}})
    e = next((x for x in edges or [] if x.id == edge_id), None)
    if e is None:
        raise AppError("NOT_FOUND", "Unknown edge")
    if e.is_closed:
        raise AppError("INVALID_STATE", "Edge is already closed")
    return plan_closure(snap, edges, twin_ids(edges, e))


async def preview(session: AsyncSession, sc: Scenario, type_: str, service_id: int | None, edge_id: int | None,
                  delay_minutes: int | None) -> dict[str, Any]:
    snap = await Snapshot.load(session, sc)
    edges = await load_edges(session, sc) if type_ == "closure" else None
    imp = await compute_impact(session, sc, snap, _target_changes(snap, edges, type_, service_id, edge_id, delay_minutes))
    ids = imp.passenger_ids()
    dests: Counter = Counter()
    if ids:
        for (d,) in (await session.execute(select(Passenger.destination_node_id).where(Passenger.id.in_(ids)))).all():
            dests[d] += 1
    return {"affected_count": imp.count,
            "by_destination": [{"destination": snap.node_ref(d), "count": c} for d, c in
                               sorted(dests.items(), key=lambda kv: (-kv[1], snap.nodes[kv[0]].name))]}


def disruption_dict(d: Disruption) -> dict[str, Any]:
    return {"id": d.id, "type": d.type, "service_id": d.service_id, "edge_id": d.edge_id,
            "delay_minutes": d.delay_minutes, "reason": d.reason, "created_at": iso(d.created_at),
            "resolved_at": iso(d.resolved_at)}


async def create(session: AsyncSession, sc: Scenario, *, type_: str, service_id: int | None, edge_id: int | None,
                 delay_minutes: int | None, reason: str) -> tuple[Disruption, int, Any, list[Event]]:
    from app.domain.batches import get_or_open_batch
    now = clock.utcnow()
    snap = await Snapshot.load(session, sc)
    edges = await load_edges(session, sc, polylines=True) if type_ == "closure" else None
    changes = _target_changes(snap, edges, type_, service_id, edge_id, delay_minutes)
    imp = await compute_impact(session, sc, snap, changes)

    d = Disruption(scenario_id=sc.id, type=type_, service_id=service_id, edge_id=edge_id,
                   delay_minutes=delay_minutes, reason=reason or "", created_at=now)
    session.add(d)
    await session.flush()
    events: list[Event] = []

    # ---- apply infrastructure / service changes
    if type_ == "closure":
        e = next(x for x in edges if x.id == edge_id)
        await session.execute(update(Edge).where(Edge.id.in_(twin_ids(edges, e))).values(is_closed=True))
    for ch in changes:
        events += await _apply_change(session, sc, snap, ch, edges)

    # ---- passengers
    all_ids = imp.passenger_ids()
    affected_ids = [p.id for p in imp.ticket_affected] + [p.id for p, _ in imp.lost_seat]
    events += await _apply_passenger_impact(session, sc, snap, d, imp, now)
    holders = sorted({pid for s in imp.holders.values() for pid in s})
    events += _service_events(snap, changes, imp, all_ids)

    events.append(ev("disruption.created", {"disruption": disruption_dict(d)}, ops=True, to=sorted(set(all_ids) | set(holders))))
    batch = None
    batch_audience = affected_ids + [p.id for p, _ in imp.reoffer]
    if batch_audience:
        trigger = "disruption" if affected_ids else "reoffer"
        batch, bev = await get_or_open_batch(session, sc, trigger, now, audience=batch_audience)
        events += bev
        seeded_events = await _seeded_requests(session, sc, snap, batch, [p for p in imp.ticket_affected if p.is_seeded], now)
        events += seeded_events
    else:
        batch, bev = None, []
    # notifications
    label = _target_label(snap, d, edges)
    notes = [notif.make(p, "disruption_alert", {"message": _alert_message(snap, d, label)}) for p in imp.ticket_affected]
    for p, _ in imp.lost_seat:
        notes.append(notif.make(p, "disruption_alert", {"message": f"Your seat was cancelled ({label})."}))
    for p, a in imp.reoffer:
        notes.append(notif.make(p, "reoffer", {"service": snap.services[a.service_id].label}))
    for p, sid, eta in imp.eta:
        notes.append(notif.make(p, "eta_updated", {"service": snap.services[sid].label, "eta": eta.strftime("%H:%M")}))
    events += await notif.emit(session, notes)
    await audit.write(session, [audit.row(sc.id, f"disruption.{type_}", "disruption", d.id,
                                          f"Operator created {type_} on {label}: {imp.count} passengers affected. {reason or ''}".strip(),
                                          actor="operator", payload={"affected": imp.count})])
    if batch is None:
        from app.domain.batches import current_batch
        batch = await current_batch(session, sc)
    return d, imp.count, batch, events


def _service_events(snap: Snapshot, changes: list[Change], imp: Impact, affected: list[int]) -> list[Event]:
    """service.status_changed / service.rerouted / eta.updated (ops + everyone with a stake in the service)."""
    out: list[Event] = []
    for ch in changes:
        sv = snap.services[ch.sid]
        aud = sorted(imp.holders.get(ch.sid, set()) | set(affected))
        out.append(ev("service.status_changed", {"service_id": sv.id, "status": sv.status, "delay_minutes": sv.delay_minutes},
                      ops=True, to=aud))
        if ch.kind in ("short", "reroute"):
            skipped = [snap.node_ref(n) for n in ch.skipped]
            out.append(ev("service.rerouted", {"service_id": sv.id, "polyline": linestring(sv.polyline),
                                               "skipped_stops": skipped}, ops=True, to=aud))
        if ch.kind in ("short", "reroute", "delay"):
            eta = sv.arrive_at + (timedelta(minutes=ch.delay) if ch.kind == "delay" else timedelta())
            out.append(ev("eta.updated", {"service_id": sv.id, "eta_at": iso(eta)}, ops=True, to=aud))
    groups: dict[tuple[int, str], list[int]] = defaultdict(list)
    for p, sid, eta in imp.eta:       # each passenger's own ETA (their destination), grouped
        groups[(sid, iso(eta))].append(p.id)
    for (sid, eta_iso), ids in groups.items():
        out.append(ev("eta.updated", {"service_id": sid, "eta_at": eta_iso}, to=ids))
    return out


def _target_label(snap: Snapshot, d: Disruption, edges: list[Edge] | None) -> str:
    if d.service_id:
        lab = snap.services[d.service_id].label
        return f"{lab} (+{d.delay_minutes} min)" if d.type == "delay" else lab
    e = next((x for x in edges or [] if x.id == d.edge_id), None)
    if e is None:
        return f"edge #{d.edge_id}"
    return f"{e.road_name or e.mode}: {snap.nodes[e.from_node_id].name} – {snap.nodes[e.to_node_id].name}"


def _alert_message(snap: Snapshot, d: Disruption, label: str) -> str:
    why = f" — {d.reason}" if d.reason else ""
    if d.type == "cancellation":
        return f"Your train {label} is cancelled{why}."
    if d.type == "delay":
        return f"Your train {label} is delayed{why}."
    return f"Disruption on {label}{why}."


async def _apply_change(session: AsyncSession, sc: Scenario, snap: Snapshot, ch: Change, edges: list[Edge] | None) -> list[Event]:
    sv = snap.services[ch.sid]
    if ch.kind == "cancel":
        sv.status = "cancelled"
        sv.version += 1
        await session.execute(delete(WaitlistEntry).where(WaitlistEntry.service_id == sv.id))
        await _scrub_requests(session, sv.id)
    elif ch.kind == "delay":
        sv.status = "delayed"
        sv.delay_minutes = ch.delay
        sv.version += 1
    else:
        route = ch.new_route
        await session.execute(delete(ServiceStop).where(ServiceStop.service_id == sv.id))
        await bulk(session, ServiceStop, [dict(service_id=sv.id, seq=i, node_id=r.node_id, arrive_at=r.arrive_at,
                                               depart_at=r.depart_at, is_skipped=r.is_skipped, is_via=r.is_via)
                                          for i, r in enumerate(route)])
        active = [r for r in route if not r.is_skipped]
        node_xy = {n.id: (n.lat, n.lng) for n in snap.nodes.values()}
        mode = "rail" if sv.mode == "local_train" else "road"
        geom = {(e.from_node_id, e.to_node_id): e.polyline for e in (edges or []) if e.mode == mode}
        sv.polyline = rt.polyline_for_route([r.node_id for r in active], geom, node_xy)
        sv.arrive_at = active[-1].arrive_at
        sv.status = "rerouted"
        sv.version += 1
        # drop waitlist entries for destinations that are no longer served
        if ch.skipped:
            await session.execute(
                delete(WaitlistEntry).where(WaitlistEntry.service_id == sv.id, WaitlistEntry.passenger_id.in_(
                    select(Passenger.id).where(Passenger.destination_node_id.in_(ch.skipped)))))
        # the snapshot is stale for this service now
        snap.stops[sv.id] = [ServiceStop(service_id=sv.id, seq=i, node_id=r.node_id, arrive_at=r.arrive_at,
                                         depart_at=r.depart_at, is_skipped=r.is_skipped, is_via=r.is_via)
                             for i, r in enumerate(route)]
        snap._served.pop(sv.id, None)
        snap._index.pop(sv.id, None)
    snap._sum.pop(sv.id, None)
    await session.flush()
    return []


async def _scrub_requests(session: AsyncSession, sid: int) -> None:
    """A cancelled service can no longer be a choice in a queued request."""
    reqs = (await session.execute(select(Request).where(
        Request.status == "queued", (Request.choice1_service_id == sid) | (Request.choice2_service_id == sid)))).scalars().all()
    for r in reqs:
        if r.choice1_service_id == sid:
            r.choice1_service_id, r.choice2_service_id = r.choice2_service_id, None
        elif r.choice2_service_id == sid:
            r.choice2_service_id = None
        if r.choice1_service_id is None:
            r.any_fastest = True


async def _apply_passenger_impact(session: AsyncSession, sc: Scenario, snap: Snapshot, d: Disruption, imp: Impact,
                                  now: datetime) -> list[Event]:
    events: list[Event] = []
    # tickets: BOOKED -> AFFECTED
    await bulk_transition(session, [p.id for p in imp.ticket_affected], "AFFECTED", {"REGISTERED", "BOOKED"},
                          affected_at=now)
    # seat holders who lost the seat: release allocation, free seats, -> AFFECTED (earliest affected_at is kept)
    release_ids = [a.id for _, a in imp.lost_seat] + [a.id for a in imp.lost_swap]
    if release_ids:
        await session.execute(update(Allocation).where(Allocation.id.in_(release_ids))
                              .values(status="released", updated_at=now))
        await session.execute(update(Seat).where(Seat.allocation_id.in_(release_ids))
                              .values(status="free", allocation_id=None))
    if imp.lost_seat:
        for p, a in imp.lost_seat:
            events.append(ev("seat.released", {"service_id": a.service_id, "count": a.seat_count}, ops=True))
        await session.execute(update(Passenger).where(Passenger.id.in_([p.id for p, _ in imp.lost_seat]),
                                                      Passenger.affected_at.is_(None)).values(affected_at=now))
        await bulk_transition(session, [p.id for p, _ in imp.lost_seat], "AFFECTED")
    # REOFFER: passenger keeps the seat (F12.2); wait_time is preserved (affected_at set only once)
    if imp.reoffer:
        await session.execute(update(Passenger).where(Passenger.id.in_([p.id for p, _ in imp.reoffer]),
                                                      Passenger.affected_at.is_(None)).values(affected_at=now))
        await bulk_transition(session, [p.id for p, _ in imp.reoffer], "REOFFER")
    link = [dict(passenger_id=pid, disruption_id=d.id, affected_at=now) for pid in imp.passenger_ids()]
    if link:
        await bulk(session, PassengerDisruption, link)
    return events


async def _seeded_requests(session: AsyncSession, sc: Scenario, snap: Snapshot, batch, seeded: list[Passenger],
                           now: datetime) -> list[Event]:
    """F5.5: affected seeded passengers get their pre-planned request (70% 2 choices / 20% any / 10% 1 choice)."""
    from app.models import Request as Req
    if not seeded:
        return []
    counts = await seat_counts(session, [s for s, v in snap.services.items() if v.has_seat_inventory])
    rows = []
    cache: dict = {}
    for p in seeded:
        plan = p.seed_plan or {}
        opts = requestable(compute_options(snap, p, now, counts, cache=cache))
        c1 = snap.by_code(plan.get("c1")) if plan.get("c1") else None
        c2 = snap.by_code(plan.get("c2")) if plan.get("c2") else None
        c1id = c1.id if c1 and c1.id in opts else None
        c2id = c2.id if c2 and c2.id in opts else None
        if c1id is None and c2id is not None:
            c1id, c2id = c2id, None
        anyf = bool(plan.get("any")) or (c1id is None and p.allow_auto)
        if c1id is None and not anyf:
            continue
        rows.append(dict(scenario_id=sc.id, batch_id=batch.id, passenger_id=p.id, choice1_service_id=c1id,
                         choice2_service_id=c2id, any_fastest=anyf, status="queued", created_at=now))
    if rows:
        await bulk(session, Req, rows)
        await bulk_transition(session, [r["passenger_id"] for r in rows], "REQUESTED", {"AFFECTED"})
    return []


async def resolve(session: AsyncSession, sc: Scenario, d: Disruption) -> list[Event]:
    if d.resolved_at is not None:
        raise AppError("INVALID_STATE", "Disruption already resolved")
    now = clock.utcnow()
    d.resolved_at = now
    events: list[Event] = []
    if d.edge_id:
        edges = await load_edges(session, sc)
        e = next((x for x in edges if x.id == d.edge_id), None)
        if e:
            await session.execute(update(Edge).where(Edge.id.in_(twin_ids(edges, e))).values(is_closed=False))
    elif d.service_id:
        sv = await session.get(Service, d.service_id)
        if sv and sv.status in ("cancelled", "delayed"):
            sv.status = "scheduled"
            sv.delay_minutes = 0
            sv.version += 1
            events.append(ev("service.status_changed", {"service_id": sv.id, "status": sv.status, "delay_minutes": 0},
                             ops=True, to=await _holders(session, sv.id)))
    pids = [r for (r,) in (await session.execute(select(PassengerDisruption.passenger_id).where(
        PassengerDisruption.disruption_id == d.id))).all()]
    events.append(ev("disruption.resolved", {"disruption": disruption_dict(d)}, ops=True, to=pids))
    await audit.write(session, [audit.row(sc.id, "disruption.resolved", "disruption", d.id,
                                          "Operator resolved the disruption (allocations are not reverted).", actor="operator")])
    return events


async def _holders(session: AsyncSession, sid: int) -> list[int]:
    t = [r for (r,) in (await session.execute(select(Passenger.id).where(Passenger.ticket_service_id == sid))).all()]
    a = [r for (r,) in (await session.execute(select(Allocation.passenger_id).where(
        Allocation.service_id == sid, Allocation.status.in_(ACTIVE_ALLOC)))).all()]
    return list(dict.fromkeys(t + a))


async def list_disruptions(session: AsyncSession, sc: Scenario) -> list[dict[str, Any]]:
    snap = await Snapshot.load(session, sc)
    edges = await load_edges(session, sc)
    rows = (await session.execute(select(Disruption).where(Disruption.scenario_id == sc.id)
                                  .order_by(Disruption.id.desc()))).scalars().all()
    from sqlalchemy import func
    counts = dict((await session.execute(select(PassengerDisruption.disruption_id, func.count())
                                         .group_by(PassengerDisruption.disruption_id))).all())
    return [{"id": d.id, "type": d.type, "target_label": _target_label(snap, d, edges), "reason": d.reason,
             "created_at": iso(d.created_at), "resolved_at": iso(d.resolved_at), "affected_count": counts.get(d.id, 0)}
            for d in rows]
