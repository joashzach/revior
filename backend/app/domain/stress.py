"""Stress test (PRD F23): N concurrent HTTP requests against a service with a handful of seats.

Traffic = open-booking claims by many passengers + accept/decline/duplicate-claim traffic from the winners,
all fired at once through the real API (auth, idempotency, row locks). While it runs, a monitor polls the
invariant checker (REPEATABLE READ) so over-allocation at *any* instant would be caught, not just at the end.
The test world is an isolated throw-away scenario (`stress-<id>`), deleted afterwards — the demo scenario is untouched.
"""
from __future__ import annotations

import asyncio
import random
import time
import uuid
from datetime import timedelta
from typing import Any, Awaitable, Callable

import httpx
from sqlalchemy import delete, func, select

from app import clock
from app.dbutil import bulk
from app.db import get_sessionmaker
from app.domain import invariants
from app.models import (Node, Passenger, PriorityRule, Scenario, Seat, Service, ServiceStop)
from app.security import create_passenger_token
from app.services.scenarios import default_config

Emit = Callable[[str, dict[str, Any]], Awaitable[None]]


async def build_world(requests: int, seats: int) -> dict[str, Any]:
    now = clock.utcnow()
    n_pax = max(requests // 2, seats * 3)
    async with get_sessionmaker()() as s:
        sc = Scenario(slug=f"stress-{uuid.uuid4().hex[:8]}", name="stress test", seed_key="potheri", is_active=False, t0=now,
                      config={**default_config(), "open_booking_enabled": True, "hold_seconds": 600}, rng_seed=1)
        s.add(sc)
        await s.flush()
        hub = Node(scenario_id=sc.id, code="HUB", name="Stress Hub", lat=1.0, lng=1.0, kind="rail_station", is_hub=True, is_default_hub=True)
        dst = Node(scenario_id=sc.id, code="DST", name="Stress Dest", lat=1.1, lng=1.1, kind="rail_station")
        s.add_all([hub, dst])
        await s.flush()
        sc.default_hub_node_id = hub.id
        sv = Service(scenario_id=sc.id, code="STRESS-1", label="Stress bus", mode="bus", status="scheduled", has_seat_inventory=True,
                     total_seats=seats, accessible_seats=0, depart_at=now + timedelta(hours=2), arrive_at=now + timedelta(hours=3),
                     created_by="seed")
        s.add(sv)
        await s.flush()
        await bulk(s, ServiceStop, [dict(service_id=sv.id, seq=0, node_id=hub.id, arrive_at=sv.depart_at, depart_at=sv.depart_at, is_skipped=False, is_via=False),
                                    dict(service_id=sv.id, seq=1, node_id=dst.id, arrive_at=sv.arrive_at, depart_at=sv.arrive_at, is_skipped=False, is_via=False)])
        await bulk(s, Seat, [dict(service_id=sv.id, seat_no=f"{i:03d}", is_accessible=False, status="free") for i in range(1, seats + 1)])
        s.add(PriorityRule(scenario_id=sc.id, version=1, is_active=True,
                           weights={"medical": 30, "wheelchair": 30, "elderly": 15, "with_children": 10, "deadline_urgency": 20, "wait_time": 20}))
        await s.flush()
        rows = [dict(scenario_id=sc.id, name=f"Stress {i}", email=f"stress{i}@stress.test", ticket_id=f"ST-{sc.id}-{i}", is_seeded=False,
                     is_demo_persona=False, token_version=0, party_size=1, hub_node_id=hub.id, destination_node_id=dst.id,
                     wheelchair=False, elderly=False, with_children=False, medical=False, allow_auto=True, state="AFFECTED",
                     affected_at=now - timedelta(minutes=i % 60), registered_at=now - timedelta(days=1)) for i in range(n_pax)]
        await bulk(s, Passenger, rows)
        await s.flush()
        pax = (await s.execute(select(Passenger).where(Passenger.scenario_id == sc.id).order_by(Passenger.id))).scalars().all()
        tokens = [create_passenger_token(p) for p in pax]
        world = {"scenario_id": sc.id, "service_id": sv.id, "tokens": tokens, "seats": seats}
        await s.commit()
    return world


async def cleanup(scenario_id: int) -> None:
    async with get_sessionmaker()() as s:
        await s.execute(delete(Scenario).where(Scenario.id == scenario_id))
        await s.commit()


async def run_stress(http: httpx.AsyncClient, world: dict[str, Any], *, requests: int, seed: int = 7,
                     emit: Emit | None = None) -> dict[str, Any]:
    rng = random.Random(seed)
    tokens, sid, seats, scenario_id = world["tokens"], world["service_id"], world["seats"], world["scenario_id"]
    n_pax = len(tokens)
    ops: list[tuple[int, str]] = [(i % n_pax, "claim") for i in range(min(requests, n_pax))]
    while len(ops) < requests:                      # follow-up traffic: more claims, accepts, declines, duplicate claims
        ops.append((rng.randrange(n_pax), rng.choice(["accept", "decline", "claim", "accept", "decline"])))
    rng.shuffle(ops)
    stats = {"sent": 0, "ok": 0, "conflicts": 0, "errors": 0, "five_xx": 0, "by_status": {}}
    lock = asyncio.Lock()
    inflight = asyncio.Semaphore(120)          # all requests are issued at once; at most 120 are in flight (pool is 20)
    done = asyncio.Event()
    monitor = {"max_over": 0, "max_multi": 0, "max_neg": 0, "samples": 0}

    async def call(idx: int, op: str) -> None:
        h = {"Authorization": f"Bearer {tokens[idx]}", "Idempotency-Key": str(uuid.uuid4())}
        url, body = {"claim": ("/api/v1/me/claim", {"service_id": sid}), "accept": ("/api/v1/me/allocation/accept", None),
                     "decline": ("/api/v1/me/allocation/decline", None)}[op]
        code = 0
        await inflight.acquire()
        for attempt in range(4):                    # transient TCP resets (Windows/Docker): same key => safe to retry
            try:
                r = await http.post(url, json=body, headers=h, timeout=120)
                code = r.status_code
                break
            except (httpx.TransportError, OSError):
                await asyncio.sleep(0.2 * (attempt + 1))
            except Exception:  # noqa: BLE001 - an exception escaping the app is, by definition, a 500
                code = 500
                break
        inflight.release()
        async with lock:
            stats["sent"] += 1
            stats["by_status"][code] = stats["by_status"].get(code, 0) + 1
            if code == 200:
                stats["ok"] += 1
            elif code == 409:
                stats["conflicts"] += 1
            elif code >= 500 or code == 0:
                stats["five_xx"] += 1
                stats["errors"] += 1
            else:
                stats["errors"] += 1
            if emit and stats["sent"] % 100 == 0:
                await emit("stress.progress", {k: stats[k] for k in ("sent", "ok", "conflicts", "errors")})

    async def watch() -> None:
        while not done.is_set():
            async with get_sessionmaker()() as s:
                inv = await invariants.check(s, scenario_id)
                await s.rollback()
            monitor["max_over"] = max(monitor["max_over"], inv["over_allocated_services"])
            monitor["max_multi"] = max(monitor["max_multi"], inv["multi_primary_passengers"])
            monitor["max_neg"] = max(monitor["max_neg"], inv["negative_free_seats"])
            monitor["samples"] += 1
            await asyncio.sleep(0.15)

    t0 = time.perf_counter()
    watcher = asyncio.create_task(watch())
    await asyncio.gather(*[call(i, op) for i, op in ops])
    done.set()
    await watcher
    async with get_sessionmaker()() as s:
        inv = await invariants.check(s, scenario_id, deep=True)
        used = (await s.execute(select(func.count()).select_from(Seat).where(Seat.service_id == sid, Seat.status != "free"))).scalar()
        await s.rollback()
    over = max(monitor["max_over"], inv["over_allocated_services"]) + max(0, used - seats)
    result = {"total": stats["sent"], "confirmed": int(used), "capacity": seats, "over_allocations": int(over),
              "five_xx": stats["five_xx"], "multi_primary": max(monitor["max_multi"], inv["multi_primary_passengers"]),
              "invariants_ok": bool(inv["ok"]), "monitor_samples": monitor["samples"], "by_status": stats["by_status"],
              "duration_s": round(time.perf_counter() - t0, 2)}
    result["passed"] = bool(over == 0 and stats["five_xx"] == 0 and inv["ok"] and used <= seats and result["multi_primary"] == 0)
    if emit:
        await emit("stress.result", {k: result[k] for k in ("total", "confirmed", "capacity", "over_allocations", "five_xx", "passed")})
    return result
