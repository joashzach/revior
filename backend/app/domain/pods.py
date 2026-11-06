"""Pods — shared cab / auto pooling for unplaced passengers (PRD F14)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.domain import routing as rt
from app.domain.disruption import edge_infos, load_edges
from app.domain.snapshot import Snapshot
from app.domain.state import transition
from app.domain.tickets import haversine_km
from app.errors import AppError
from app.models import Passenger, Pod, PodMember, Request, Scenario, WaitlistEntry
from app.services import audit
from app.services import notifications as notif
from app.ws.events import Event, ev

# mock fares (PRD F14.4): base + per_km x route_km, split equally among seats
MODES = {"cab": {"capacity": 4, "base": 100.0, "per_km": 18.0}, "auto": {"capacity": 3, "base": 30.0, "per_km": 15.0}}
CORRIDOR_DETOUR = 1.15
POD_STATES = ("AFFECTED", "REQUESTED", "WAITLISTED", "UNRESOLVED")


class Geo:
    """Road distances between nodes (shortest road path; haversine x 1.25 fallback)."""

    def __init__(self, snap: Snapshot, edges):
        self.snap = snap
        self.g = rt.build_graph(edge_infos(edges), {"road"})

    def km(self, a: int, b: int) -> float:
        if a == b:
            return 0.0
        p = rt.shortest_path(self.g, a, b)
        if p:
            return round(rt.path_km(self.g, p), 2)
        na, nb = self.snap.nodes[a], self.snap.nodes[b]
        return round(haversine_km(na.lat, na.lng, nb.lat, nb.lng) * 1.25, 2)

    def minutes(self, a: int, b: int) -> float:
        p = rt.shortest_path(self.g, a, b) if a != b else None
        return rt.path_minutes(self.g, p) if p else self.km(a, b) / 0.45


async def geo_for(session: AsyncSession, sc: Scenario, snap: Snapshot) -> Geo:
    return Geo(snap, await load_edges(session, sc))


def fare(mode: str, km: float) -> float:
    m = MODES[mode]
    return round(m["base"] + m["per_km"] * km, 2)


async def members_of(session: AsyncSession, pod_id: int) -> list[tuple[PodMember, Passenger]]:
    return list((await session.execute(select(PodMember, Passenger).join(Passenger, Passenger.id == PodMember.passenger_id)
                                       .where(PodMember.pod_id == pod_id).order_by(PodMember.joined_at, Passenger.id))).all())


async def pod_dict(session: AsyncSession, snap: Snapshot, pod: Pod) -> dict[str, Any]:
    ms = await members_of(session, pod.id)
    taken = sum(m.seat_count for m, _ in ms)
    return {"id": pod.id, "origin": snap.node_ref(pod.origin_node_id), "destination": snap.node_ref(pod.destination_node_id),
            "mode": pod.mode, "capacity": pod.capacity, "seats_taken": taken, "status": pod.status,
            "members": [{"passenger_id": p.id, "name": p.name, "seat_count": m.seat_count} for m, p in ms],
            "route_km": float(pod.route_km), "fare_total": float(pod.fare_total),
            "fare_per_seat": round(float(pod.fare_total) / max(1, taken), 2)}


async def _recompute(session: AsyncSession, pod: Pod) -> int:
    taken = (await session.execute(select(func.coalesce(func.sum(PodMember.seat_count), 0)).where(PodMember.pod_id == pod.id))).scalar()
    return int(taken)


async def pod_in_which(session: AsyncSession, p: Passenger) -> Pod | None:
    return (await session.execute(select(Pod).join(PodMember, PodMember.pod_id == Pod.id).where(
        PodMember.passenger_id == p.id, Pod.status.in_(("forming", "full", "confirmed"))))).scalars().first()


async def suggested(session: AsyncSession, sc: Scenario, snap: Snapshot, p: Passenger) -> list[Pod]:
    """Forming pods from the passenger's hub whose destination is theirs, or lies on the same corridor
    (dropping the passenger at their stop adds <= 15% to the pod's direct route)."""
    if await pod_in_which(session, p) is not None:
        return []
    geo = await geo_for(session, sc, snap)
    pods = (await session.execute(select(Pod).where(Pod.scenario_id == sc.id, Pod.status == "forming",
                                                    Pod.origin_node_id == p.hub_node_id).order_by(Pod.id))).scalars().all()
    out = []
    for pod in pods:
        taken = await _recompute(session, pod)
        if pod.capacity - taken < p.party_size:
            continue
        if pod.destination_node_id == p.destination_node_id:
            out.append(pod)
            continue
        direct = geo.km(pod.origin_node_id, pod.destination_node_id)
        via = geo.km(pod.origin_node_id, p.destination_node_id) + geo.km(p.destination_node_id, pod.destination_node_id)
        if direct > 0 and via <= direct * CORRIDOR_DETOUR:
            out.append(pod)
    return out


def _check_state(p: Passenger) -> None:
    if p.state not in POD_STATES:
        raise AppError("INVALID_STATE", f"You can't join a pod while {p.state}", {"state": p.state})


async def _to_resolved(session: AsyncSession, p: Passenger) -> None:
    """Joining a pod resolves the journey (RESOLVED_ALT): drop waitlists and queued requests."""
    from sqlalchemy import delete, update
    transition(p, "RESOLVED_ALT")
    await session.execute(delete(WaitlistEntry).where(WaitlistEntry.passenger_id == p.id, WaitlistEntry.is_swap.is_(False)))
    await session.execute(update(Request).where(Request.passenger_id == p.id, Request.status == "queued").values(status="superseded"))


async def create(session: AsyncSession, sc: Scenario, p: Passenger, destination_node_id: int, mode: str) -> tuple[Pod, list[Event]]:
    _check_state(p)
    if await pod_in_which(session, p) is not None:
        raise AppError("INVALID_STATE", "You are already in a pod")
    snap = await Snapshot.load(session, sc)
    if destination_node_id not in snap.nodes or destination_node_id == p.hub_node_id:
        raise AppError("VALIDATION_ERROR", "Invalid destination", {"fields": {"destination_node_id": "invalid"}})
    cap = MODES[mode]["capacity"]
    if p.party_size > cap:
        raise AppError("VALIDATION_ERROR", f"A {mode} seats {cap}; your party is {p.party_size}", {"fields": {"mode": "too small"}})
    geo = await geo_for(session, sc, snap)
    km = geo.km(p.hub_node_id, destination_node_id)
    pod = Pod(scenario_id=sc.id, origin_node_id=p.hub_node_id, destination_node_id=destination_node_id, mode=mode,
              capacity=cap, status="forming", route_km=km, fare_total=fare(mode, km), created_at=clock.utcnow())
    session.add(pod)
    await session.flush()
    session.add(PodMember(pod_id=pod.id, passenger_id=p.id, seat_count=p.party_size, joined_at=clock.utcnow()))
    await session.flush()
    await _to_resolved(session, p)
    await audit.write(session, [audit.row(sc.id, "pod.created", "pod", pod.id,
                                          f"{p.name} created a shared {mode} to {snap.nodes[destination_node_id].name} "
                                          f"({km} km, ₹{fare(mode, km)} total).", actor="passenger", actor_id=p.id, passenger_id=p.id)])
    return pod, await _events(session, snap, pod)


async def _events(session: AsyncSession, snap: Snapshot, pod: Pod, actor: Passenger | None = None,
                  what: str = "") -> list[Event]:
    d = await pod_dict(session, snap, pod)
    events = [ev("pod.updated", {"pod": d}, ops=True, to=[m["passenger_id"] for m in d["members"]])]
    if actor is not None and what:                       # `pod_update` notification for everyone else in the pod
        others = [p for _, p in await members_of(session, pod.id) if p.id != actor.id]
        msg = f"{actor.name} {what} - {d['seats_taken']}/{d['capacity']} seats, about ₹{d['fare_per_seat']:.0f} each."
        events += await notif.emit(session, [notif.make(p, "pod_update", {"message": msg}) for p in others])
    return events


async def join(session: AsyncSession, sc: Scenario, p: Passenger, pod_id: int) -> tuple[Pod, list[Event]]:
    """Transactional join: the pod row is locked, capacity is never exceeded (POD_FULL)."""
    _check_state(p)
    pod = (await session.execute(select(Pod).where(Pod.id == pod_id, Pod.scenario_id == sc.id).with_for_update())).scalars().first()
    if pod is None:
        raise AppError("NOT_FOUND", "Unknown pod")
    if await pod_in_which(session, p) is not None:
        raise AppError("INVALID_STATE", "You are already in a pod")
    if pod.status != "forming":
        raise AppError("POD_FULL", "That pod is no longer open", {"status": pod.status})
    taken = await _recompute(session, pod)
    if taken + p.party_size > pod.capacity:
        raise AppError("POD_FULL", "That pod is full", {"capacity": pod.capacity})
    session.add(PodMember(pod_id=pod.id, passenger_id=p.id, seat_count=p.party_size, joined_at=clock.utcnow()))
    await session.flush()
    taken += p.party_size
    if taken >= pod.capacity:
        pod.status = "confirmed"                  # full -> auto-confirm (F14.3)
    await _to_resolved(session, p)
    snap = await Snapshot.load(session, sc)
    await audit.write(session, [audit.row(sc.id, "pod.joined", "pod", pod.id, f"{p.name} joined the shared {pod.mode} to "
                                          f"{snap.nodes[pod.destination_node_id].name} ({taken}/{pod.capacity} seats).",
                                          actor="passenger", actor_id=p.id, passenger_id=p.id)])
    return pod, await _events(session, snap, pod, p, "joined your shared " + pod.mode)


async def leave(session: AsyncSession, sc: Scenario, p: Passenger, pod_id: int) -> list[Event]:
    pod = (await session.execute(select(Pod).where(Pod.id == pod_id, Pod.scenario_id == sc.id).with_for_update())).scalars().first()
    if pod is None:
        raise AppError("NOT_FOUND", "Unknown pod")
    m = await session.get(PodMember, (pod_id, p.id))
    if m is None:
        raise AppError("INVALID_STATE", "You are not in that pod")
    if pod.status in ("departed", "cancelled"):
        raise AppError("INVALID_STATE", f"That pod is {pod.status}")
    snap = await Snapshot.load(session, sc)
    audience = [pm.passenger_id for pm, _ in await members_of(session, pod_id)]
    await session.delete(m)
    await session.flush()
    remaining = await _recompute(session, pod)
    if remaining == 0:
        pod.status = "cancelled"
    elif pod.status in ("full", "confirmed") and (remaining < pod.capacity):
        members_left = len(await members_of(session, pod_id))
        pod.status = "confirmed" if members_left >= 2 and pod.status == "confirmed" and remaining >= pod.capacity else "forming"
    if p.state == "RESOLVED_ALT":                 # back to needing a way home
        transition(p, "UNRESOLVED", force=True)
    await audit.write(session, [audit.row(sc.id, "pod.left", "pod", pod.id, f"{p.name} left the shared {pod.mode}.",
                                          actor="passenger", actor_id=p.id, passenger_id=p.id)])
    d = await pod_dict(session, snap, pod)
    events = [ev("pod.updated", {"pod": d}, ops=True, to=list(dict.fromkeys(audience)))]
    rest = [m["passenger_id"] for m in d["members"]]
    if rest:
        who = await session.get(Passenger, p.id)
        msg = f"{who.name} left the shared {pod.mode} - {d['seats_taken']}/{d['capacity']} seats, about ₹{d['fare_per_seat']:.0f} each."
        others = [x for _, x in await members_of(session, pod.id)]
        events += await notif.emit(session, [notif.make(x, "pod_update", {"message": msg}) for x in others])
    return events


async def confirm(session: AsyncSession, sc: Scenario, p: Passenger, pod_id: int) -> tuple[Pod, list[Event]]:
    pod = (await session.execute(select(Pod).where(Pod.id == pod_id, Pod.scenario_id == sc.id).with_for_update())).scalars().first()
    if pod is None:
        raise AppError("NOT_FOUND", "Unknown pod")
    if await session.get(PodMember, (pod_id, p.id)) is None:
        raise AppError("FORBIDDEN", "Only pod members can confirm")
    members = await members_of(session, pod_id)
    if pod.status == "confirmed":
        return pod, []
    if pod.status != "forming":
        raise AppError("INVALID_STATE", f"Pod is {pod.status}")
    if len(members) < 2:
        raise AppError("INVALID_STATE", "A pod needs at least 2 members to be confirmed")
    pod.status = "confirmed"
    snap = await Snapshot.load(session, sc)
    await audit.write(session, [audit.row(sc.id, "pod.confirmed", "pod", pod.id, f"{p.name} confirmed the pod "
                                          f"({len(members)} members).", actor="passenger", actor_id=p.id, passenger_id=p.id)])
    return pod, await _events(session, snap, pod, p, "confirmed your shared " + pod.mode)
