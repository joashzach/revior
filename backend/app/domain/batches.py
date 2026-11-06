"""Batch lifecycle (PRD F6): open -> closed -> allocated; at most one open batch per scenario."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models import Batch, Request, Scenario
from app.serializers import batch_out
from app.services.scenarios import cfg
from app.ws.events import Event, ev


async def open_batch_row(session: AsyncSession, sc: Scenario) -> Batch | None:
    return (await session.execute(select(Batch).where(Batch.scenario_id == sc.id, Batch.status == "open")
                                  .order_by(Batch.id.desc()))).scalars().first()


async def current_batch(session: AsyncSession, sc: Scenario) -> Batch | None:
    """The open batch, else the latest closed-but-unallocated one."""
    b = await open_batch_row(session, sc)
    if b is not None:
        return b
    return (await session.execute(select(Batch).where(Batch.scenario_id == sc.id, Batch.status == "closed")
                                  .order_by(Batch.id.desc()))).scalars().first()


async def get_or_open_batch(session: AsyncSession, sc: Scenario, trigger: str, now: datetime,
                            audience: list[int] | None = None) -> tuple[Batch, list[Event]]:
    """Return the open batch or open a new one (``batch.opened`` event only when created)."""
    b = await open_batch_row(session, sc)
    if b is not None:
        return b, []
    window = int(cfg(sc)["batch_window_seconds"])
    b = Batch(scenario_id=sc.id, status="open", opens_at=now, closes_at=now + timedelta(seconds=window), trigger=trigger)
    try:
        async with session.begin_nested():
            session.add(b)
            await session.flush()
    except IntegrityError:  # lost the race for the partial unique index -> use the winner
        b = await open_batch_row(session, sc)
        return b, []
    return b, [ev("batch.opened", {"batch_id": b.id, "closes_at": b.closes_at.isoformat()}, ops=True,
                  to=audience or [], everyone=audience is None)]


async def request_count(session: AsyncSession, b: Batch) -> int:
    return (await session.execute(select(func.count()).select_from(Request).where(
        Request.batch_id == b.id, Request.status == "queued"))).scalar() or 0


async def close_batch(session: AsyncSession, sc: Scenario, b: Batch, now: datetime) -> list[Event]:
    if b.status != "open":
        raise AppError("INVALID_STATE", "Batch is not open")
    b.status = "closed"
    b.closes_at = min(b.closes_at, now)
    passenger_ids = [r for (r,) in (await session.execute(select(Request.passenger_id).where(
        Request.batch_id == b.id, Request.status == "queued"))).all()]
    return [ev("batch.closed", {"batch_id": b.id, "closes_at": b.closes_at.isoformat()}, ops=True, to=passenger_ids)]


async def due_open_batches(session: AsyncSession, now: datetime) -> list[Batch]:
    return list((await session.execute(select(Batch).where(Batch.status == "open", Batch.closes_at <= now))).scalars())
