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
