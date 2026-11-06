"""Priority-rules editor (PRD F17): history, dry-run preview (rolled back), apply + live re-rank."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.db import get_sessionmaker
from app.domain import allocation as alloc_dom
from app.domain import batches as batches_dom
from app.domain.analytics import needs_class
from app.domain.cascade import refresh_positions
from app.domain.rules import active_rule, rank_waitlist, validate_weights
from app.domain.snapshot import Snapshot, iso
from app.models import Passenger, PriorityRule, Scenario, WaitlistEntry
from app.services import audit
from app.ws.events import Event, ev

PLACED = ("HELD", "CONFIRMED", "RESOLVED_ALT")


def merged(current: dict, given: dict[str, float]) -> dict[str, float]:
    return validate_weights({**{k: float(v) for k, v in current.items()}, **given})


async def history(session: AsyncSession, sc: Scenario) -> dict[str, Any]:
    rows = (await session.execute(select(PriorityRule).where(PriorityRule.scenario_id == sc.id)
                                  .order_by(PriorityRule.version.desc()))).scalars().all()
    act = next((r for r in rows if r.is_active), None)
    return {"active": {"version": act.version, "weights": {k: float(v) for k, v in act.weights.items()}} if act else
            {"version": 0, "weights": {}},
            "history": [{"version": r.version, "weights": {k: float(v) for k, v in r.weights.items()}, "created_at": iso(r.created_at)}
                        for r in rows]}


async def _wait_positions(session, sc, weights, now) -> dict[tuple[int, int], tuple[int, str]]:
    """{(service_id, passenger_id): (position, passenger name)} for the active plain waitlists."""
    sids = [s for (s,) in (await session.execute(select(WaitlistEntry.service_id).where(
        WaitlistEntry.scenario_id == sc.id, WaitlistEntry.status == "active").distinct())).all()]
    out = {}
    for sid in sids:
        for i, r in enumerate(await rank_waitlist(session, sc, weights, now, sid), 1):
            out[(sid, r["passenger"].id)] = (i, r["passenger"].name)
    return out


async def _simulate(sc_id: int, batch_id: int | None, weights: dict) -> set[int]:
    """Run the real engine on the current snapshot with ``weights`` inside a transaction that is rolled back."""
    async with get_sessionmaker()() as s:
        sc = await s.get(Scenario, sc_id)
        batch = await s.get(batches_dom.Batch, batch_id) if batch_id else None
        res = await alloc_dom.run_allocation(s, sc, batch=batch, preview=True, weights_override=weights)
        placed = {u.p.id for u in res.units if u.placed_sid is not None}
        await s.rollback()                                           # nothing is ever committed
        return placed


async def preview(session: AsyncSession, sc: Scenario, given: dict[str, float]) -> dict[str, Any]:
    now = clock.utcnow()
    old_rule = await active_rule(session, sc)
    old_w = {k: float(v) for k, v in old_rule.weights.items()}
    new_w = merged(old_w, given)
    snap = await Snapshot.load(session, sc)
    # ---- waitlist movers (pure re-scoring)
    before = await _wait_positions(session, sc, old_w, now)
    after = await _wait_positions(session, sc, new_w, now)
    movers = [{"passenger_id": pid, "name": name, "service_label": snap.services[sid].label,
               "position_before": b, "position_after": after[(sid, pid)][0]}
              for (sid, pid), (b, name) in before.items() if (sid, pid) in after and after[(sid, pid)][0] != b]
    movers.sort(key=lambda m: (-abs(m["position_before"] - m["position_after"]), m["passenger_id"]))
    # ---- simulated next run under old vs new weights
    batch = await batches_dom.current_batch(session, sc)
    bid = batch.id if batch else None
    sid_ = sc.id
    await session.rollback()
    placed_old = await _simulate(sid_, bid, old_w)
    placed_new = await _simulate(sid_, bid, new_w)
    sc = await session.get(Scenario, sid_)
    pax = (await session.execute(select(Passenger).where(Passenger.scenario_id == sid_, Passenger.affected_at.is_not(None)))).scalars().all()
    cls_of = {p.id: needs_class(p) for p in pax}
    checked: dict[str, int] = defaultdict(int)
    placed_now: dict[str, int] = defaultdict(int)
    for p in pax:
        if p.state != "AFFECTED":
            checked[cls_of[p.id]] += 1
        if p.state in PLACED:
            placed_now[cls_of[p.id]] += 1

    def rate(cls: str, sim: set[int]) -> float:
        extra = sum(1 for pid in sim if cls_of.get(pid) == cls)
        return round((placed_now[cls] + extra) / checked[cls], 3) if checked[cls] else 0.0
    return {"placed_delta": len(placed_new) - len(placed_old),
            "by_needs_class": [{"needs_class": c, "placement_rate_before": rate(c, placed_old), "placement_rate_after": rate(c, placed_new)}
                               for c in ("accessible", "priority", "general")],
            "movers": movers[:20]}


async def apply(session: AsyncSession, sc: Scenario, given: dict[str, float]) -> tuple[int, list[Event]]:
    """New active version; waitlists re-rank live; held/confirmed allocations are never touched (F17.2)."""
    now = clock.utcnow()
    old = await active_rule(session, sc)
    new_w = merged(old.weights, given)
    top = (await session.execute(select(PriorityRule.version).where(PriorityRule.scenario_id == sc.id)
                                 .order_by(PriorityRule.version.desc()).limit(1))).scalar() or 0
    snap = await Snapshot.load(session, sc)
    await session.execute(update(PriorityRule).where(PriorityRule.scenario_id == sc.id, PriorityRule.is_active).values(is_active=False))
    await session.flush()
    rule = PriorityRule(scenario_id=sc.id, version=top + 1, weights=new_w, is_active=True, created_at=now)
    session.add(rule)
    await session.flush()
    sids = [s for (s,) in (await session.execute(select(WaitlistEntry.service_id).where(
        WaitlistEntry.scenario_id == sc.id, WaitlistEntry.status == "active").distinct())).all()]
    events = await refresh_positions(session, sc, snap, new_w, now, sids)
    events.append(ev("rules.updated", {"version": rule.version}, ops=True, everyone=True))
    changed = {k: (old.weights.get(k), new_w[k]) for k in new_w if float(old.weights.get(k, 0)) != new_w[k]}
    await audit.write(session, [audit.row(sc.id, "rules.applied", "rules", rule.id,
                                          f"Operator applied priority rules v{rule.version}: "
                                          + (", ".join(f"{k} {a:g}→{b:g}" for k, (a, b) in changed.items()) or "no change")
                                          + ". Waitlists re-ranked; held and confirmed seats untouched.", actor="operator",
                                          payload={"weights": new_w})])
    return rule.version, events
