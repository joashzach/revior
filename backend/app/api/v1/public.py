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


# ---- hubs, destinations, demo personas -----------------------------------------------------------
from app.domain import personas as personas_dom  # noqa: E402
from app.domain.tickets import destinations_from, haversine_km, hub_ids  # noqa: E402
from app.schemas.contract import HubsNearbyIn, HubsNearbyOut, NodeList, PersonaList  # noqa: E402
from app.serializers import persona_out  # noqa: E402
from app.services.scenarios import scenario_by_slug  # noqa: E402
from app.errors import AppError  # noqa: E402


@router.post("/hubs/nearby", response_model=HubsNearbyOut)
async def hubs_nearby(body: HubsNearbyIn, session: AsyncSession = Depends(get_session)) -> dict:
    sc = await scenario_by_slug(session, body.scenario)
    snap = await Snapshot.load(session, sc)
    default = snap.nodes[sc.default_hub_node_id]
    radius = float(cfg(sc)["hub_radius_km"])
    if body.lat is not None and body.lng is not None:
        near = sorted(((haversine_km(body.lat, body.lng, snap.nodes[i].lat, snap.nodes[i].lng), i)
                       for i in hub_ids(snap)), key=lambda x: (x[0], x[1]))
        near = [(d, i) for d, i in near if d <= radius]
        if near:
            ids = [i for _, i in near]
            selected = default.id if default.id in ids else ids[0]
            return {"hubs": [{"hub": snap.node_ref(i), "distance_km": round(d, 2), "is_default": i == default.id}
                             for d, i in near], "selected_hub_id": selected, "reason": "nearest"}
    return {"hubs": [{"hub": snap.node_ref(default.id), "distance_km": None, "is_default": True}],
            "selected_hub_id": default.id, "reason": "default"}


@router.get("/destinations", response_model=NodeList)
async def destinations(scenario: str | None = None, hub: str | None = None, q: str | None = None,
                       session: AsyncSession = Depends(get_session)) -> dict:
    sc = await scenario_by_slug(session, scenario)
    snap = await Snapshot.load(session, sc)
    hub_id = sc.default_hub_node_id
    if hub:
        node = snap.nodes.get(int(hub)) if hub.isdigit() else snap.code_to_node(hub.upper())
        if node is None or not node.is_hub:
            raise AppError("NOT_FOUND", "Unknown hub")
        hub_id = node.id
    return {"items": [snap.node_ref(i) for i in destinations_from(snap, hub_id, q)]}


@router.get("/demo/personas", response_model=PersonaList)
async def demo_personas(scenario: str | None = None, session: AsyncSession = Depends(get_session)) -> dict:
    sc = await scenario_by_slug(session, scenario)
    snap = await Snapshot.load(session, sc)
    return {"items": [persona_out(p, snap) for p in await personas_dom.list_personas(session, sc)]}
