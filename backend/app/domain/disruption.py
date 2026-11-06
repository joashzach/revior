"""Disruptions: helpers used by registration and persona release (full cancel/delay/closure logic follows)."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.domain.state import transition
from app.models import Disruption, Passenger, PassengerDisruption, Scenario, Service, ServiceStop
from app.services.scenarios import cfg


async def service_is_disrupting(session: AsyncSession, sc: Scenario, svc: Service, p: Passenger) -> bool:
    if svc.status == "cancelled":
        return True
    if svc.delay_minutes and svc.delay_minutes > 0:
        if svc.delay_minutes >= int(cfg(sc)["delay_threshold_minutes"]):
            return True
        if p.connection_deadline_at is not None:
            arr = (await session.execute(select(ServiceStop.arrive_at).where(
                ServiceStop.service_id == svc.id, ServiceStop.node_id == p.destination_node_id))).scalar()
            if arr and arr + timedelta(minutes=svc.delay_minutes) > p.connection_deadline_at:
                return True
    return False


async def initial_state_for(session: AsyncSession, sc: Scenario, p: Passenger) -> bool:
    """A passenger whose ticket service is already disrupted starts out AFFECTED (not BOOKED)."""
    if p.ticket_service_id is None:
        return False
    svc = await session.get(Service, p.ticket_service_id)
    if svc is None or not await service_is_disrupting(session, sc, svc, p):
        return False
    transition(p, "AFFECTED", force=True)
    p.affected_at = clock.utcnow()
    d = (await session.execute(select(Disruption).where(
        Disruption.scenario_id == sc.id, Disruption.service_id == svc.id, Disruption.resolved_at.is_(None))
        .order_by(Disruption.id.desc()))).scalars().first()
    if d is not None and await session.get(PassengerDisruption, (p.id, d.id)) is None:
        session.add(PassengerDisruption(passenger_id=p.id, disruption_id=d.id, affected_at=p.affected_at))
    return True
