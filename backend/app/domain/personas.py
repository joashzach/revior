"""Demo personas (PRD F24): atomic claim, release, switch, auto-create."""
from __future__ import annotations

import random

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.domain import cascade
from app.domain.snapshot import Snapshot
from app.domain.state import transition
from app.domain.tickets import new_ticket_id
from app.errors import AppError
from app.models import (Allocation, LoginToken, Notification, Passenger, PodMember, Request, Scenario, Seat,
                        WaitlistEntry, PassengerDisruption)
from app.security import hash_password
from app.ws.events import Event, ev
from app.config import get_settings


async def list_personas(session: AsyncSession, sc: Scenario) -> list[Passenger]:
    return list((await session.execute(select(Passenger).where(
        Passenger.scenario_id == sc.id, Passenger.is_demo_persona).order_by(Passenger.id))).scalars())


async def claim(session: AsyncSession, sc: Scenario, *, persona_id: int | None, surprise: bool,
                exclude_id: int | None = None) -> tuple[Passenger, list[Event]]:
    """Atomically claim a persona. Row-locks the candidate(s); a persona already claimed -> PERSONA_TAKEN."""
    if persona_id is not None:
        p = (await session.execute(select(Passenger).where(
            Passenger.id == persona_id, Passenger.scenario_id == sc.id, Passenger.is_demo_persona)
            .with_for_update())).scalars().first()
        if p is None:
            raise AppError("NOT_FOUND", "Unknown persona")
        if p.persona_claimed_at is not None:
            raise AppError("PERSONA_TAKEN", "Someone just picked that one")
    elif surprise:
        free = list((await session.execute(select(Passenger).where(
            Passenger.scenario_id == sc.id, Passenger.is_demo_persona, Passenger.persona_claimed_at.is_(None),
            Passenger.id != (exclude_id or -1)).order_by(Passenger.id).with_for_update(skip_locked=True))).scalars())
        p = random.choice(free) if free else await _create_surprise(session, sc)
    else:
        raise AppError("VALIDATION_ERROR", "Provide persona_id or surprise=true", {"fields": {"persona_id": "required"}})
    p.persona_claimed_at = clock.utcnow()
    p.token_version += 1
    await session.flush()
    return p, [ev("persona.claimed", {"persona_id": p.id}, ops=True)]


async def next_free(session: AsyncSession, sc: Scenario, after_id: int) -> Passenger | None:
    rows = list((await session.execute(select(Passenger).where(
        Passenger.scenario_id == sc.id, Passenger.is_demo_persona, Passenger.persona_claimed_at.is_(None))
        .order_by(Passenger.id).with_for_update(skip_locked=True))).scalars())
    if not rows:
        return None
    return next((r for r in rows if r.id > after_id), rows[0])


async def _create_surprise(session: AsyncSession, sc: Scenario) -> Passenger:
    """Pool empty -> create a new traveller with random needs on the featured service."""
    snap = await Snapshot.load(session, sc)
    rng = random.Random()
    feat = sc.featured_service_id
    served = [s.node_id for s in snap.served(feat)]
    hub = sc.default_hub_node_id
    dests = served[served.index(hub) + 1:] if hub in served else served[1:]
    dest = rng.choice(dests)
    need = rng.choice(["wheelchair", "elderly", "with_children", "medical", None, None])
    n_existing = (await session.execute(select(Passenger.id).where(
        Passenger.scenario_id == sc.id, Passenger.is_demo_persona))).all()
    k = len(n_existing) + 1
    while True:
        email = f"surprise-{k}@demo.revior.test"
        if not (await session.execute(select(Passenger.id).where(Passenger.scenario_id == sc.id,
                                                                  Passenger.email == email))).first():
            break
        k += 1
    labels = {"wheelchair": ("♿", "Needs accessible seat"), "elderly": ("👵", "Senior citizen"),
              "with_children": ("👨‍👩‍👧", "Travelling with a child"), "medical": ("🏥", "Medical priority"),
              None: ("🎲", "General traveller")}
    emoji, summ = labels[need]
    p = Passenger(
        scenario_id=sc.id, name=f"Surprise Traveller {k}", email=email,
        password_hash=await hash_password(get_settings().DEMO_PERSONA_PASSWORD),
        ticket_id=await new_ticket_id(session, sc.id), is_seeded=False, is_demo_persona=True,
        persona_title=f"Surprise traveller → {snap.nodes[dest].name}", persona_emoji=emoji,
        persona_summary=f"{summ} · random draw", party_size=1, hub_node_id=hub, destination_node_id=dest,
        ticket_service_id=feat, wheelchair=need == "wheelchair", elderly=need == "elderly",
        with_children=need == "with_children", medical=need == "medical", allow_auto=True, state="BOOKED",
        registered_at=clock.utcnow())
    session.add(p)
    await session.flush()
    return p


async def release(session: AsyncSession, sc: Scenario, p: Passenger) -> list[Event]:
    """Release a persona back to the pool: free its seats/waitlists/requests, reset its journey, bump
    token_version (old JWT -> 401) and revoke login QRs."""
    events: list[Event] = []
    freed_services: set[int] = set()
    allocs = (await session.execute(select(Allocation).where(
        Allocation.passenger_id == p.id, Allocation.status.in_(("held", "swap_held", "confirmed"))))).scalars().all()
    for a in allocs:
        a.status = "released"
        freed_services.add(a.service_id)
        events.append(ev("seat.released", {"service_id": a.service_id, "count": a.seat_count}, ops=True))
    if allocs:
        await session.execute(update(Seat).where(Seat.allocation_id.in_([a.id for a in allocs]))
                              .values(status="free", allocation_id=None))
    await session.execute(delete(WaitlistEntry).where(WaitlistEntry.passenger_id == p.id))
    await session.execute(delete(Request).where(Request.passenger_id == p.id))
    await session.execute(delete(PodMember).where(PodMember.passenger_id == p.id))
    await session.execute(delete(Notification).where(Notification.passenger_id == p.id))
    await session.execute(delete(PassengerDisruption).where(PassengerDisruption.passenger_id == p.id))
    await session.execute(update(LoginToken).where(LoginToken.passenger_id == p.id, LoginToken.revoked_at.is_(None))
                          .values(revoked_at=clock.utcnow()))
    p.persona_claimed_at = None
    p.token_version += 1
    p.affected_at = None
    transition(p, "BOOKED", force=True)
    # a persona created while a disruption is active starts out affected (F2.5)
    from app.domain.disruption import initial_state_for
    await initial_state_for(session, sc, p)
    await session.flush()
    events.append(ev("persona.released", {"persona_id": p.id}, ops=True))
    if freed_services:
        events += await cascade.run_cascade(session, sc, sorted(freed_services))
    return events
