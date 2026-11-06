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


# ---- allocation, audit, passenger detail (F8, F17.3-4) -------------------------------------------------------
from app.domain import runner  # noqa: E402
from app.domain.rules import active_rule  # noqa: E402
from app.domain.status import build_status, build_why  # noqa: E402
from app.models import AllocationRun, AuditLog, PriorityRule  # noqa: E402
from app.schemas.contract import OpenBookingIn, RunIn  # noqa: E402


@router.post("/allocation/run")
async def allocation_run(body: RunIn, session: AsyncSession = Depends(get_session)) -> dict:
    sid = (await active_scenario(session)).id
    await session.rollback()
    return await runner.execute_run(sid, body.mode)


@router.get("/allocation/runs/{run_id}")
async def allocation_run_get(run_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    run = await session.get(AllocationRun, run_id)
    if run is None:
        raise AppError("NOT_FOUND", "Unknown run")
    rule = await session.get(PriorityRule, run.rule_version_id) if run.rule_version_id else None
    return {"id": run.id, "mode": run.mode, "started_at": iso(run.started_at), "finished_at": iso(run.finished_at),
            "rule_version": rule.version if rule else 0, "stats": run.stats}


def _page(page: int, page_size: int) -> tuple[int, int]:
    return max(1, page), min(max(1, page_size), 200)


@router.get("/audit")
async def audit_log(passenger_id: int | None = None, entity: str | None = None, page: int = 1, page_size: int = 50,
                    session: AsyncSession = Depends(get_session)) -> dict:
    sc = await active_scenario(session)
    page, page_size = _page(page, page_size)
    q = select(AuditLog).where(AuditLog.scenario_id == sc.id)
    if passenger_id is not None:
        q = q.where(AuditLog.passenger_id == passenger_id)
    if entity:
        q = q.where(AuditLog.entity_type == entity)
    total = (await session.execute(select(func.count()).select_from(q.subquery()))).scalar()
    rows = (await session.execute(q.order_by(AuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {"items": [{"id": a.id, "actor": a.actor, "action": a.action, "entity_type": a.entity_type,
                       "entity_id": a.entity_id, "explanation": a.explanation, "created_at": iso(a.created_at)} for a in rows],
            "page": page, "page_size": page_size, "total": total}


@router.get("/passengers/{passenger_id}")
async def passenger_detail(passenger_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    p = await session.get(Passenger, passenger_id)
    if p is None:
        raise AppError("NOT_FOUND", "Unknown passenger")
    from app.models import Scenario
    sc = await session.get(Scenario, p.scenario_id)
    snap = await Snapshot.load(session, sc)
    return {"passenger": passenger_out(p, snap), "status": await build_status(session, sc, snap, p),
            "why": await build_why(session, sc, snap, p)}


@router.post("/open-booking")
async def open_booking(body: OpenBookingIn, session: AsyncSession = Depends(get_session)) -> dict:
    sc = await active_scenario(session)
    sc.config = {**(sc.config or {}), "open_booking_enabled": body.enabled}
    await finish(session, [], sc.slug)
    return {"enabled": body.enabled}


@router.get("/invariants")
async def invariants(session: AsyncSession = Depends(get_session)) -> dict:
    from app.domain import invariants as inv
    sc = await active_scenario(session)
    sid = sc.id
    await session.rollback()
    return await inv.check(session, sid)


# ---- add capacity (F15) ---------------------------------------------------------------------------------------
from app.domain import capacity as capacity_dom  # noqa: E402
from app.schemas.contract import AddServiceIn  # noqa: E402


@router.post("/services")
async def add_service(body: AddServiceIn, session: AsyncSession = Depends(get_session)) -> dict:
    sc = await active_scenario(session)
    sv, events = await capacity_dom.create_service(
        session, sc, label=body.label, mode=body.mode, stop_node_ids=body.stop_node_ids,
        depart_in_minutes=body.depart_in_minutes, total_seats=body.total_seats, accessible_seats=body.accessible_seats)
    sid, slug, auto = sv.id, sc.slug, bool(cfg_(sc)["auto_run_on_capacity_add"])
    queued, bev = (0, [])
    if auto:
        queued, bev = await capacity_dom.requeue_unplaced(session, sc)
    snap = await Snapshot.load(session, sc)
    out = snap.summary(sid)
    sc_id = sc.id
    await finish(session, events + bev, slug)
    if auto:      # F15.2: immediately re-allocate all UNRESOLVED + WAITLISTED units (existing choices kept, plus auto)
        await runner.execute_run(sc_id, "greedy")
    return out


@router.get("/kpis")
async def kpis_endpoint(session: AsyncSession = Depends(get_session)) -> dict:
    from app.domain import metrics
    return await metrics.kpis(session, await active_scenario(session))


# ---- analytics (F18) + rules editor (F17.1-2) + messages ---------------------------------------------------------
from app.domain import analytics, rules_editor  # noqa: E402
from app.models import Notification  # noqa: E402
from app.schemas.contract import WeightsIn  # noqa: E402


@router.get("/clusters")
async def clusters_endpoint(session: AsyncSession = Depends(get_session)) -> dict:
    sc = await active_scenario(session)
    return {"items": await analytics.clusters(session, sc, await Snapshot.load(session, sc))}


@router.get("/capacity")
async def capacity_endpoint(session: AsyncSession = Depends(get_session)) -> dict:
    sc = await active_scenario(session)
    return {"items": await analytics.capacity_rows(session, sc, await Snapshot.load(session, sc))}


@router.get("/allocations")
async def allocations_endpoint(status: str | None = None, destination: str | None = None, needs: str | None = None,
                               q: str | None = None, page: int = 1, page_size: int = 50,
                               session: AsyncSession = Depends(get_session)) -> dict:
    sc = await active_scenario(session)
    page, page_size = _page(page, page_size)
    return await analytics.allocations_page(session, sc, await Snapshot.load(session, sc), status=status,
                                            destination=destination, needs=needs, q=q, page=page, page_size=page_size)


@router.get("/unresolved")
async def unresolved_endpoint(limit: int = 50, session: AsyncSession = Depends(get_session)) -> dict:
    sc = await active_scenario(session)
    return {"items": await analytics.unresolved_queue(session, sc, await Snapshot.load(session, sc), min(max(limit, 1), 200))}


@router.get("/fairness")
async def fairness_endpoint(session: AsyncSession = Depends(get_session)) -> dict:
    sc = await active_scenario(session)
    return await analytics.fairness(session, sc, await Snapshot.load(session, sc))


@router.get("/map")
async def map_endpoint(session: AsyncSession = Depends(get_session)) -> dict:
    sc = await active_scenario(session)
    edges = await disruption_dom.load_edges(session, sc, polylines=True)
    return await analytics.map_snapshot(session, sc, await Snapshot.load(session, sc, polylines=True), edges, canonical_edges, edge_out)


@router.get("/rules")
async def rules_get(session: AsyncSession = Depends(get_session)) -> dict:
    return await rules_editor.history(session, await active_scenario(session))


@router.post("/rules/preview")
async def rules_preview(body: WeightsIn, session: AsyncSession = Depends(get_session)) -> dict:
    return await rules_editor.preview(session, await active_scenario(session), body.weights)


@router.post("/rules/apply")
async def rules_apply(body: WeightsIn, session: AsyncSession = Depends(get_session)) -> dict:
    sc = await active_scenario(session)
    version, events = await rules_editor.apply(session, sc, body.weights)
    await finish(session, events, sc.slug)
    return {"version": version}


@router.get("/notifications")
async def ops_notifications(page: int = 1, page_size: int = 50, session: AsyncSession = Depends(get_session)) -> dict:
    sc = await active_scenario(session)
    page, page_size = _page(page, page_size)
    total = (await session.execute(select(func.count()).select_from(Notification).where(Notification.scenario_id == sc.id))).scalar()
    rows = (await session.execute(select(Notification, Passenger.name).join(Passenger, Passenger.id == Notification.passenger_id)
                                  .where(Notification.scenario_id == sc.id).order_by(Notification.id.desc())
                                  .offset((page - 1) * page_size).limit(page_size))).all()
    return {"items": [{"passenger_name": name, "channel": n.channel, "template": n.template, "body": n.body or n.title,
                       "created_at": iso(n.created_at)} for n, name in rows], "page": page, "page_size": page_size, "total": total}


# ---- stress test (F23.2) — demo mode only ----------------------------------------------------------------------------
import asyncio as _asyncio  # noqa: E402
import uuid as _uuid  # noqa: E402

from app.domain import stress as stress_dom  # noqa: E402
from app.schemas.contract import StressIn  # noqa: E402
from app.services.scenarios import cfg as _cfg  # noqa: E402
from app.ws.events import Event as _Event  # noqa: E402

_stress_tasks: set = set()


@router.post("/stress/run")
async def stress_run(body: StressIn, session: AsyncSession = Depends(get_session)) -> dict:
    sc = await active_scenario(session)
    if not _cfg(sc)["demo_mode"]:
        raise AppError("FORBIDDEN", "The stress test is only available in demo mode")
    slug = sc.slug
    run_id = f"stress-{_uuid.uuid4().hex[:8]}"

    async def job() -> None:
        import httpx
        from app.main import app as _app

        async def emit(kind: str, data: dict) -> None:
            await hub.publish([_Event(kind, data, ops=True, dirty_kpi=False)], slug)
        world = await stress_dom.build_world(body.requests, body.seats)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app), base_url="http://stress") as c:
                await stress_dom.run_stress(c, world, requests=body.requests, emit=emit)
        except Exception:  # noqa: BLE001
            import structlog
            structlog.get_logger().error("stress_failed", exc_info=True)
            await emit("stress.result", {"total": 0, "confirmed": 0, "capacity": body.seats, "over_allocations": 0, "five_xx": 1, "passed": False})
        finally:
            await stress_dom.cleanup(world["scenario_id"])

    t = _asyncio.create_task(job())
    _stress_tasks.add(t)
    t.add_done_callback(_stress_tasks.discard)
    return {"run_id": run_id}
