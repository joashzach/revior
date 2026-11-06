from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.config import get_settings
from app.db import check_db, get_session
from app.domain.snapshot import Snapshot, iso
from app.schemas.contract import ActiveScenarioOut, HealthOut
from app.services.scenarios import active_scenario, cfg, join_url

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthOut)
async def health() -> dict:
    ok = await check_db()
    return {"status": "ok" if ok else "degraded", "db": "ok" if ok else "down",
            "version": get_settings().APP_VERSION, "server_time": iso(clock.utcnow())}


@router.get("/scenarios/active", response_model=ActiveScenarioOut)
async def scenario_active(session: AsyncSession = Depends(get_session)) -> dict:
    sc = await active_scenario(session)
    snap = await Snapshot.load(session, sc)
    return {"slug": sc.slug, "name": sc.name, "default_hub": snap.node_ref(sc.default_hub_node_id),
            "join_url": join_url(sc), "demo_mode": bool(cfg(sc)["demo_mode"])}
