"""Audit log writer (PRD F8.6, F17.4): every allocation-affecting decision is recorded with an explanation."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.dbutil import bulk
from app.models import AuditLog


def row(scenario_id: int, action: str, entity_type: str, entity_id: int | None, explanation: str = "", *,
        actor: str = "system", actor_id: int | None = None, passenger_id: int | None = None,
        payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(scenario_id=scenario_id, actor=actor, actor_id=actor_id, action=action, entity_type=entity_type,
                entity_id=entity_id, passenger_id=passenger_id, payload=payload or {}, explanation=explanation,
                created_at=clock.utcnow())


async def write(session: AsyncSession, rows: list[dict[str, Any]]) -> None:
    """Bulk-insert audit rows built with :func:`row` (one round-trip)."""
    await bulk(session, AuditLog, rows)
