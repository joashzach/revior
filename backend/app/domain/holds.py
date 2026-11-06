"""Holds: accept / decline / expiry (PRD F9), swap (F11), open-booking claim (F16)."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.db import acquire_xact_lock_shared, try_xact_lock_shared
from app.domain import cascade
from app.domain.options import compute_options, requestable
from app.domain.rules import active_rule
from app.domain.seats import assign_seats, free_seats, lock_seats
from app.domain.snapshot import Snapshot, seat_counts
from app.domain.state import transition
from app.errors import AppError
from app.models import Allocation, Passenger, Request, Scenario, Seat, WaitlistEntry
from app.services import audit
from app.services import notifications as notif
from app.services.scenarios import cfg
from app.ws.events import Event, ev

ACTIVE = ("held", "confirmed")


async def _passenger_allocs(session: AsyncSession, p: Passenger, *, lock: bool = False) -> list[Allocation]:
    q = select(Allocation).where(Allocation.passenger_id == p.id, Allocation.status.in_(("held", "swap_held", "confirmed"))).order_by(Allocation.id)
    if lock:
        q = q.with_for_update()
    return list((await session.execute(q)).scalars())


def _target(allocs: list[Allocation], allocation_id: int | None, want: tuple[str, ...]) -> Allocation:
    if allocation_id is not None:
        a = next((x for x in allocs if x.id == allocation_id), None)
        if a is None:
            raise AppError("NOT_FOUND", "Unknown allocation")
        return a
    a = next((x for x in allocs if x.is_primary and x.status in want), None)
    if a is None:
        raise AppError("INVALID_STATE", "You have no held seat to act on")
    return a


async def _after_loss_state(session: AsyncSession, p: Passenger) -> None:
    """After the primary seat is gone: WAITLISTED if waitlist entries remain, else UNRESOLVED (F9.3)."""
    n = (await session.execute(select(func.count()).select_from(WaitlistEntry).where(
        WaitlistEntry.passenger_id == p.id, WaitlistEntry.status == "active", WaitlistEntry.is_swap.is_(False)))).scalar()
    transition(p, "WAITLISTED" if n else "UNRESOLVED", force=True)


async def accept(session: AsyncSession, sc: Scenario, p: Passenger, allocation_id: int | None) -> list[Event]:
    now = clock.utcnow()
    allocs = await _passenger_allocs(session, p, lock=True)
    a = _target(allocs, allocation_id, ("held", "confirmed"))
    snap = await Snapshot.load(session, sc)
    label = snap.services[a.service_id].label
    events: list[Event] = []
    if a.status == "confirmed":
        return events                                              # idempotent: already confirmed
    if a.status not in ("held", "swap_held"):
        raise AppError("HOLD_EXPIRED", "That hold is no longer available")
    if a.hold_expires_at is not None and a.hold_expires_at <= now:
        raise AppError("HOLD_EXPIRED", "Your hold expired", {"allocation_id": a.id})
    seats = (await session.execute(select(Seat.seat_no).where(Seat.allocation_id == a.id).order_by(Seat.seat_no))).scalars().all()
    if a.status == "held":                                         # normal accept
        a.status = "confirmed"
        a.hold_expires_at = None
        await session.execute(update(Seat).where(Seat.allocation_id == a.id).values(status="confirmed"))
        await session.execute(delete(WaitlistEntry).where(WaitlistEntry.passenger_id == p.id, WaitlistEntry.is_swap.is_(False)))
        transition(p, "CONFIRMED", force=True)
        audit_expl = f"Passenger accepted the hold on {label}."
    else:                                                          # accept a swap: confirm new + release old, atomically
        old = next((x for x in allocs if x.is_primary and x.status in ACTIVE), None)
        if old is not None:
            old.status = "released"
            old.hold_expires_at = None
            await free_seats(session, [old.id])
            events.append(ev("seat.released", {"service_id": old.service_id, "count": old.seat_count}, ops=True))
        a.status, a.is_primary, a.hold_expires_at, a.choice_rank = "confirmed", True, None, "swap"
        await session.flush()
        await session.execute(update(Seat).where(Seat.allocation_id == a.id).values(status="confirmed"))
        await session.execute(delete(WaitlistEntry).where(WaitlistEntry.passenger_id == p.id))
        transition(p, "CONFIRMED", force=True)
        audit_expl = f"Passenger accepted the swap to {label}; the previous seat was released."
        if old is not None:
            events += await cascade.run_cascade(session, sc, [old.service_id], now=now)
    events.append(ev("allocation.confirmed", {"allocation_id": a.id, "passenger_id": p.id, "service_id": a.service_id}, ops=True))
    n = notif.make(p, "confirmed", {"service": label, "seats": ", ".join(seats)})
    events += await notif.emit(session, [n])
    await audit.write(session, [audit.row(sc.id, "allocation.confirmed", "allocation", a.id, audit_expl, actor="passenger",
                                          actor_id=p.id, passenger_id=p.id)])
    return events


async def decline(session: AsyncSession, sc: Scenario, p: Passenger, allocation_id: int | None) -> list[Event]:
    now = clock.utcnow()
    allocs = await _passenger_allocs(session, p, lock=True)
    a = _target(allocs, allocation_id, ("held",))
    if a.status == "confirmed":
        raise AppError("INVALID_STATE", "A confirmed seat can't be declined")
    snap = await Snapshot.load(session, sc)
    events: list[Event] = []
    a.status = "declined"
    a.hold_expires_at = None
    await free_seats(session, [a.id])
    await session.flush()
    if a.is_primary:
        await session.execute(update(WaitlistEntry).where(WaitlistEntry.passenger_id == p.id, WaitlistEntry.status == "offered",
                                                         WaitlistEntry.is_swap.is_(False)).values(status="removed"))
        await _after_loss_state(session, p)
    else:                                                          # swap offer dropped only (F11.2)
        await session.execute(update(WaitlistEntry).where(WaitlistEntry.passenger_id == p.id, WaitlistEntry.service_id == a.service_id,
                                                         WaitlistEntry.is_swap).values(status="removed"))
    events.append(ev("allocation.declined", {"allocation_id": a.id, "passenger_id": p.id, "service_id": a.service_id}, ops=True))
    events.append(ev("seat.released", {"service_id": a.service_id, "count": a.seat_count}, ops=True))
    await audit.write(session, [audit.row(sc.id, "allocation.declined", "allocation", a.id,
                                          f"Passenger declined the {'seat' if a.is_primary else 'swap offer'} on "
                                          f"{snap.services[a.service_id].label}; the seat was released and cascaded.",
                                          actor="passenger", actor_id=p.id, passenger_id=p.id)])
    events += await cascade.run_cascade(session, sc, [a.service_id], now=now)
    return events


async def expire_due(session: AsyncSession, sc: Scenario, now: datetime | None = None) -> list[Event]:
    """hold_expirer iteration: expire overdue holds / swap holds, release seats, cascade; warn at 30 s left."""
    now = now or clock.utcnow()
    events: list[Event] = []
    # ---- 30-second warning
    warn = (await session.execute(select(Allocation, Passenger).join(Passenger, Passenger.id == Allocation.passenger_id).where(
        Allocation.scenario_id == sc.id, Allocation.status.in_(("held", "swap_held")), Allocation.expiring_notified.is_(False),
        Allocation.hold_expires_at.is_not(None), Allocation.hold_expires_at > now,
        Allocation.hold_expires_at <= now + timedelta(seconds=30)).with_for_update(skip_locked=True, of=Allocation)
        .execution_options(populate_existing=True))).all()
    if warn:
        snap = await Snapshot.load(session, sc)
        notes = []
        for a, p in warn:
            a.expiring_notified = True
            secs = max(1, int((a.hold_expires_at - now).total_seconds()))
            events.append(ev("hold.expiring", {"allocation_id": a.id, "seconds_left": 30}, to=[p.id], kpi=False))
            notes.append(notif.make(p, "hold_expiring", {"service": snap.services[a.service_id].label, "seconds": secs}))
        events += await notif.emit(session, notes)
    # ---- expiry
    rows = (await session.execute(select(Allocation, Passenger).join(Passenger, Passenger.id == Allocation.passenger_id).where(
        Allocation.scenario_id == sc.id, Allocation.status.in_(("held", "swap_held")),
        Allocation.hold_expires_at.is_not(None), Allocation.hold_expires_at <= now)
        .order_by(Allocation.id).with_for_update(skip_locked=True, of=Allocation)
        .execution_options(populate_existing=True))).all()
    if not rows:
        return events
    snap = await Snapshot.load(session, sc)
    freed: list[int] = []
    notes, audit_rows = [], []
    for a, p in rows:
        was_primary = a.is_primary
        a.status = "expired"
        await free_seats(session, [a.id])
        freed.append(a.service_id)
        label = snap.services[a.service_id].label
        events.append(ev("hold.expired", {"allocation_id": a.id}, to=[p.id]))
        events.append(ev("seat.released", {"service_id": a.service_id, "count": a.seat_count}, ops=True))
        notes.append(notif.make(p, "expired", {"service": label}))
        audit_rows.append(audit.row(sc.id, "allocation.expired", "allocation", a.id,
                                    f"Hold on {label} expired unanswered; seat released and cascaded to the waitlist.",
                                    passenger_id=p.id))
        await session.flush()
        if was_primary:
            await session.execute(update(WaitlistEntry).where(WaitlistEntry.passenger_id == p.id, WaitlistEntry.status == "offered",
                                                             WaitlistEntry.is_swap.is_(False)).values(status="removed"))
            await _after_loss_state(session, p)
        else:
            await session.execute(update(WaitlistEntry).where(WaitlistEntry.passenger_id == p.id, WaitlistEntry.service_id == a.service_id,
                                                             WaitlistEntry.is_swap).values(status="removed"))
    events += await notif.emit(session, notes)
    await audit.write(session, audit_rows)
    events += await cascade.run_cascade(session, sc, sorted(set(freed)), now=now)
    return events


# ------------------------------------------------------------------------------------------------ swap
async def request_swap(session: AsyncSession, sc: Scenario, p: Passenger, service_id: int) -> list[Event]:
    now = clock.utcnow()
    allocs = await _passenger_allocs(session, p, lock=True)
    prim = next((x for x in allocs if x.is_primary and x.status in ACTIVE), None)
    if prim is None or p.state not in ("HELD", "CONFIRMED"):
        raise AppError("INVALID_STATE", "You can only request a swap while you hold a seat")
    if prim.service_id == service_id:
        raise AppError("VALIDATION_ERROR", "You already have a seat on that service", {"fields": {"service_id": "same as current"}})
    snap = await Snapshot.load(session, sc)
    counts = await seat_counts(session, [s for s, v in snap.services.items() if v.has_seat_inventory])
    if service_id not in requestable(compute_options(snap, p, now, counts)):
        raise AppError("VALIDATION_ERROR", "That option is not available for you", {"fields": {"service_id": "not feasible"}})
    rule = await active_rule(session, sc)
    from app.domain import scoring
    s, pts, text_ = scoring.score(scoring.ScoreInput.of(p), rule.weights, now)
    e = (await session.execute(select(WaitlistEntry).where(WaitlistEntry.service_id == service_id, WaitlistEntry.passenger_id == p.id))).scalars().first()
    if e is None:
        e = WaitlistEntry(scenario_id=sc.id, service_id=service_id, passenger_id=p.id, is_swap=True, score=s, score_breakdown=pts,
                          status="active", created_at=now)
        session.add(e)
    else:
        e.is_swap, e.status, e.score, e.score_breakdown = True, "active", s, pts
    await session.flush()
    await audit.write(session, [audit.row(sc.id, "swap.requested", "passenger", p.id,
                                          f"Passenger asked to swap to {snap.services[service_id].label}; keeps the current seat on "
                                          f"{snap.services[prim.service_id].label} until a swap offer is accepted.",
                                          actor="passenger", actor_id=p.id, passenger_id=p.id)])
    return await cascade.run_cascade(session, sc, [service_id], now=now)


# ------------------------------------------------------------------------------------------------ claim
async def claim(session: AsyncSession, sc: Scenario, p: Passenger, service_id: int) -> list[Event]:
    """Open booking (F16): instantly hold seats if free — same row-lock path as allocation, capacity-safe."""
    now = clock.utcnow()
    if not cfg(sc)["open_booking_enabled"]:
        raise AppError("INVALID_STATE", "Open booking is not enabled")
    if not await try_xact_lock_shared(session, "alloc", sc.id):    # an allocation run holds the exclusive lock
        raise AppError("ALLOCATION_IN_PROGRESS", "Allocation is running, try again in a moment")
    snap = await Snapshot.load(session, sc)
    sv = snap.services.get(service_id)
    if sv is None or not sv.has_seat_inventory:
        raise AppError("NOT_FOUND", "Unknown service")
    existing = (await session.execute(select(Allocation.id).where(
        Allocation.passenger_id == p.id, Allocation.is_primary, Allocation.status.in_(ACTIVE)))).first()
    if existing is not None or p.state in ("HELD", "CONFIRMED"):
        raise AppError("INVALID_STATE", "You already hold a seat - use swap to change it")
    if p.state not in ("AFFECTED", "REQUESTED", "WAITLISTED", "UNRESOLVED", "REOFFER", "BOOKED"):
        raise AppError("INVALID_STATE", f"You can't claim a seat while {p.state}")
    if service_id not in requestable(compute_options(snap, p, now, None)):
        raise AppError("VALIDATION_ERROR", "That option is not available for you", {"fields": {"service_id": "not feasible"}})
    # accessible seats go to wheelchair users while any of them is still waiting (F16.1)
    wc_waiting = (await session.execute(select(func.count()).select_from(Passenger).where(
        Passenger.scenario_id == sc.id, Passenger.wheelchair, Passenger.state.in_(("WAITLISTED", "UNRESOLVED"))))).scalar()
    seats = await lock_seats(session, service_id, p.party_size, wheelchair=bool(p.wheelchair),
                             accessible_ok=bool(p.wheelchair) or not wc_waiting)
    if seats is None:
        raise AppError("SEAT_UNAVAILABLE", "That seat was just taken.", {"service_id": service_id})
    rule = await active_rule(session, sc)
    from app.domain import scoring
    s, pts, text_ = scoring.score(scoring.ScoreInput.of(p), rule.weights, now)
    hold_s = int(cfg(sc)["hold_seconds"])
    expl = f"Open booking: claimed {p.party_size} seat(s) on {sv.label} instantly (first come, first served). {text_}."
    a = Allocation(scenario_id=sc.id, passenger_id=p.id, service_id=service_id, seat_count=p.party_size, choice_rank="claim",
                   status="held", is_primary=True, hold_expires_at=now + timedelta(seconds=hold_s), score=s,
                   score_breakdown=pts, explanation=expl, created_at=now, updated_at=now)
    session.add(a)
    try:
        await session.flush()                                      # one_primary_active guards double claims
    except IntegrityError:
        raise AppError("INVALID_STATE", "You already hold a seat - use swap to change it")
    await assign_seats(session, seats, a.id, "held")
    await session.execute(delete(WaitlistEntry).where(WaitlistEntry.passenger_id == p.id, WaitlistEntry.is_swap.is_(False)))
    await session.execute(update(Request).where(Request.passenger_id == p.id, Request.status == "queued").values(status="superseded"))
    transition(p, "HELD", force=True)
    await audit.write(session, [audit.row(sc.id, "allocation.claim", "allocation", a.id, expl, actor="passenger", actor_id=p.id,
                                          passenger_id=p.id, payload={"service_id": service_id})])
    from app.serializers import allocation_dict
    dct = allocation_dict(snap, a.id, service_id, a.seat_count, [x.seat_no for x in seats], "claim", "held", True,
                          a.hold_expires_at, s, expl)
    return [ev("allocation.result", {"state": "HELD", "allocation": dct, "explanation": expl}, to=[p.id])]
