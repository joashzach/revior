"""Cascade of freed seats to the waitlist in priority order (PRD F10, F11.2).

Whenever seats on a service are released (decline, expiry, cancellation, persona release...), the highest-priority
*feasible* waitlisted unit receives a held offer (`cascade`), or a `swap_held` offer for swap requests. Repeats
while seats remain. Takes the shared advisory lock so it never interleaves with an allocation run.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.db import acquire_xact_lock_shared
from app.domain import scoring
from app.domain.options import compute_options, requestable
from app.domain.rules import active_rule, rank_waitlist
from app.domain.seats import assign_seats, lock_seats
from app.domain.snapshot import Snapshot, seat_counts
from app.domain.state import transition
from app.models import Allocation, Passenger, Scenario, Seat, WaitlistEntry
from app.serializers import allocation_dict
from app.services import audit
from app.services import notifications as notif
from app.services.scenarios import cfg
from app.ws.events import Event, ev


async def _feasible(session, snap, r, sid, counts, now) -> bool:
    """Capacity, accessibility, deadline and stop-order feasibility of offering ``sid`` to this entry."""
    p: Passenger = r["passenger"]
    opts = requestable(compute_options(snap, p, now, counts))
    if sid not in opts:
        return False
    c = counts[sid]
    n = p.party_size
    if p.wheelchair:
        return c["accessible_free"] >= 1 and c["free"] >= n
    return c["free"] >= n


async def run_cascade(session: AsyncSession, sc: Scenario, service_ids: list[int], *, now: datetime | None = None
                      ) -> list[Event]:
    """Offer free seats of ``service_ids`` to their waitlists. Returns events (publish after commit)."""
    now = now or clock.utcnow()
    await acquire_xact_lock_shared(session, "alloc", sc.id)
    snap = await Snapshot.load(session, sc)
    rule = await active_rule(session, sc)
    hold_s = int(cfg(sc)["hold_seconds"])
    events: list[Event] = []
    notes, audit_rows = [], []
    touched: set[int] = set()
    for sid in dict.fromkeys(service_ids):
        sv = snap.services.get(sid)
        if sv is None or not sv.has_seat_inventory or sv.status in ("cancelled", "completed", "running"):
            continue
        while True:
            counts = await seat_counts(session, [sid])
            if counts[sid]["free"] <= 0:
                break
            ranked = await rank_waitlist(session, sc, rule.weights, now, sid)
            wc_waiting = any(r["passenger"].wheelchair and not r["entry"].is_swap for r in ranked)
            chosen = None
            for pos, r in enumerate(ranked, 1):
                p: Passenger = r["passenger"]
                e: WaitlistEntry = r["entry"]
                if e.is_swap:
                    has_primary = (await session.execute(select(Allocation.id).where(
                        Allocation.passenger_id == p.id, Allocation.is_primary, Allocation.status.in_(("held", "confirmed"))))).first()
                    has_swap = (await session.execute(select(Allocation.id).where(
                        Allocation.passenger_id == p.id, Allocation.status == "swap_held"))).first()
                    if not has_primary or has_swap:
                        continue
                elif p.state != "WAITLISTED":
                    continue
                # accessible seats stay reserved for waiting wheelchair users (F16.1 / F8.4)
                reg_free = counts[sid]["free"] - counts[sid]["accessible_free"]
                if not p.wheelchair and wc_waiting and reg_free < p.party_size:
                    continue
                if not await _feasible(session, snap, r, sid, counts, now):
                    continue
                chosen = (pos, r)
                break
            if chosen is None:
                break
            pos, r = chosen
            p, e = r["passenger"], r["entry"]
            seats = await lock_seats(session, sid, p.party_size, wheelchair=bool(p.wheelchair),
                                     accessible_ok=not (wc_waiting and not p.wheelchair))
            if seats is None:
                break
            swap = e.is_swap
            text_ = (f"Seat freed on {sv.label}: you were the highest-priority feasible waitlisted "
                     f"{'swap request' if swap else 'unit'} (position {pos} of {len(ranked)}, score {r['score']:g}, rules v{rule.version}). "
                     f"{r['text']}.")
            a = Allocation(scenario_id=sc.id, passenger_id=p.id, service_id=sid, seat_count=p.party_size,
                           choice_rank="swap" if swap else "cascade", status="swap_held" if swap else "held",
                           is_primary=not swap, hold_expires_at=now + timedelta(seconds=hold_s), score=r["score"],
                           score_breakdown=r["points"], explanation=text_, created_at=now, updated_at=now)
            session.add(a)
            await session.flush()
            await assign_seats(session, seats, a.id, "held")
            e.status = "offered"
            if not swap:
                await session.execute(update(WaitlistEntry).where(
                    WaitlistEntry.passenger_id == p.id, WaitlistEntry.id != e.id, WaitlistEntry.is_swap.is_(False))
                    .values(status="removed"))
                transition(p, "HELD", force=True)
            seat_nos = [s.seat_no for s in seats]
            dct = allocation_dict(snap, a.id, sid, a.seat_count, seat_nos, a.choice_rank, a.status, a.is_primary,
                                  a.hold_expires_at, r["score"], text_)
            events.append(ev("swap.offer_created" if swap else "offer.created", {"allocation": dct}, to=[p.id]))
            notes.append(notif.make(p, "swap_offer" if swap else "offer_cascade",
                                    {"service": sv.label, "seats": ", ".join(seat_nos), "minutes": max(1, hold_s // 60)}))
            audit_rows.append(audit.row(sc.id, "allocation.swap" if swap else "allocation.cascade", "allocation", a.id,
                                        text_, passenger_id=p.id, payload={"service_id": sid, "score": r["score"]}))
            touched.add(sid)
    events += await notif.emit(session, notes)
    await audit.write(session, audit_rows)
    events += await refresh_positions(session, sc, snap, rule.weights, now, service_ids)
    return events


async def refresh_positions(session: AsyncSession, sc: Scenario, snap: Snapshot, weights: dict, now: datetime,
                            service_ids: list[int]) -> list[Event]:
    """`waitlist.position_changed` for every entry whose rank moved (F10.3)."""
    events: list[Event] = []
    for sid in dict.fromkeys(service_ids):
        ranked = await rank_waitlist(session, sc, weights, now, sid)
        for i, r in enumerate(ranked, 1):
            e: WaitlistEntry = r["entry"]
            if e.last_position != i:
                e.last_position = i
                events.append(ev("waitlist.position_changed", {"service_id": sid, "position": i, "total": len(ranked)},
                                 to=[r["passenger"].id], kpi=False))
    return events
