"""Versioned priority rules (PRD F7.5, F17) and live waitlist ranking (F10.3)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.domain import scoring
from app.errors import AppError
from app.models import Passenger, PriorityRule, Scenario, WaitlistEntry


async def active_rule(session: AsyncSession, sc: Scenario) -> PriorityRule:
    r = (await session.execute(select(PriorityRule).where(PriorityRule.scenario_id == sc.id, PriorityRule.is_active))).scalars().first()
    if r is None:  # defensive: scenario without rules -> defaults as version 0 (not persisted)
        r = PriorityRule(id=0, scenario_id=sc.id, version=0, weights=dict(scoring.DEFAULT_WEIGHTS), is_active=True)
    return r


def validate_weights(w: dict[str, float]) -> dict[str, float]:
    bad = [k for k in w if k not in scoring.FEATURES]
    if bad:
        raise AppError("VALIDATION_ERROR", f"Unknown weight(s): {', '.join(bad)}", {"fields": {"weights": f"unknown keys {bad}"}})
    out = {}
    for k in scoring.FEATURES:
        v = float(w.get(k, 0))
        if v < 0 or v > 100:
            raise AppError("VALIDATION_ERROR", f"Weight {k} must be between 0 and 100", {"fields": {"weights": f"{k} out of range"}})
        out[k] = v
    return out


async def rank_waitlist(session: AsyncSession, sc: Scenario, weights: dict[str, Any], now: datetime,
                        service_id: int, *, include_swap: bool = True) -> list[dict[str, Any]]:
    """Active waitlist of ``service_id`` ordered by *current* priority (scores recomputed at ``now``)."""
    q = (select(WaitlistEntry, Passenger).join(Passenger, Passenger.id == WaitlistEntry.passenger_id)
         .where(WaitlistEntry.service_id == service_id, WaitlistEntry.status == "active"))
    rows = (await session.execute(q.execution_options(populate_existing=True))).all()
    ranked = []
    for e, p in rows:
        if not include_swap and e.is_swap:
            continue
        s, pts, text = scoring.score(scoring.ScoreInput.of(p), weights, now)
        ranked.append({"entry": e, "passenger": p, "score": s, "points": pts, "text": text,
                       "key": scoring.sort_key(s, p.affected_at, p.registered_at, p.id)})
    ranked.sort(key=lambda r: r["key"])
    return ranked


async def positions_for(session: AsyncSession, sc: Scenario, snap, passenger_id: int, weights: dict[str, Any],
                        now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or clock.utcnow()
    sids = [s for (s,) in (await session.execute(select(WaitlistEntry.service_id).where(
        WaitlistEntry.passenger_id == passenger_id, WaitlistEntry.status == "active").order_by(WaitlistEntry.id))).all()]
    out = []
    for sid in sids:
        ranked = await rank_waitlist(session, sc, weights, now, sid)
        for i, r in enumerate(ranked, 1):
            if r["passenger"].id == passenger_id:
                out.append({"service_id": sid, "label": snap.services[sid].label, "position": i, "total": len(ranked),
                            "is_swap": r["entry"].is_swap})
    return out
