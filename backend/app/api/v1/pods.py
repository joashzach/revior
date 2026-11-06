"""Pod membership endpoints (contract §5.5): /pods/{id}/join · leave · confirm."""
from fastapi import APIRouter, Depends
from fastapi import Request as HttpRequest
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.me import load_ctx
from app.db import get_session
from app.domain import idempotency as idem
from app.domain import pods as pods_dom
from app.models import Passenger
from app.schemas.contract import PodOut
from app.security import current_passenger
from app.ws.publish import finish

router = APIRouter(tags=["pods"])


@router.post("/pods/{pod_id}/join", response_model=PodOut)
async def join(pod_id: int, request: HttpRequest, p: Passenger = Depends(current_passenger),
               session: AsyncSession = Depends(get_session)) -> dict:
    key = idem.key_of(request)
    replay = await idem.claim_key(session, key, p.id, f"pod-join:{pod_id}")
    if replay is not None:
        await session.rollback()
        return replay
    sc, snap = await load_ctx(session, p)
    pod, events = await pods_dom.join(session, sc, p, pod_id)
    out = await pods_dom.pod_dict(session, snap, pod)
    await idem.store_response(session, key, p.id, out)
    await finish(session, events, sc.slug)
    return out


@router.post("/pods/{pod_id}/leave", status_code=204)
async def leave(pod_id: int, p: Passenger = Depends(current_passenger), session: AsyncSession = Depends(get_session)) -> Response:
    sc, _ = await load_ctx(session, p)
    events = await pods_dom.leave(session, sc, p, pod_id)
    await finish(session, events, sc.slug)
    return Response(status_code=204)


@router.post("/pods/{pod_id}/confirm", response_model=PodOut)
async def confirm(pod_id: int, p: Passenger = Depends(current_passenger), session: AsyncSession = Depends(get_session)) -> dict:
    sc, snap = await load_ctx(session, p)
    pod, events = await pods_dom.confirm(session, sc, p, pod_id)
    out = await pods_dom.pod_dict(session, snap, pod)
    await finish(session, events, sc.slug)
    return out
