from sqlalchemy.ext.asyncio import AsyncSession

from app.ws.events import Event
from app.ws.hub import hub


async def finish(session: AsyncSession, events: list[Event], scenario_slug: str) -> None:
    """Commit, then publish (events are never sent before the transaction is durable). Any committed
    mutation marks the KPI snapshot dirty so ops dashboards refresh within a second."""
    await session.commit()
    hub.kpi_dirty[scenario_slug] = True
    if events:
        await hub.publish(events, scenario_slug)
