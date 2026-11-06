"""Passenger endpoints (role=passenger) — contract §5.5."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.db import get_session
from app.domain import personas as personas_dom
from app.domain.snapshot import Snapshot, iso
from app.domain.state import EDITABLE_STATES
from app.domain.tickets import assign_ticket_service, destinations_from, hub_ids
from app.errors import AppError
from app.models import Disruption, LoginToken, Notification, Passenger, PassengerDisruption, Scenario
from app.schemas.contract import (DemoClaimOut, DemoSwitchIn, LoginQrOut, NotifReadIn, NotificationsOut,
                                  PassengerOut, PatchMeIn, TripOut)
from app.security import create_passenger_token, current_passenger, new_qr_token
from app.serializers import notification_out, passenger_out, persona_out, ticket_out
from app.services.scenarios import cfg
from app.config import get_settings
from app.ws.events import ev
from app.ws.hub import hub
from app.ws.publish import finish

router = APIRouter(prefix="/me", tags=["passenger"])


async def load_ctx(session: AsyncSession, p: Passenger) -> tuple[Scenario, Snapshot]:
    sc = await session.get(Scenario, p.scenario_id)
    return sc, await Snapshot.load(session, sc)


@router.get("", response_model=PassengerOut)
async def me(p: Passenger = Depends(current_passenger), session: AsyncSession = Depends(get_session)) -> dict:
    _, snap = await load_ctx(session, p)
    return passenger_out(p, snap)


@router.patch("", response_model=PassengerOut)
async def patch_me(body: PatchMeIn, p: Passenger = Depends(current_passenger),
                   session: AsyncSession = Depends(get_session)) -> dict:
    if p.state not in EDITABLE_STATES:
        raise AppError("INVALID_STATE", f"Profile can't be changed while {p.state}", {"state": p.state})
    sc, snap = await load_ctx(session, p)
    new_hub = body.hub_node_id or p.hub_node_id
    new_dest = body.destination_node_id or p.destination_node_id
    if body.hub_node_id is not None and body.hub_node_id not in hub_ids(snap):
        raise AppError("VALIDATION_ERROR", "Unknown hub", {"fields": {"hub_node_id": "must be a hub"}})
    if (body.hub_node_id or body.destination_node_id) and new_dest not in destinations_from(snap, new_hub):
        raise AppError("VALIDATION_ERROR", "Destination is not served from this hub",
                       {"fields": {"destination_node_id": "not reachable from hub"}})
    if new_hub != p.hub_node_id or new_dest != p.destination_node_id:
        cur = snap.services.get(p.ticket_service_id) if p.ticket_service_id else None
        if not (cur and snap.serves_in_order(cur.id, new_hub, new_dest)):
            svc = assign_ticket_service(snap, new_hub, new_dest, clock.utcnow())
            if svc is None:
                raise AppError("VALIDATION_ERROR", "No service available for that trip")
            p.ticket_service_id = svc.id
        p.hub_node_id, p.destination_node_id = new_hub, new_dest
    if body.needs is not None:
        n = body.needs
        p.wheelchair, p.elderly, p.with_children, p.medical = n.wheelchair, n.elderly, n.with_children, n.medical
        from app.api.v1.auth import _parse_dt
        p.connection_deadline_at = _parse_dt(n.connection_deadline_at)
    if body.party_size is not None:
        p.party_size = body.party_size
    if body.allow_auto is not None:
        p.allow_auto = body.allow_auto
    await session.commit()
    return passenger_out(p, snap)


def trip_headline(sc: Scenario, svc, snap: Snapshot, p: Passenger | None = None) -> str:
    thr = int(cfg(sc)["delay_threshold_minutes"])
    if svc.status == "cancelled":
        return "Your train is cancelled"
    if svc.delay_minutes and svc.delay_minutes >= thr:
        return f"Your train is delayed by {svc.delay_minutes} min"
    if svc.delay_minutes:
        return f"Running {svc.delay_minutes} min late — no action needed"
    if svc.status == "completed":
        return "Your train has completed its run"
    stop = snap.stop_at(svc.id, p.hub_node_id) if p is not None else None
    if stop is not None:
        mins = int((snap.effective(stop.depart_at, svc.id) - clock.utcnow()).total_seconds() // 60)
        hub = snap.nodes[p.hub_node_id].name
        if mins >= 0:
            return f"On time — departs {hub} in {mins} min. We'll alert you if anything changes."
        return "Your train has departed"
    return "On time — we'll alert you if anything changes."


@router.get("/trip", response_model=TripOut)
async def trip(p: Passenger = Depends(current_passenger), session: AsyncSession = Depends(get_session)) -> dict:
    sc, snap = await load_ctx(session, p)
    ticket = ticket_out(p, snap)
    if ticket is None:
        raise AppError("NOT_FOUND", "No ticket for this passenger")
    svc = snap.services[p.ticket_service_id]
    d = (await session.execute(
        select(Disruption).where(Disruption.scenario_id == sc.id, Disruption.service_id == svc.id,
                                 Disruption.resolved_at.is_(None)).order_by(Disruption.id.desc()))).scalars().first()
    if d is None:  # closure / earlier disruption that hit this passenger
        d = (await session.execute(
            select(Disruption).join(PassengerDisruption, PassengerDisruption.disruption_id == Disruption.id)
            .where(PassengerDisruption.passenger_id == p.id, Disruption.resolved_at.is_(None))
            .order_by(Disruption.id.desc()))).scalars().first()
    headline = trip_headline(sc, svc, snap, p)
    if d is not None and d.reason and svc.status == "cancelled":
        headline = f"{headline} — {d.reason}"
    return {"ticket": ticket,
            "disruption": {"id": d.id, "type": d.type, "reason": d.reason, "created_at": iso(d.created_at)} if d else None,
            "headline": headline}


# ---- login QR + notifications -----------------------------------------------------------------
async def make_login_qr(session: AsyncSession, p: Passenger) -> dict:
    now = clock.utcnow()
    await session.execute(update(LoginToken).where(LoginToken.passenger_id == p.id, LoginToken.revoked_at.is_(None))
                          .values(revoked_at=now))
    raw, hashed = new_qr_token()
    exp = now + timedelta(hours=24)
    session.add(LoginToken(passenger_id=p.id, token_hash=hashed, expires_at=exp))
    await session.commit()
    return {"url": f"{get_settings().FRONTEND_BASE_URL.rstrip('/')}/qr-login?t={raw}", "expires_at": iso(exp)}


@router.get("/login-qr", response_model=LoginQrOut)
async def login_qr(p: Passenger = Depends(current_passenger), session: AsyncSession = Depends(get_session)) -> dict:
    return await make_login_qr(session, p)


@router.get("/notifications", response_model=NotificationsOut)
async def notifications(p: Passenger = Depends(current_passenger), session: AsyncSession = Depends(get_session)) -> dict:
    rows = (await session.execute(select(Notification).where(Notification.passenger_id == p.id)
                                  .order_by(Notification.id.desc()).limit(50))).scalars().all()
    return {"items": [notification_out(n) for n in rows]}


@router.post("/notifications/read", status_code=204)
async def notifications_read(body: NotifReadIn, p: Passenger = Depends(current_passenger),
                             session: AsyncSession = Depends(get_session)) -> Response:
    if body.ids:
        await session.execute(update(Notification).where(Notification.passenger_id == p.id,
                                                         Notification.id.in_(body.ids)).values(read=True))
    await session.commit()
    return Response(status_code=204)


# ---- demo persona switch ----------------------------------------------------------------------------
@router.post("/demo-switch", response_model=DemoClaimOut)
async def demo_switch(body: DemoSwitchIn, p: Passenger = Depends(current_passenger),
                      session: AsyncSession = Depends(get_session)) -> dict:
    if not p.is_demo_persona:
        raise AppError("FORBIDDEN", "Only demo personas can switch passenger")
    sc, snap = await load_ctx(session, p)
    if body.mode == "pick":
        if body.persona_id is None:
            raise AppError("VALIDATION_ERROR", "persona_id required", {"fields": {"persona_id": "required"}})
        new, events = await personas_dom.claim(session, sc, persona_id=body.persona_id, surprise=False)
    else:
        nxt = await personas_dom.next_free(session, sc, p.id)
        new, events = await personas_dom.claim(session, sc, persona_id=nxt.id if nxt else None, surprise=nxt is None)
    old_id = p.id
    if new.id != p.id:
        events += await personas_dom.release(session, sc, p)
    out = {"token": create_passenger_token(new), "passenger": passenger_out(new, snap), "persona": persona_out(new, snap)}
    await finish(session, events, sc.slug)
    hub.disconnect_passenger(old_id)
    return out


# ---- options + request (F4.2, F6.1) --------------------------------------------------------------------
from app.domain import batches as batches_dom  # noqa: E402
from app.models import Batch as _Batch  # noqa: E402
from app.domain.options import compute_options, option_dict, requestable  # noqa: E402
from app.domain.snapshot import seat_counts  # noqa: E402
from app.domain.state import REQUESTABLE  # noqa: E402
from app.models import Allocation, Request  # noqa: E402
from app.schemas.contract import OptionsOut, RequestIn, RequestOut  # noqa: E402
from app.serializers import batch_out  # noqa: E402


async def _options_for(session: AsyncSession, sc: Scenario, snap: Snapshot, p: Passenger):
    counts = await seat_counts(session, [s for s, v in snap.services.items() if v.has_seat_inventory])
    return compute_options(snap, p, clock.utcnow(), counts)


@router.get("/options", response_model=OptionsOut)
async def options(p: Passenger = Depends(current_passenger), session: AsyncSession = Depends(get_session)) -> dict:
    sc, snap = await load_ctx(session, p)
    opts = await _options_for(session, sc, snap, p)
    b = await batches_dom.open_batch_row(session, sc)
    return {"items": [option_dict(snap, o) for o in opts], "batch": batch_out(b) if b else None}


@router.post("/request", response_model=RequestOut)
async def submit_request(body: RequestIn, p: Passenger = Depends(current_passenger),
                         session: AsyncSession = Depends(get_session)) -> dict:
    sc, snap = await load_ctx(session, p)
    if p.state not in REQUESTABLE:
        raise AppError("INVALID_STATE", f"You can't send a request while {p.state}", {"state": p.state})
    if body.choice1_service_id is None and body.choice2_service_id is not None:
        body.choice1_service_id, body.choice2_service_id = body.choice2_service_id, None
    if body.choice1_service_id is None and not body.any_fastest:
        raise AppError("VALIDATION_ERROR", "Pick at least one option or choose 'Any, fastest'",
                       {"fields": {"choice1_service_id": "required unless any_fastest"}})
    if body.choice1_service_id is not None and body.choice1_service_id == body.choice2_service_id:
        raise AppError("VALIDATION_ERROR", "Choose two different options", {"fields": {"choice2_service_id": "duplicate"}})
    valid = requestable(await _options_for(session, sc, snap, p))
    for field_, sid in (("choice1_service_id", body.choice1_service_id), ("choice2_service_id", body.choice2_service_id)):
        if sid is not None and sid not in valid:
            raise AppError("VALIDATION_ERROR", "That option is not available for you",
                           {"fields": {field_: "not one of your feasible options"}})
    # a passenger whose previous request sits in an already-closed batch cannot edit it any more
    closed = (await session.execute(select(Request).join(_Batch, _Batch.id == Request.batch_id).where(
        Request.passenger_id == p.id, Request.status == "queued", _Batch.status != "open"))).scalars().first()
    if closed is not None:
        raise AppError("BATCH_CLOSED", "Window closed — you're in the next batch", {"batch_id": closed.batch_id})
    now = clock.utcnow()
    batch, events = await batches_dom.get_or_open_batch(session, sc, "late_request", now, audience=[p.id])
    req = (await session.execute(select(Request).where(Request.batch_id == batch.id, Request.passenger_id == p.id))).scalars().first()
    if req is None:
        req = Request(scenario_id=sc.id, batch_id=batch.id, passenger_id=p.id)
        session.add(req)
    req.choice1_service_id, req.choice2_service_id = body.choice1_service_id, body.choice2_service_id
    req.any_fastest, req.status, req.created_at = body.any_fastest, "queued", now
    from app.domain.state import transition
    transition(p, "REQUESTED")
    await session.flush()
    out = {"id": req.id, "batch": batch_out(batch), "choice1_service_id": req.choice1_service_id,
           "choice2_service_id": req.choice2_service_id, "any_fastest": req.any_fastest}
    await finish(session, events, sc.slug)
    return out


# ---- status + why (F10.3, F17.3) ------------------------------------------------------------------------
from app.domain.status import build_status, build_why  # noqa: E402
from app.schemas.contract import MyStatus, Why  # noqa: E402


@router.get("/status", response_model=MyStatus)
async def my_status(p: Passenger = Depends(current_passenger), session: AsyncSession = Depends(get_session)) -> dict:
    sc, snap = await load_ctx(session, p)
    return await build_status(session, sc, snap, p)


@router.get("/why", response_model=Why)
async def my_why(p: Passenger = Depends(current_passenger), session: AsyncSession = Depends(get_session)) -> dict:
    sc, snap = await load_ctx(session, p)
    return await build_why(session, sc, snap, p)
