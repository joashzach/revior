"""Operator endpoints (role=operator). Grown stage by stage."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.db import get_session
from app.errors import AppError
from app.models import Scenario
from app.schemas.contract import ConfigPatch, ScenarioConfig
from app.security import require_ops
from app.seed.loader import reset_scenario
from app.services.scenarios import cfg as cfg_, public_config, scenario_by_slug
from app.ws.events import ev
from app.ws.hub import hub
from app.ws.publish import finish

router = APIRouter(prefix="/ops", tags=["ops"], dependencies=[Depends(require_ops)])


# ---- scenarios (F1) ---------------------------------------------------------------------------
@router.get("/scenarios")
async def list_scenarios(session: AsyncSession = Depends(get_session)) -> dict:
    rows = (await session.execute(select(Scenario).order_by(Scenario.id))).scalars().all()
    return {"items": [{"slug": s.slug, "name": s.name, "is_active": s.is_active} for s in rows]}


@router.post("/scenarios/{slug}/activate")
async def activate_scenario(slug: str, session: AsyncSession = Depends(get_session)) -> dict:
    sc = await scenario_by_slug(session, slug)
    await session.execute(update(Scenario).values(is_active=False))
    sc.is_active = True
    await finish(session, [], sc.slug)
    return {"slug": sc.slug}


@router.post("/scenarios/{slug}/reset")
async def reset(slug: str, session: AsyncSession = Depends(get_session)) -> dict:
    sc = await scenario_by_slug(session, slug)
    # sockets of the wiped passengers are closed (their tokens no longer resolve)
    connected = hub.connected_passenger_ids()
    res = await reset_scenario(session, sc.slug)
    await finish(session, [], sc.slug)          # marks the KPI snapshot dirty -> the broadcaster sends a real kpi.updated
    for pid in connected:
        hub.disconnect_passenger(pid)
    return {"duration_ms": res["duration_ms"], "counts": res["counts"]}


@router.get("/scenarios/{slug}/config", response_model=ScenarioConfig)
async def get_config(slug: str, session: AsyncSession = Depends(get_session)) -> dict:
    return public_config(await scenario_by_slug(session, slug))


@router.patch("/scenarios/{slug}/config", response_model=ScenarioConfig)
async def patch_config(slug: str, body: ConfigPatch, session: AsyncSession = Depends(get_session)) -> dict:
    sc = await scenario_by_slug(session, slug)
    patch = body.model_dump(exclude_none=True)
    sc.config = {**(sc.config or {}), **patch}
    await finish(session, [], sc.slug)
    return public_config(sc)


# ---- demo personas + login QR (F24) --------------------------------------------------------------------
from fastapi.responses import Response  # noqa: E402

from app.api.v1.me import make_login_qr  # noqa: E402
from app.domain import personas as personas_dom  # noqa: E402
from app.domain.snapshot import Snapshot, iso  # noqa: E402
from app.models import Passenger  # noqa: E402
from app.serializers import passenger_out, persona_out  # noqa: E402
from app.services.scenarios import active_scenario  # noqa: E402


@router.get("/passengers/{passenger_id}/login-qr")
async def passenger_login_qr(passenger_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    p = await session.get(Passenger, passenger_id)
    if p is None:
        raise AppError("NOT_FOUND", "Unknown passenger")
    return await make_login_qr(session, p)


@router.get("/demo/personas")
async def ops_demo_personas(session: AsyncSession = Depends(get_session)) -> dict:
    sc = await active_scenario(session)
    snap = await Snapshot.load(session, sc)
    return {"items": [{**persona_out(p, snap), "claimed_at": iso(p.persona_claimed_at), "state": p.state}
                      for p in await personas_dom.list_personas(session, sc)]}


@router.post("/demo/personas/release-all", status_code=204)
async def release_all_personas(session: AsyncSession = Depends(get_session)) -> Response:
    sc = await active_scenario(session)
    events, ids = [], []
    for p in await personas_dom.list_personas(session, sc):
        if p.persona_claimed_at is not None:
            events += await personas_dom.release(session, sc, p)
            ids.append(p.id)
    await finish(session, events, sc.slug)
    for pid in ids:
        hub.disconnect_passenger(pid)
    return Response(status_code=204)


@router.post("/demo/personas/{persona_id}/release", status_code=204)
async def release_persona(persona_id: int, session: AsyncSession = Depends(get_session)) -> Response:
    sc = await active_scenario(session)
    p = await session.get(Passenger, persona_id)
    if p is None or not p.is_demo_persona or p.scenario_id != sc.id:
        raise AppError("NOT_FOUND", "Unknown persona")
    events = await personas_dom.release(session, sc, p)
    await finish(session, events, sc.slug)
    hub.disconnect_passenger(p.id)
    return Response(status_code=204)


# ---- network, services, disruptions, batches (F5, F6, F18.7) ---------------------------------------------
from sqlalchemy import func  # noqa: E402

from app.domain import batches as batches_dom  # noqa: E402
from app.domain import disruption as disruption_dom  # noqa: E402
from app.domain.snapshot import linestring, seat_counts  # noqa: E402
from app.models import Disruption, Edge, WaitlistEntry  # noqa: E402
from app.schemas.contract import DisruptionIn  # noqa: E402
from app.serializers import batch_out  # noqa: E402


def canonical_edges(edges: list[Edge]) -> list[Edge]:
    """One row per physical segment (the lower id of each twin pair)."""
    seen: dict[tuple, Edge] = {}
    for e in sorted(edges, key=lambda x: x.id):
        seen.setdefault((e.mode, frozenset((e.from_node_id, e.to_node_id))), e)
    return list(seen.values())


def edge_out(e: Edge) -> dict:
    return {"id": e.id, "from_node_id": e.from_node_id, "to_node_id": e.to_node_id, "mode": e.mode,
            "road_name": e.road_name, "is_closed": e.is_closed, "polyline": linestring(e.polyline)}


@router.get("/network")
async def network(session: AsyncSession = Depends(get_session)) -> dict:
    sc = await active_scenario(session)
    snap = await Snapshot.load(session, sc)
    edges = await disruption_dom.load_edges(session, sc, polylines=True)
    return {"nodes": [snap.node_ref(i) for i in sorted(snap.nodes)],
            "edges": [edge_out(e) for e in canonical_edges(edges)]}


@router.get("/services")
async def list_services(status: str | None = None, mode: str | None = None,
                        session: AsyncSession = Depends(get_session)) -> dict:
    sc = await active_scenario(session)
    snap = await Snapshot.load(session, sc, polylines=True)
    counts = await seat_counts(session, list(snap.services))
    wl = dict((await session.execute(select(WaitlistEntry.service_id, func.count()).where(
        WaitlistEntry.scenario_id == sc.id, WaitlistEntry.status == "active").group_by(WaitlistEntry.service_id))).all())
    items = []
    for sid, sv in snap.services.items():
        if (status and sv.status != status) or (mode and sv.mode != mode):
            continue
        c = counts[sid]
        items.append({**snap.summary(sid), "total_seats": sv.total_seats, "held": c["held"], "confirmed": c["confirmed"],
                      "free": c["free"], "accessible_free": c["accessible_free"], "waitlist_len": wl.get(sid, 0),
                      "polyline": linestring(sv.polyline)})
    return {"items": items}


@router.get("/disruptions/preview")
async def disruption_preview(type: str, service_id: int | None = None, edge_id: int | None = None,
                             delay_minutes: int | None = None, session: AsyncSession = Depends(get_session)) -> dict:
    if type not in ("cancellation", "delay", "closure"):
        raise AppError("VALIDATION_ERROR", "Unknown disruption type", {"fields": {"type": "cancellation|delay|closure"}})
    sc = await active_scenario(session)
    return await disruption_dom.preview(session, sc, type, service_id, edge_id, delay_minutes)


@router.post("/disruptions")
async def create_disruption(body: DisruptionIn, session: AsyncSession = Depends(get_session)) -> dict:
    sc = await active_scenario(session)
    d, affected, batch, events = await disruption_dom.create(
        session, sc, type_=body.type, service_id=body.service_id, edge_id=body.edge_id,
        delay_minutes=body.delay_minutes, reason=body.reason)
    out = {"disruption": disruption_dom.disruption_dict(d), "affected_count": affected,
           "batch": batch_out(batch) if batch else None}
    await finish(session, events, sc.slug)
    return out


@router.get("/disruptions")
async def list_disruptions(session: AsyncSession = Depends(get_session)) -> dict:
    sc = await active_scenario(session)
    return {"items": await disruption_dom.list_disruptions(session, sc)}


@router.post("/disruptions/{disruption_id}/resolve")
async def resolve_disruption(disruption_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    sc = await active_scenario(session)
    d = await session.get(Disruption, disruption_id)
    if d is None or d.scenario_id != sc.id:
        raise AppError("NOT_FOUND", "Unknown disruption")
    events = await disruption_dom.resolve(session, sc, d)
    out = {"id": d.id, "resolved_at": d.resolved_at.isoformat()}
    await finish(session, events, sc.slug)
    return out


@router.get("/batches/current")
async def batches_current(session: AsyncSession = Depends(get_session)) -> dict:
    sc = await active_scenario(session)
    b = await batches_dom.current_batch(session, sc)
    return {"batch": batch_out(b) if b else None, "request_count": await batches_dom.request_count(session, b) if b else 0}


@router.post("/batches/current/close")
async def batches_close(session: AsyncSession = Depends(get_session)) -> dict:
    sc = await active_scenario(session)
    b = await batches_dom.open_batch_row(session, sc)
    if b is None:
        raise AppError("INVALID_STATE", "There is no open batch")
    events = await batches_dom.close_batch(session, sc, b, clock.utcnow())
    out = batch_out(b)
    await finish(session, events, sc.slug)
    return out
