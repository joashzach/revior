"""Background loops (PRD §14). Each iteration is individually guarded: a failure is logged and the loop continues.
Every iteration is also exposed as a plain coroutine (`*_once`) so tests can drive time deterministically."""
from __future__ import annotations

import asyncio
from datetime import datetime

import structlog
from sqlalchemy import delete, select, text

from app import clock
from app.db import get_sessionmaker
from app.domain import batches as batches_dom
from app.domain import holds as holds_dom
from app.domain import metrics, runner, simulator
from app.domain.snapshot import Snapshot
from app.errors import AppError
from app.models import IdempotencyKey, Scenario, WaitlistEntry
from app.services.scenarios import cfg
from app.ws.events import ev
from app.ws.hub import hub
from app.ws.publish import finish

log = structlog.get_logger()


async def _active_scenarios(session) -> list[Scenario]:
    return list((await session.execute(select(Scenario).where(Scenario.is_active))).scalars())


async def batch_closer_once(now: datetime | None = None) -> int:
    """Close due batches; run allocation when `auto_run_on_batch_close` (F6.3). Returns batches handled."""
    now = now or clock.utcnow()
    handled = 0
    async with get_sessionmaker()() as s:
        due = [(b.id, b.scenario_id) for b in await batches_dom.due_open_batches(s, now)]
        scs = {sc.id: (sc.slug, bool(cfg(sc)["auto_run_on_batch_close"])) for sc in (await s.execute(select(Scenario))).scalars()}
    for batch_id, sc_id in due:
        slug, auto = scs[sc_id]
        try:
            if auto:
                await runner.execute_run(sc_id, "greedy", batch_id=batch_id)
            else:
                async with get_sessionmaker()() as s:
                    sc = await s.get(Scenario, sc_id)
                    b = await s.get(batches_dom.Batch, batch_id)
                    if b is not None and b.status == "open":
                        events = await batches_dom.close_batch(s, sc, b, now)
                        await finish(s, events, slug)
            handled += 1
        except AppError:
            pass  # lost a race with a manual close/run
    return handled


async def hold_expirer_once(now: datetime | None = None) -> None:
    async with get_sessionmaker()() as s:
        for sc in await _active_scenarios(s):
            events = await holds_dom.expire_due(s, sc, now)
            await finish(s, events, sc.slug)


async def simulator_tick_once(now: datetime | None = None) -> None:
    now = now or clock.utcnow()
    async with get_sessionmaker()() as s:
        for sc in await _active_scenarios(s):
            snap = await Snapshot.load(s, sc)
            events = await simulator.transitions(s, sc, snap, now)
            if events:
                await finish(s, events, sc.slug)
            snap = await Snapshot.load(s, sc, polylines=True)
            pos = await simulator.positions(s, sc, snap, now, hub.connected_passenger_ids())
            if pos:
                await hub.publish(pos, sc.slug)
            await s.rollback()


async def kpi_broadcaster_once() -> int:
    """`kpi.updated` to ops at most once per second, only when something changed (dirty flag). Returns the number
    of snapshots published."""
    slugs = hub.take_dirty()
    if not slugs or not hub.ops:
        return 0
    sent = 0
    async with get_sessionmaker()() as s:
        for sc in await _active_scenarios(s):          # ops dashboards only watch the active scenario
            if sc.slug in slugs:
                await hub.publish([ev("kpi.updated", await metrics.kpis(s, sc), ops=True, kpi=False)], sc.slug)
                sent += 1
        await s.rollback()
    return sent


async def cleanup_once() -> None:
    async with get_sessionmaker()() as s:
        await s.execute(text("DELETE FROM idempotency_keys WHERE created_at < now() - interval '24 hours'"))
        await s.execute(text("DELETE FROM waitlist_entries w USING services v WHERE w.service_id = v.id "
                             "AND v.status IN ('running', 'completed', 'cancelled')"))
        await s.commit()


class LoopRunner:
    INTERVALS = {"batch_closer": 1.0, "hold_expirer": 2.0, "simulator_tick": 1.0, "kpi_broadcaster": 1.0, "cleanup": 60.0}

    def __init__(self) -> None:
        self.tasks: list[asyncio.Task] = []
        self.fns = {"batch_closer": batch_closer_once, "hold_expirer": hold_expirer_once,
                    "simulator_tick": simulator_tick_once, "kpi_broadcaster": kpi_broadcaster_once, "cleanup": cleanup_once}

    async def _loop(self, name: str) -> None:
        fn, interval = self.fns[name], self.INTERVALS[name]
        while True:
            try:
                await fn()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - never kill the process
                log.error("loop_iteration_failed", loop=name, exc_info=True)
            await asyncio.sleep(interval)

    def start(self) -> None:
        self.tasks = [asyncio.create_task(self._loop(n), name=f"loop-{n}") for n in self.fns]
        log.info("background_loops_started", loops=list(self.fns))

    async def stop(self) -> None:
        for t in self.tasks:
            t.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
