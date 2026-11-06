"""Cascade of freed seats to the waitlist (placeholder until the seat-hold work lands)."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Scenario
from app.ws.events import Event


async def run_cascade(session: AsyncSession, sc: Scenario, service_ids: list[int]) -> list[Event]:
    return []
