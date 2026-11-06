"""Alternatives for unplaced passengers (PRD F13): LATER_SERVICE, MULTI_LEG, POD, ALT_HUB, WAIT_DELAYED."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.domain import pods as pods_dom
from app.domain.options import OptionData, compute_options, leg_dict, option_dict
from app.domain.snapshot import Snapshot, iso, seat_counts
from app.domain.state import transition
from app.errors import AppError
from app.models import AuditLog, Passenger, Request, Scenario, WaitlistEntry
from app.services import audit
from app.ws.events import Event

ALT_STATES = ("AFFECTED", "REQUESTED", "WAITLISTED", "UNRESOLVED")


def _alt(type_: str, ref: str, title: str, desc: str, eta, legs: list, pod: dict | None, requires: bool) -> dict[str, Any]:
    return {"type": type_, "ref": ref, "title": title, "description": desc, "eta_at": iso(eta), "legs": legs, "pod": pod,
            "requires_allocation": requires}


async def generate(session: AsyncSession, sc: Scenario, snap: Snapshot, p: Passenger) -> list[dict[str, Any]]:
    now = clock.utcnow()
    counts = await seat_counts(session, [s for s, v in snap.services.items() if v.has_seat_inventory])
    opts: list[OptionData] = compute_options(snap, p, now, counts)
    alts: list[tuple[Any, dict]] = []
    for o in opts:
        if o.is_full or not o.meets_deadline:
            continue
        legs = [leg_dict(snap, *leg) for leg in o.legs]
        if o.is_multi_leg:
            t = snap.nodes[o.legs[0][2]].name
            alts.append((o.eta_at, _alt("MULTI_LEG", f"MULTI:{o.key}", f"{snap.services[o.legs[0][0]].label}, then onward from {t}",
                                        f"{o.label}. ETA {o.eta_at.strftime('%H:%M')} with {o.transfers} change.",
                                        o.eta_at, legs, None, True)))
        else:
            alts.append((o.eta_at, _alt("LATER_SERVICE", f"SVC:{o.request_sid}", f"Service: {o.label}",
                                        f"Departs {o.depart_at.strftime('%H:%M')}, arrives {o.eta_at.strftime('%H:%M')} - "
                                        f"{o.seats_left} seats left.", o.eta_at, legs, None, True)))
    # ---- shared cab / auto pods
    geo = await pods_dom.geo_for(session, sc, snap)
    already = await pods_dom.pod_in_which(session, p)
    if already is None:
        for pod in await pods_dom.suggested(session, sc, snap, p):
            d = await pods_dom.pod_dict(session, snap, pod)
            eta = now + timedelta(minutes=10 + geo.minutes(pod.origin_node_id, pod.destination_node_id) * 0.6)
            alts.append((eta, _alt("POD", f"POD:{pod.id}", f"Share a {pod.mode} to {d['destination']['name']}",
                                   f"{d['seats_taken']}/{d['capacity']} seats taken - about ₹{d['fare_per_seat']:.0f} per seat.",
                                   eta, [], d, False)))
        km = geo.km(p.hub_node_id, p.destination_node_id)
        eta = now + timedelta(minutes=15 + geo.minutes(p.hub_node_id, p.destination_node_id) * 0.6)
        mode = "cab" if p.party_size > 3 else "auto" if False else "cab"
        alts.append((eta, _alt("POD", "POD:NEW", f"Start a shared {mode} to {snap.nodes[p.destination_node_id].name}",
                               f"Be the first in a new pod ({km} km, about ₹{pods_dom.fare(mode, km):.0f} total, split equally).",
                               eta, [], None, False)))
    # ---- nearby hub (walk / auto edge) with a feasible service
    alts += await _alt_hubs(session, sc, snap, p, now, counts)
    # ---- wait for the delayed train (delay disruptions only)
    sv = snap.services.get(p.ticket_service_id) if p.ticket_service_id else None
    if sv is not None and sv.delay_minutes and sv.status in ("delayed", "rerouted", "scheduled", "running"):
        pair = snap.serves_in_order(sv.id, p.hub_node_id, p.destination_node_id)
        if pair:
            dep, arr = snap.effective(pair[0].depart_at, sv.id), snap.effective(pair[1].arrive_at, sv.id)
            if dep >= now:
                ok = p.connection_deadline_at is None or arr <= p.connection_deadline_at
                alts.append((arr, _alt("WAIT_DELAYED", f"WAIT:{sv.id}", "Wait for your delayed train",
                                       f"Your train is {sv.delay_minutes} min late: departs {dep.strftime('%H:%M')}, arrives "
                                       f"{arr.strftime('%H:%M')}." + ("" if ok else " (After your connection deadline.)"),
                                       arr, [leg_dict(snap, sv.id, p.hub_node_id, p.destination_node_id)], None, False)))
    alts.sort(key=lambda t: (t[0] is None, t[0], t[1]["ref"]))
    return [a for _, a in alts]


async def _alt_hubs(session, sc, snap: Snapshot, p: Passenger, now, counts) -> list[tuple[Any, dict]]:
    from app.domain.disruption import edge_infos, load_edges
    edges = await load_edges(session, sc)
    out = []
    for e in edges:
        if e.mode != "walk" or e.is_closed or e.from_node_id != p.hub_node_id:
            continue
        hub = snap.nodes[e.to_node_id]
        if not hub.is_hub:
            continue
        arrive = now + timedelta(minutes=float(e.base_minutes))
        best = None
        for sid, sv in snap.services.items():
            if sv.status in ("cancelled", "completed", "running") or (p.wheelchair and sv.accessible_seats <= 0 and sv.has_seat_inventory):
                continue
            if sv.has_seat_inventory and counts.get(sid, {}).get("free", 0) < p.party_size:
                continue
            pair = snap.serves_in_order(sid, hub.id, p.destination_node_id)
            if not pair:
                continue
            dep = snap.effective(pair[0].depart_at, sid)
            if dep < arrive:
                continue
            arr = snap.effective(pair[1].arrive_at, sid)
            if p.connection_deadline_at is not None and arr > p.connection_deadline_at:
                continue
            if best is None or arr < best[0]:
                best = (arr, sid, dep)
        if best:
            arr, sid, dep = best
            out.append((arr, _alt("ALT_HUB", f"HUB:{hub.id}:{sid}", f"Go to {hub.name} ({round(float(e.base_minutes))} min away)",
                                  f"{snap.services[sid].label} leaves {hub.name} at {dep.strftime('%H:%M')}, arrives {arr.strftime('%H:%M')}.",
                                  arr, [leg_dict(snap, sid, hub.id, p.destination_node_id)], None, False)))
    return out


async def accept(session: AsyncSession, sc: Scenario, p: Passenger, type_: str, ref: str) -> list[Event]:
    """Accept a non-seat alternative -> RESOLVED_ALT (POD / WAIT_DELAYED); ALT_HUB moves the passenger to that hub."""
    if p.state not in ALT_STATES:
        raise AppError("INVALID_STATE", f"You can't choose an alternative while {p.state}", {"state": p.state})
    snap = await Snapshot.load(session, sc)
    alts = await generate(session, sc, snap, p)
    alt = next((a for a in alts if a["type"] == type_ and a["ref"] == ref), None)
    if alt is None:
        raise AppError("NOT_FOUND", "That alternative is not available (any more)", {"type": type_, "ref": ref})
    if alt["requires_allocation"]:
        raise AppError("VALIDATION_ERROR", "Seat-bearing alternatives go through /me/request",
                       {"fields": {"type": "use POST /me/request with the service id"}})
    events: list[Event] = []
    if type_ == "POD":
        if ref == "POD:NEW":
            _, events = await pods_dom.create(session, sc, p, p.destination_node_id, "cab")
        else:
            _, events = await pods_dom.join(session, sc, p, int(ref.split(":")[1]))
    elif type_ == "WAIT_DELAYED":
        transition(p, "RESOLVED_ALT")
    elif type_ == "ALT_HUB":
        hub_id = int(ref.split(":")[1])
        p.hub_node_id = hub_id
        p.ticket_service_id = int(ref.split(":")[2])
        transition(p, "AFFECTED", force=True)
        await session.execute(delete(WaitlistEntry).where(WaitlistEntry.passenger_id == p.id, WaitlistEntry.is_swap.is_(False)))
        await session.execute(update(Request).where(Request.passenger_id == p.id, Request.status == "queued").values(status="superseded"))
    if type_ in ("WAIT_DELAYED",):
        await session.execute(delete(WaitlistEntry).where(WaitlistEntry.passenger_id == p.id, WaitlistEntry.is_swap.is_(False)))
        await session.execute(update(Request).where(Request.passenger_id == p.id, Request.status == "queued").values(status="superseded"))
    await audit.write(session, [audit.row(sc.id, "alternative.accepted", "passenger", p.id,
                                          f"Passenger chose alternative: {alt['title']}.", actor="passenger", actor_id=p.id,
                                          passenger_id=p.id, payload={"type": type_, "ref": ref, "alternative": alt})])
    return events


async def resolved_alternative(session: AsyncSession, sc: Scenario, snap: Snapshot, p: Passenger) -> dict[str, Any] | None:
    row = (await session.execute(select(AuditLog.payload).where(AuditLog.passenger_id == p.id, AuditLog.action == "alternative.accepted")
                                 .order_by(AuditLog.id.desc()).limit(1))).first()
    pod = await pods_dom.pod_in_which(session, p)
    if pod is not None:                                  # always show the live pod (members, fare)
        d = await pods_dom.pod_dict(session, snap, pod)
        base = (row[0].get("alternative") if row else None) or _alt("POD", f"POD:{pod.id}", f"Shared {pod.mode}", "", None, [], None, False)
        return {**base, "ref": f"POD:{pod.id}", "type": "POD", "pod": d,
                "title": f"Shared {pod.mode} to {d['destination']['name']}",
                "description": f"{d['seats_taken']}/{d['capacity']} seats - ₹{d['fare_per_seat']:.0f} per seat ({pod.status})"}
    return row[0].get("alternative") if row else None
