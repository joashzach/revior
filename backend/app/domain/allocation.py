"""Allocation engine (PRD §8): greedy, two-pass, deterministic, explainable, capacity-safe.

All free seats of the candidate services are row-locked up front (``FOR UPDATE SKIP LOCKED``) inside one
transaction; units are then placed in memory and written back in bulk. Runs for a scenario are serialised by
an exclusive advisory lock (claims/cascades hold the shared variant), so seats can never be over-allocated.
"""
from __future__ import annotations

import json
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.dbutil import bulk, in_ids
from app.domain import explain, scoring
from app.domain.options import OptionData, compute_options, requestable
from app.domain.rules import active_rule
from app.domain.snapshot import Snapshot, iso
from app.domain.state import force_states
from app.models import (Allocation, AllocationRun, Batch, Passenger, Request, Scenario, Seat, WaitlistEntry)
from app.serializers import allocation_dict
from app.services import audit
from app.services import notifications as notif
from app.services.scenarios import cfg
from app.ws.events import Event, ev

import structlog

log = structlog.get_logger()


@dataclass
class Pool:
    """Free seats of one service, deterministic order (regular first by seat_no, accessible by seat_no)."""
    reg: deque = field(default_factory=deque)   # (seat_id, seat_no)
    acc: deque = field(default_factory=deque)

    def free(self) -> int:
        return len(self.reg) + len(self.acc)

    def can(self, n: int, wheelchair: bool, accessible_ok: bool = True) -> bool:
        if wheelchair:
            return len(self.acc) >= 1 and self.free() >= n
        return (len(self.reg) + (len(self.acc) if accessible_ok else 0)) >= n

    def take(self, n: int, wheelchair: bool) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        if wheelchair:                       # one accessible seat for the wheelchair user, rest from regular first
            out.append(self.acc.popleft())
        while len(out) < n and self.reg:
            out.append(self.reg.popleft())
        while len(out) < n and self.acc:
            out.append(self.acc.popleft())
        return out


@dataclass
class Unit:
    p: Passenger
    req: Request | None
    c1: int | None
    c2: int | None
    any_fastest: bool
    score: float = 0.0
    points: dict = field(default_factory=dict)
    score_text: str = ""
    options: dict[int, OptionData] = field(default_factory=dict)
    order: list[int] = field(default_factory=list)
    ranks: dict[int, str] = field(default_factory=dict)
    old_alloc: Allocation | None = None
    key: tuple = ()
    placed_sid: int | None = None
    placed_seats: list[tuple[int, str]] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    waitlist_sids: list[int] = field(default_factory=list)
    outcome: str = ""      # placed | waitlisted | unresolved
    explanation: str = ""
    position: dict[int, int] = field(default_factory=dict)

    @property
    def need(self) -> int:
        return self.p.party_size

    @property
    def wc(self) -> bool:
        return bool(self.p.wheelchair)


@dataclass
class RunResult:
    run_id: int
    stats: dict[str, Any]
    events: list[Event]
    units: list[Unit]
    rule_version: int
    duration_ms: int


# ------------------------------------------------------------------------------------------------
async def load_units(session: AsyncSession, sc: Scenario, snap: Snapshot, batch: Batch | None, now: datetime,
                     weights: dict) -> list[Unit]:
    reqs: list[Request] = []
    if batch is not None:
        reqs = list((await session.execute(select(Request).where(Request.batch_id == batch.id, Request.status == "queued")
                                           .order_by(Request.id))).scalars())
    wl_rows = (await session.execute(
        select(WaitlistEntry, Passenger).join(Passenger, Passenger.id == WaitlistEntry.passenger_id)
        .where(WaitlistEntry.scenario_id == sc.id, WaitlistEntry.status == "active", WaitlistEntry.is_swap.is_(False),
               Passenger.state == "WAITLISTED").order_by(WaitlistEntry.id))).all()
    pids = {r.passenger_id for r in reqs} | {p.id for _, p in wl_rows}
    pax = {p.id: p for p in (await session.execute(select(Passenger).where(in_ids(Passenger.id, pids)))).scalars()} if pids else {}
    prim = {a.passenger_id: a for a in (await session.execute(select(Allocation).where(
        in_ids(Allocation.passenger_id, pids), Allocation.is_primary, Allocation.status.in_(("held", "confirmed"))))).scalars()} if pids else {}
    units: dict[int, Unit] = {}
    for r in reqs:
        p = pax.get(r.passenger_id)
        if p is None or p.state not in ("REQUESTED", "AFFECTED", "WAITLISTED", "UNRESOLVED", "REOFFER"):
            continue
        units[p.id] = Unit(p, r, r.choice1_service_id, r.choice2_service_id, r.any_fastest, old_alloc=prim.get(p.id))
    wl_by_p: dict[int, list[int]] = defaultdict(list)
    for e, p in wl_rows:
        wl_by_p[p.id].append(e.service_id)
    for pid, sids in wl_by_p.items():
        if pid in units or pid in prim:
            continue
        p = pax[pid]
        units[pid] = Unit(p, None, sids[0], sids[1] if len(sids) > 1 else None, False)
    out = list(units.values())
    cache: dict = {}
    for u in out:
        u.score, u.points, u.score_text = scoring.score(scoring.ScoreInput.of(u.p), weights, now)
        u.key = scoring.sort_key(u.score, u.p.affected_at, u.p.registered_at, u.p.id)
        opts = requestable(compute_options(snap, u.p, now, None, cache=cache))
        u.options = opts
        order: list[int] = []
        if not u.any_fastest:
            for sid in (u.c1, u.c2):
                if sid is not None and sid in opts and sid not in order:
                    order.append(sid)
        if u.any_fastest or u.p.allow_auto:
            order += [o.request_sid for o in sorted(opts.values(), key=lambda o: (o.eta_at, o.transfers, o.request_sid))
                      if o.request_sid not in order]
        u.order = order
        u.ranks = {u.c1: "1", u.c2: "2"} if not u.any_fastest else {}
        u.ranks = {k: v for k, v in u.ranks.items() if k is not None}
    out.sort(key=lambda u: u.key)
    return out


async def lock_pools(session: AsyncSession, sids: list[int]) -> dict[int, Pool]:
    pools = {sid: Pool() for sid in sids}
    if not sids:
        return pools
    rows = (await session.execute(
        select(Seat.id, Seat.service_id, Seat.seat_no, Seat.is_accessible)
        .where(Seat.service_id.in_(sids), Seat.status == "free")
        .order_by(Seat.service_id, Seat.is_accessible, Seat.seat_no).with_for_update(skip_locked=True))).all()
    for sid_, svc, no, acc in rows:
        (pools[svc].acc if acc else pools[svc].reg).append((sid_, no))
    return pools


def assign(units: list[Unit], pools: dict[str, Pool], snap: Snapshot, rule_version: int) -> dict[int, list[dict]]:
    """Pure in-memory two-pass placement. Returns takers per service (placement order) for explanations."""
    takers: dict[int, list[dict]] = defaultdict(list)

    def try_place(u: Unit, sid: int) -> bool:
        pool = pools.get(sid)
        if pool is None or not pool.can(u.need, u.wc):
            return False
        u.placed_seats = pool.take(u.need, u.wc)
        u.placed_sid = sid
        takers[sid].append({"score": u.score, "wheelchair": u.wc, "pid": u.p.id})
        return True

    def note_failure(u: Unit, sid: int) -> None:
        r = u.ranks.get(sid)
        if r is None:
            return
        sv = snap.services[sid]
        u.reasons.append(explain.full_reason(sv.label, r, takers.get(sid, []), u.score))

    # PASS 1 — wheelchair units get first call on accessible seats (F8.4)
    for u in units:
        if not u.wc:
            continue
        for sid in u.order:
            if try_place(u, sid):
                break
            note_failure(u, sid)
    # PASS 2 — everyone else, in priority order (accessible seats were released to the general pool)
    for u in units:
        if u.placed_sid is not None or u.wc:
            continue
        for sid in u.order:
            if try_place(u, sid):
                break
            note_failure(u, sid)
    return takers


# ------------------------------------------------------------------------------------------------
async def start_run(session_factory, sc_id: int, batch_id: int | None, mode: str) -> int:
    """Insert the run row in its own transaction so `allocation.run_started` can carry a real run id."""
    async with session_factory() as s:
        run = AllocationRun(scenario_id=sc_id, batch_id=batch_id, mode=mode, started_at=clock.utcnow(), stats={})
        s.add(run)
        await s.commit()
        return run.id


async def run_allocation(session: AsyncSession, sc: Scenario, *, batch: Batch | None, run_id: int | None = None,
                         mode: str = "greedy", now: datetime | None = None, preview: bool = False,
                         weights_override: dict | None = None) -> RunResult:
    """Run the engine. With ``preview=True`` nothing may be committed by the caller (it rolls back) and no
    events are meaningful. Returns stats + events (to publish after commit)."""
    t_start = time.perf_counter()
    tm: dict[str, int] = {}

    def lap(name: str) -> None:
        tm[name] = int((time.perf_counter() - t_start) * 1000)
    now = now or clock.utcnow()
    from app.db import acquire_xact_lock
    await acquire_xact_lock(session, "alloc", sc.id)                 # one run at a time per scenario (F8.7)
    rule = await active_rule(session, sc)
    weights = weights_override or rule.weights
    lap('lock')
    snap = await Snapshot.load(session, sc)
    lap('snapshot')
    units = await load_units(session, sc, snap, batch, now, weights)
    lap('load_units')
    inv = [sid for sid, sv in snap.services.items() if sv.has_seat_inventory and sv.status in ("scheduled", "delayed", "rerouted", "running")]
    pools = await lock_pools(session, inv)
    lap('pools')
    takers = assign(units, pools, snap, rule.version)
    lap('assign')

    hold_s = int(cfg(sc)["hold_seconds"])
    placed = [u for u in units if u.placed_sid is not None]
    # ---- unplaced: waitlist on choice services, else unresolved
    for u in units:
        if u.placed_sid is not None:
            u.outcome = "placed"
            continue
        if u.any_fastest:
            wl = []
        else:
            wl = [sid for sid in (u.c1, u.c2) if sid is not None and sid in u.options]
        u.waitlist_sids = list(dict.fromkeys(wl))
        u.outcome = "waitlisted" if u.waitlist_sids else "unresolved"
    wl_order: dict[int, list[Unit]] = defaultdict(list)
    for u in units:                                   # `units` is in score order -> position = index
        for sid in u.waitlist_sids:
            wl_order[sid].append(u)
    for sid, lst in wl_order.items():
        for i, u in enumerate(lst, 1):
            u.position[sid] = i

    # ---- explanations
    for u in units:
        if u.outcome == "placed":
            sv = snap.services[u.placed_sid]
            rank = u.ranks.get(u.placed_sid, "auto")
            opt = u.options[u.placed_sid]
            u.explanation = explain.placed(rank, sv.label, [no for _, no in u.placed_seats], u.reasons, u.score_text,
                                           rule.version, u.any_fastest, opt.eta_at.strftime("%H:%M"))
        elif u.outcome == "waitlisted":
            reasons = list(u.reasons)
            if not reasons:
                reasons = [f"Your choices are full."]
            waits = [(snap.services[s].label, u.position[s]) for s in u.waitlist_sids]
            u.explanation = explain.waitlisted(reasons, waits, u.score_text, rule.version)
        else:
            reasons = list(u.reasons) or (["No feasible service matches your needs and deadline."] if not u.order else
                                          ["Every feasible service is full."])
            u.explanation = explain.unresolved(reasons, u.score_text, rule.version)

    events: list[Event] = []
    run_id = run_id
    if run_id is None:
        run = AllocationRun(scenario_id=sc.id, batch_id=batch.id if batch else None, mode="preview" if preview else mode,
                            started_at=now, stats={})
        session.add(run)
        await session.flush()
        run_id = run.id
    run_row = await session.get(AllocationRun, run_id)
    run_row.rule_version_id = rule.id or None

    # ---- persist placements (REOFFER units replace their old seat atomically)
    release_ids = [u.old_alloc.id for u in placed if u.old_alloc is not None]
    if release_ids:
        await session.execute(update(Allocation).where(Allocation.id.in_(release_ids)).values(status="released", updated_at=now))
        await session.execute(update(Seat).where(Seat.allocation_id.in_(release_ids)).values(status="free", allocation_id=None))
        for u in placed:
            if u.old_alloc is not None:
                events.append(ev("seat.released", {"service_id": u.old_alloc.service_id, "count": u.old_alloc.seat_count}, ops=True))
    alloc_rows = []
    for u in placed:
        rank = u.ranks.get(u.placed_sid, "auto")
        alloc_rows.append(dict(
            scenario_id=sc.id, run_id=run_id, passenger_id=u.p.id, service_id=u.placed_sid, seat_count=u.need,
            choice_rank=rank, status="held", is_primary=True, hold_expires_at=now + timedelta(seconds=hold_s),
            expiring_notified=False, score=u.score, score_breakdown=u.points, explanation=u.explanation,
            created_at=now, updated_at=now))
    ids = {pid: aid for aid, pid in await bulk(session, Allocation, alloc_rows, (Allocation.id, Allocation.passenger_id))}
    seat_map = [{"id": sid_, "aid": ids[u.p.id]} for u in placed for sid_, _ in u.placed_seats]
    if seat_map:
        await session.execute(text(
            "UPDATE seats s SET status='held', allocation_id=v.aid FROM jsonb_to_recordset(CAST(:d AS jsonb)) "
            "AS v(id bigint, aid bigint) WHERE s.id=v.id AND s.status='free'"), {"d": json.dumps(seat_map)})

    # ---- waitlists (delete + re-insert for every unit's non-swap entries)
    unit_pids = [u.p.id for u in units]
    if unit_pids:
        await session.execute(text("DELETE FROM waitlist_entries WHERE passenger_id = ANY(:p) AND NOT is_swap"), {"p": unit_pids})
    wl_rows = []
    for u in units:
        for sid in u.waitlist_sids:
            # a REOFFER passenger who keeps their seat waits as a *swap* request
            wl_rows.append(dict(scenario_id=sc.id, service_id=sid, passenger_id=u.p.id, is_swap=u.old_alloc is not None,
                                score=u.score, score_breakdown=u.points, status="active", created_at=now,
                                last_position=u.position.get(sid)))
    if wl_rows:
        await bulk(session, WaitlistEntry, wl_rows)

    lap('persist_alloc')
    # ---- passenger states (set-based), requests, batch
    by_state: dict[str, list[int]] = defaultdict(list)
    for u in units:
        if u.outcome == "placed":
            by_state["HELD"].append(u.p.id)
        elif u.old_alloc is not None:                       # REOFFER passenger keeps the old seat; state restored
            by_state["CONFIRMED" if u.old_alloc.status == "confirmed" else "HELD"].append(u.p.id)
        elif u.outcome == "waitlisted":
            by_state["WAITLISTED"].append(u.p.id)
        else:
            by_state["UNRESOLVED"].append(u.p.id)
    await force_states(session, by_state)
    req_ids = [u.req.id for u in units if u.req is not None]
    if req_ids:
        await session.execute(update(Request).where(in_ids(Request.id, req_ids)).values(status="processed"))
    if batch is not None and batch.status in ("closed", "open"):
        batch.status = "allocated"

    # ---- notifications, audit, events
    notes, audit_rows = [], []
    for u in units:
        pid, sc_id = u.p.id, sc.id
        if u.outcome == "placed":
            sv = snap.services[u.placed_sid]
            rank = u.ranks.get(u.placed_sid, "auto")
            notes.append(notif.make(u.p, "placed" if rank in ("1", "2") else "moved",
                                    {"service": sv.label, "seats": ", ".join(no for _, no in u.placed_seats),
                                     "minutes": max(1, hold_s // 60), "why": u.explanation}))
            audit_rows.append(audit.row(sc_id, "allocation.placed", "allocation", ids[pid], u.explanation, passenger_id=pid,
                                        payload={"score": u.score, "rank": rank, "service_id": u.placed_sid, "run_id": run_id}))
            alloc = allocation_dict(snap, ids[pid], u.placed_sid, u.need, [no for _, no in u.placed_seats], rank, "held", True,
                                    now + timedelta(seconds=hold_s), u.score, u.explanation)
            events.append(ev("allocation.result", {"state": "HELD", "allocation": alloc, "explanation": u.explanation}, to=[pid]))
        elif u.outcome == "waitlisted":
            first = u.waitlist_sids[0]
            notes.append(notif.make(u.p, "waitlisted", {"service": snap.services[first].label, "position": u.position[first]}))
            audit_rows.append(audit.row(sc_id, "allocation.waitlisted", "passenger", pid, u.explanation, passenger_id=pid,
                                        payload={"score": u.score, "waitlist": u.waitlist_sids, "run_id": run_id}))
            events.append(ev("allocation.result", {"state": "WAITLISTED" if u.old_alloc is None else u.p.state,
                                                   "allocation": None, "explanation": u.explanation}, to=[pid]))
            for sid in u.waitlist_sids:
                events.append(ev("waitlist.position_changed", {"service_id": sid, "position": u.position[sid],
                                                               "total": len(wl_order[sid])}, to=[pid]))
        else:
            notes.append(notif.make(u.p, "unresolved"))
            audit_rows.append(audit.row(sc_id, "allocation.unresolved", "passenger", pid, u.explanation, passenger_id=pid,
                                        payload={"score": u.score, "run_id": run_id}))
            events.append(ev("allocation.result", {"state": "UNRESOLVED", "allocation": None, "explanation": u.explanation}, to=[pid]))
    lap('states')
    await audit.write(session, audit_rows)
    lap('audit')
    note_events = await notif.emit(session, notes)

    lap('notif')
    # ---- stats
    c1 = sum(1 for u in placed if u.ranks.get(u.placed_sid) == "1")
    c2 = sum(1 for u in placed if u.ranks.get(u.placed_sid) == "2")
    fill = []
    for sid in inv:
        sv = snap.services[sid]
        if sv.total_seats:
            fill.append({"service_id": sid, "label": sv.label, "fill_rate": round(1 - pools[sid].free() / sv.total_seats, 3)})
    stats = {"units": len(units), "placed_choice1": c1, "placed_choice2": c2, "placed_auto": len(placed) - c1 - c2,
             "waitlisted": sum(1 for u in units if u.outcome == "waitlisted"),
             "unresolved": sum(1 for u in units if u.outcome == "unresolved"),
             "duration_ms": int((time.perf_counter() - t_start) * 1000), "fill_rate_by_service": fill}
    log.info("allocation_run", scenario=sc.slug, preview=preview, timings_ms=tm, units=len(units))
    run_row.finished_at = clock.utcnow()
    run_row.stats = stats
    await session.flush()
    events = events + note_events + [ev("allocation.run_completed", {"run_id": run_id, "stats": stats}, ops=True)]
    return RunResult(run_id, stats, events, units, rule.version, stats["duration_ms"])
