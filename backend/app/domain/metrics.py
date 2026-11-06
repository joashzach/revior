"""Dashboard metrics (PRD F18.1): KPI snapshot."""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import batches as batches_dom
from app.models import Scenario
from app.serializers import batch_out

_STATE_COUNTS = """
SELECT
  count(*) FILTER (WHERE affected_at IS NOT NULL) AS affected,
  count(*) FILTER (WHERE affected_at IS NOT NULL AND state = 'AFFECTED') AS not_checked_in,
  count(*) FILTER (WHERE state = 'REQUESTED') AS requested,
  count(*) FILTER (WHERE state = 'HELD') AS held,
  count(*) FILTER (WHERE state = 'CONFIRMED') AS confirmed,
  count(*) FILTER (WHERE state = 'WAITLISTED') AS waitlisted,
  count(*) FILTER (WHERE state = 'UNRESOLVED') AS unresolved,
  count(*) FILTER (WHERE state = 'RESOLVED_ALT') AS resolved_alt
FROM passengers WHERE scenario_id = :sid
"""
_WAIT = """
SELECT
  COALESCE(avg(EXTRACT(EPOCH FROM (COALESCE(a.first_at, now()) - p.affected_at)) / 60), 0) AS avg_wait,
  COALESCE(percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (a.first_at - p.affected_at)) / 60)
           FILTER (WHERE a.first_at IS NOT NULL), 0) AS median_place
FROM passengers p
LEFT JOIN (SELECT passenger_id, min(created_at) AS first_at FROM allocations WHERE scenario_id = :sid GROUP BY passenger_id) a
       ON a.passenger_id = p.id
WHERE p.scenario_id = :sid AND p.affected_at IS NOT NULL
"""
_FILL = """
SELECT COALESCE(sum(t.total), 0), COALESCE(sum(t.used), 0) FROM (
  SELECT s.id, s.total_seats AS total, count(x.id) FILTER (WHERE x.status <> 'free') AS used
  FROM services s LEFT JOIN seats x ON x.service_id = s.id
  WHERE s.scenario_id = :sid AND s.has_seat_inventory AND s.status NOT IN ('cancelled') GROUP BY s.id) t
"""


async def kpis(session: AsyncSession, sc: Scenario) -> dict[str, Any]:
    p = {"sid": sc.id}
    row = (await session.execute(text(_STATE_COUNTS), p)).mappings().one()
    w = (await session.execute(text(_WAIT), p)).mappings().one()
    total, used = (await session.execute(text(_FILL), p)).one()
    b = await batches_dom.open_batch_row(session, sc)
    affected = int(row["affected"])
    return {
        "affected": affected, "checked_in": affected - int(row["not_checked_in"]), "not_checked_in": int(row["not_checked_in"]),
        "requested": int(row["requested"]), "held": int(row["held"]), "confirmed": int(row["confirmed"]),
        "waitlisted": int(row["waitlisted"]), "unresolved": int(row["unresolved"]), "resolved_alt": int(row["resolved_alt"]),
        "avg_wait_min": round(float(w["avg_wait"]), 1), "median_time_to_placement_min": round(float(w["median_place"]), 1),
        "fill_rate": round(float(used) / float(total), 3) if total else 0.0, "batch": batch_out(b) if b else None,
    }
