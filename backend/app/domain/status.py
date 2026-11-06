"""`GET /me/status` and `GET /me/why` payloads (PRD F10.3, F17.3)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.domain import explain, scoring
from app.domain.rules import active_rule, positions_for
from app.domain.snapshot import Snapshot, iso
from app.models import Allocation, AuditLog, Batch, Passenger, PriorityRule, Request, Scenario, Seat
from app.serializers import allocation_dict, batch_out


async def seats_of(session: AsyncSession, alloc_ids: list[int]) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {a: [] for a in alloc_ids}
    if alloc_ids:
        for aid, no in (await session.execute(select(Seat.allocation_id, Seat.seat_no).where(
                Seat.allocation_id.in_(alloc_ids)).order_by(Seat.is_accessible.desc(), Seat.seat_no))).all():
            out[aid].append(no)
    return out


def alloc_out(snap: Snapshot, a: Allocation, seats: list[str]) -> dict[str, Any]:
    return allocation_dict(snap, a.id, a.service_id, a.seat_count, seats, a.choice_rank, a.status, a.is_primary,
                           a.hold_expires_at, float(a.score), a.explanation)


async def build_status(session: AsyncSession, sc: Scenario, snap: Snapshot, p: Passenger) -> dict[str, Any]:
    now = clock.utcnow()
    allocs = list((await session.execute(select(Allocation).where(
        Allocation.passenger_id == p.id, Allocation.status.in_(("held", "confirmed", "swap_held")))
        .order_by(Allocation.id))).scalars())
    seat_map = await seats_of(session, [a.id for a in allocs])
    primary = next((a for a in allocs if a.is_primary and a.status in ("held", "confirmed")), None)
    swap = next((a for a in allocs if a.status == "swap_held"), None)
    rule = await active_rule(session, sc)
    waitlist = await positions_for(session, sc, snap, p.id, rule.weights, now)
    batch = None
    if p.state == "REQUESTED":
        b = (await session.execute(select(Batch).join(Request, Request.batch_id == Batch.id).where(
            Request.passenger_id == p.id, Request.status == "queued").order_by(Batch.id.desc()))).scalars().first()
        batch = batch_out(b) if b else None
    resolved = None
    if p.state == "RESOLVED_ALT":
        from app.domain.alternatives import resolved_alternative
        resolved = await resolved_alternative(session, sc, snap, p)
    best = min(waitlist, key=lambda w: w["position"]) if waitlist else None
    head = explain.headline(
        p.state, rank=primary.choice_rank if primary else None,
        label=snap.services[primary.service_id].label if primary else None,
        position=best["position"] if best else None, wait_label=best["label"] if best else None,
        alt_title=resolved["title"] if resolved else None)
    if p.state == "BOOKED":
        sv = snap.services.get(p.ticket_service_id)
        if sv is not None and sv.delay_minutes:
            head = f"Running {sv.delay_minutes} min late - no action needed"
    return {"state": p.state, "batch": batch,
            "allocation": alloc_out(snap, primary, seat_map[primary.id]) if primary else None,
            "swap_offer": alloc_out(snap, swap, seat_map[swap.id]) if swap else None,
            "waitlist": waitlist, "resolved_alternative": resolved, "headline": head, "server_time": iso(now)}


async def latest_decision(session: AsyncSession, p: Passenger) -> str | None:
    row = (await session.execute(select(AuditLog.explanation).where(
        AuditLog.passenger_id == p.id,
        AuditLog.action.in_(("allocation.placed", "allocation.waitlisted", "allocation.unresolved",
                             "allocation.cascade", "allocation.claim", "allocation.swap"))).order_by(AuditLog.id.desc()).limit(1))).first()
    return row[0] if row else None


async def build_why(session: AsyncSession, sc: Scenario, snap: Snapshot, p: Passenger) -> dict[str, Any]:
    now = clock.utcnow()
    rule = await active_rule(session, sc)
    total, points, text = scoring.score(scoring.ScoreInput.of(p), rule.weights, now)
    return {"score": total, "breakdown": points, "explanation": text,
            "decision_explanation": await latest_decision(session, p), "rule_version": rule.version,
            "weights": {k: float(v) for k, v in rule.weights.items()},
            "waitlist": await positions_for(session, sc, snap, p.id, rule.weights, now)}
