"""Invariant checker (PRD F18.8): must always be zero. Runs in REPEATABLE READ for a consistent snapshot."""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_OVER = """
SELECT count(*) FROM (
  SELECT s.id FROM services s LEFT JOIN allocations a ON a.service_id = s.id AND a.status IN ('held','swap_held','confirmed')
  WHERE s.scenario_id = :sid AND s.has_seat_inventory
  GROUP BY s.id, s.total_seats HAVING COALESCE(sum(a.seat_count), 0) > s.total_seats) x
"""
_MULTI = """
SELECT count(*) FROM (
  SELECT passenger_id FROM allocations WHERE scenario_id = :sid AND is_primary AND status IN ('held','confirmed')
  GROUP BY passenger_id HAVING count(*) > 1) x
"""
_NEG = """
SELECT count(*) FROM (
  SELECT s.id FROM services s LEFT JOIN seats t ON t.service_id = s.id AND t.status <> 'free'
  WHERE s.scenario_id = :sid AND s.has_seat_inventory
  GROUP BY s.id, s.total_seats HAVING s.total_seats - count(t.id) < 0) x
"""
# stronger bookkeeping checks (used by tests / stress run): seats <-> allocations agree both ways
_ORPHAN_SEATS = """
SELECT count(*) FROM seats t JOIN services s ON s.id = t.service_id
LEFT JOIN allocations a ON a.id = t.allocation_id AND a.status IN ('held','swap_held','confirmed')
WHERE s.scenario_id = :sid AND t.status <> 'free' AND a.id IS NULL
"""
_SEAT_MISMATCH = """
SELECT count(*) FROM allocations a
WHERE a.scenario_id = :sid AND a.status IN ('held','swap_held','confirmed')
  AND a.seat_count <> (SELECT count(*) FROM seats t WHERE t.allocation_id = a.id)
"""
_MULTI_SWAP = """
SELECT count(*) FROM (SELECT passenger_id FROM allocations WHERE scenario_id = :sid AND status = 'swap_held'
                      GROUP BY passenger_id HAVING count(*) > 1) x
"""


async def check(session: AsyncSession, scenario_id: int, *, deep: bool = False) -> dict[str, Any]:
    await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
    q = lambda sql: session.execute(text(sql), {"sid": scenario_id})  # noqa: E731
    over = (await q(_OVER)).scalar()
    multi = (await q(_MULTI)).scalar()
    neg = (await q(_NEG)).scalar()
    out: dict[str, Any] = {"over_allocated_services": over, "multi_primary_passengers": multi,
                           "negative_free_seats": neg, "ok": over == 0 and multi == 0 and neg == 0}
    if deep:
        out["orphan_seats"] = (await q(_ORPHAN_SEATS)).scalar()
        out["seat_mismatch"] = (await q(_SEAT_MISMATCH)).scalar()
        out["multi_swap"] = (await q(_MULTI_SWAP)).scalar()
        out["ok"] = out["ok"] and out["orphan_seats"] == 0 and out["seat_mismatch"] == 0 and out["multi_swap"] == 0
    return out
