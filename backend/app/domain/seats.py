"""Seat locking: every path that takes a seat uses ``SELECT ... FOR UPDATE SKIP LOCKED`` (PRD §9.1)."""
from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Seat


async def lock_seats(session: AsyncSession, service_id: int, n: int, *, wheelchair: bool,
                     accessible_ok: bool = True) -> list[Seat] | None:
    """Lock exactly ``n`` free seats of a service or return None (never a partial set).
    Wheelchair unit: one accessible seat + the rest regular-first. Others: regular first, accessible only if
    ``accessible_ok``."""
    out: list[Seat] = []
    if wheelchair:
        acc = (await session.execute(select(Seat).where(Seat.service_id == service_id, Seat.status == "free", Seat.is_accessible)
                                     .order_by(Seat.seat_no).limit(1).with_for_update(skip_locked=True))).scalars().all()
        if not acc:
            return None
        out += acc
    need = n - len(out)
    if need > 0:
        q = select(Seat).where(Seat.service_id == service_id, Seat.status == "free", Seat.id.not_in([s.id for s in out]) if out else True)
        if not accessible_ok and not wheelchair:
            q = q.where(Seat.is_accessible.is_(False))
        rest = (await session.execute(q.order_by(Seat.is_accessible, Seat.seat_no).limit(need).with_for_update(skip_locked=True))).scalars().all()
        out += rest
    return out if len(out) == n else None


async def assign_seats(session: AsyncSession, seats: list[Seat], allocation_id: int, status: str = "held") -> None:
    await session.execute(update(Seat).where(Seat.id.in_([s.id for s in seats])).values(status=status, allocation_id=allocation_id))


async def free_seats(session: AsyncSession, allocation_ids: list[int]) -> None:
    if allocation_ids:
        await session.execute(update(Seat).where(Seat.allocation_id.in_(allocation_ids)).values(status="free", allocation_id=None))
