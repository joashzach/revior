"""Orchestrates an allocation run: close the open batch, announce, run, commit, publish (PRD F6.3, F8)."""
from __future__ import annotations

from sqlalchemy import select

from app import clock
from app.db import get_sessionmaker
from app.domain import allocation as alloc_dom
from app.domain import batches as batches_dom
from app.errors import AppError
from app.models import Batch, Scenario
from app.ws.events import ev
from app.ws.hub import hub
from app.ws.publish import finish


async def execute_run(scenario_id: int, mode: str = "greedy", *, batch_id: int | None = None) -> dict:
    """Close the open batch (if any), run the engine over it (+ waitlisted units), commit, publish.
    Used by `POST /ops/allocation/run`, the batch_closer loop and capacity-add."""
    if mode == "ortools":
        from app.config import get_settings
        if not get_settings().ENABLE_ORTOOLS:
            raise AppError("VALIDATION_ERROR", "OR-Tools mode is disabled (ENABLE_ORTOOLS=false)",
                           {"fields": {"mode": "ortools disabled"}})
        mode = "greedy"  # optional stretch (F8.9) not implemented: greedy remains the production mode
    sf = get_sessionmaker()
    async with sf() as s:
        sc = await s.get(Scenario, scenario_id)
        pre_events = []
        batch = await s.get(Batch, batch_id) if batch_id else await batches_dom.open_batch_row(s, sc)
        if batch is not None and batch.status == "open":
            pre_events = await batches_dom.close_batch(s, sc, batch, clock.utcnow())
        elif batch is None:
            batch = (await s.execute(select(Batch).where(Batch.scenario_id == sc.id, Batch.status == "closed")
                                     .order_by(Batch.id.desc()))).scalars().first()
        await finish(s, pre_events, sc.slug)
        run_id = await alloc_dom.start_run(sf, sc.id, batch.id if batch else None, mode)
        await hub.publish([ev("allocation.run_started", {"run_id": run_id}, ops=True)], sc.slug)
        # re-read inside the run transaction (the commit above expired nothing, but be explicit)
        batch = await s.get(Batch, batch.id) if batch is not None else None
        result = await alloc_dom.run_allocation(s, sc, batch=batch, run_id=run_id, mode=mode)
        await finish(s, result.events, sc.slug)
        return {"run_id": run_id, "stats": result.stats}
