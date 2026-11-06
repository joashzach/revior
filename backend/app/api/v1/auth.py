"""Auth endpoints (contract §5.2, §5.3): email+password, personal login QR, demo personas, logout."""
from __future__ import annotations

import hmac
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.config import get_settings
from app.db import get_session
from app.domain import personas as personas_dom
from app.domain.disruption import initial_state_for
from app.domain.snapshot import Snapshot
from app.domain.tickets import assign_ticket_service, destinations_from, hub_ids, new_ticket_id
from app.errors import AppError
from app.models import LoginToken, Passenger
from app.schemas.contract import (AuthOut, DemoClaimIn, DemoClaimOut, LoginIn, OpsLoginIn, QrLoginIn, RegisterIn,
                                  RegisterOut, TokenOut)
from app.security import (auth_limiter, create_ops_token, create_passenger_token, current_passenger,
                          hash_password, hash_password_sync, hash_qr_token, register_limiter, verify_password)
from app.serializers import passenger_out, persona_out, ticket_out
from app.services.scenarios import scenario_by_slug
from app.ws.events import ev
from app.ws.publish import finish

router = APIRouter(prefix="/auth", tags=["auth"])

_DUMMY_HASH = hash_password_sync("revior-dummy")  # equalises timing for unknown emails


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        raise AppError("VALIDATION_ERROR", "Invalid datetime", {"fields": {"needs.connection_deadline_at": "invalid ISO-8601"}})
    return dt if dt.tzinfo else dt.replace(tzinfo=clock.utcnow().tzinfo)


@router.post("/ops-login", response_model=TokenOut, dependencies=[Depends(auth_limiter)])
async def ops_login(body: OpsLoginIn) -> dict:
    if not hmac.compare_digest(body.password.encode(), get_settings().OPS_PASSWORD.encode()):
        raise AppError("INVALID_CREDENTIALS", "Wrong operator password")
    return {"token": create_ops_token()}


@router.post("/register", response_model=RegisterOut, dependencies=[Depends(register_limiter)])
async def register(body: RegisterIn, session: AsyncSession = Depends(get_session)) -> dict:
    sc = await scenario_by_slug(session, body.scenario)
    snap = await Snapshot.load(session, sc)
    email = body.email.lower()
    if (await session.execute(select(Passenger.id).where(
            Passenger.scenario_id == sc.id, Passenger.email == email))).first():
        raise AppError("EMAIL_TAKEN", "That email is already registered", {"fields": {"email": "already registered"}})
    hub = body.hub_node_id or sc.default_hub_node_id
    if hub not in hub_ids(snap):
        raise AppError("VALIDATION_ERROR", "Unknown hub", {"fields": {"hub_node_id": "must be a hub"}})
    if body.destination_node_id not in destinations_from(snap, hub):
        raise AppError("VALIDATION_ERROR", "Destination is not served from this hub",
                       {"fields": {"destination_node_id": "not reachable from hub"}})
    svc = assign_ticket_service(snap, hub, body.destination_node_id, clock.utcnow())
    if svc is None:
        raise AppError("VALIDATION_ERROR", "No service available for that trip",
                       {"fields": {"destination_node_id": "no service"}})
    n = body.needs
    p = Passenger(
        scenario_id=sc.id, name=body.name.strip(), email=email, password_hash=await hash_password(body.password),
        phone=body.phone, ticket_id=await new_ticket_id(session, sc.id), is_seeded=False, is_demo_persona=False,
        party_size=body.party_size, hub_node_id=hub, destination_node_id=body.destination_node_id,
        ticket_service_id=svc.id, wheelchair=n.wheelchair, elderly=n.elderly, with_children=n.with_children,
        medical=n.medical, connection_deadline_at=_parse_dt(n.connection_deadline_at), allow_auto=body.allow_auto,
        state="BOOKED", registered_at=clock.utcnow())
    session.add(p)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise AppError("EMAIL_TAKEN", "That email is already registered", {"fields": {"email": "already registered"}})
    await initial_state_for(session, sc, p)  # F2.5
    out = passenger_out(p, snap)
    await finish(session, [ev("passenger.registered", {"passenger": out, "is_demo_persona": False}, ops=True)], sc.slug)
    return {"token": create_passenger_token(p), "passenger": out, "ticket": ticket_out(p, snap)}


@router.post("/login", response_model=AuthOut, dependencies=[Depends(auth_limiter)])
async def login(body: LoginIn, session: AsyncSession = Depends(get_session)) -> dict:
    sc = await scenario_by_slug(session, body.scenario)
    p = (await session.execute(select(Passenger).where(
        Passenger.scenario_id == sc.id, Passenger.email == body.email.lower()))).scalars().first()
    ok = await verify_password(body.password, p.password_hash if p else _DUMMY_HASH)
    if p is None or not ok:
        raise AppError("INVALID_CREDENTIALS", "Wrong email or password")
    events = []
    if p.is_demo_persona and p.persona_claimed_at is None:  # backup login takes the persona out of the pool
        p.persona_claimed_at = clock.utcnow()
        events.append(ev("persona.claimed", {"persona_id": p.id}, ops=True))
    snap = await Snapshot.load(session, sc)
    out = passenger_out(p, snap)
    await finish(session, events, sc.slug)
    return {"token": create_passenger_token(p), "passenger": out}


@router.post("/qr-login", response_model=AuthOut, dependencies=[Depends(auth_limiter)])
async def qr_login(body: QrLoginIn, session: AsyncSession = Depends(get_session)) -> dict:
    row = (await session.execute(select(LoginToken).where(LoginToken.token_hash == hash_qr_token(body.token)))).scalars().first()
    if row is None or row.revoked_at is not None or row.expires_at <= clock.utcnow():
        raise AppError("QR_TOKEN_INVALID", "QR expired — log in with email")
    p = await session.get(Passenger, row.passenger_id)
    if p is None:
        raise AppError("QR_TOKEN_INVALID", "QR expired — log in with email")
    from app.models import Scenario
    sc = await session.get(Scenario, p.scenario_id)
    snap = await Snapshot.load(session, sc)
    return {"token": create_passenger_token(p), "passenger": passenger_out(p, snap)}


@router.post("/logout", status_code=204)
async def logout(p: Passenger = Depends(current_passenger), session: AsyncSession = Depends(get_session)) -> Response:
    p.token_version += 1  # every outstanding JWT for this passenger now returns 401
    await session.commit()
    from app.ws.hub import hub
    hub.disconnect_passenger(p.id)
    return Response(status_code=204)


@router.post("/demo-claim", response_model=DemoClaimOut, dependencies=[Depends(auth_limiter)])
async def demo_claim(body: DemoClaimIn, session: AsyncSession = Depends(get_session)) -> dict:
    sc = await scenario_by_slug(session, body.scenario)
    p, events = await personas_dom.claim(session, sc, persona_id=body.persona_id, surprise=body.surprise)
    snap = await Snapshot.load(session, sc)
    out = {"token": create_passenger_token(p), "passenger": passenger_out(p, snap), "persona": persona_out(p, snap)}
    events.append(ev("passenger.registered", {"passenger": out["passenger"], "is_demo_persona": True}, ops=True))
    await finish(session, events, sc.slug)
    return out
