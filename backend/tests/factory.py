"""Tiny hand-built scenarios for engine tests (nothing Potheri-specific: proves location-agnostic logic)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dbutil import bulk
from app.models import (Allocation, Batch, Node, Passenger, PriorityRule, Request, Scenario, Seat, Service,
                        ServiceStop)
from app.services.scenarios import default_config

NOW = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)


@dataclass
class Ctx:
    sc: Scenario
    hub: Node
    dest: Node
    dest2: Node
    services: dict[str, Service]
    batch: Batch
    now: datetime = NOW
    pax: dict[str, Passenger] = field(default_factory=dict)
    n: int = 0


async def build(session: AsyncSession, seats: dict[str, tuple[int, int]] | None = None, now: datetime = NOW,
                weights: dict | None = None) -> Ctx:
    """`seats`: {service_code: (total_seats, accessible_seats)} — every service runs HUB -> DEST -> DEST2."""
    seats = seats or {"S1": (3, 1), "S2": (3, 1)}
    sc = Scenario(slug=f"t-{uuid.uuid4().hex[:8]}", name="test", seed_key="potheri", is_active=False, t0=now,
                  config=default_config(), rng_seed=1)
    session.add(sc)
    await session.flush()
    hub = Node(scenario_id=sc.id, code="HUB", name="Hub", lat=1.0, lng=1.0, kind="rail_station", is_hub=True, is_default_hub=True)
    d1 = Node(scenario_id=sc.id, code="DST", name="Dest", lat=1.1, lng=1.1, kind="rail_station")
    d2 = Node(scenario_id=sc.id, code="DS2", name="Dest2", lat=1.2, lng=1.2, kind="rail_station")
    session.add_all([hub, d1, d2])
    await session.flush()
    sc.default_hub_node_id = hub.id
    svcs: dict[str, Service] = {}
    for i, (code, (total, acc)) in enumerate(seats.items()):
        sv = Service(scenario_id=sc.id, code=code, label=f"Bus-{code}", mode="bus", status="scheduled", has_seat_inventory=True,
                     total_seats=total, accessible_seats=acc, depart_at=now + timedelta(minutes=30 + i),
                     arrive_at=now + timedelta(minutes=60 + i), created_by="seed")
        session.add(sv)
        svcs[code] = sv
    await session.flush()
    stops, seat_rows = [], []
    for i, sv in enumerate(svcs.values()):
        base = now + timedelta(minutes=30 + i)
        for seq, (n, off) in enumerate([(hub, 0), (d1, 20), (d2, 30)]):
            stops.append(dict(service_id=sv.id, seq=seq, node_id=n.id, arrive_at=base + timedelta(minutes=off),
                              depart_at=base + timedelta(minutes=off), is_skipped=False, is_via=False))
        seat_rows += [dict(service_id=sv.id, seat_no=f"W{k:02d}", is_accessible=True, status="free") for k in range(1, sv.accessible_seats + 1)]
        seat_rows += [dict(service_id=sv.id, seat_no=f"{k:03d}", is_accessible=False, status="free")
                      for k in range(1, sv.total_seats - sv.accessible_seats + 1)]
    await bulk(session, ServiceStop, stops)
    await bulk(session, Seat, seat_rows)
    session.add(PriorityRule(scenario_id=sc.id, version=1, is_active=True,
                             weights=weights or {"medical": 30, "wheelchair": 30, "elderly": 15, "with_children": 10,
                                                 "deadline_urgency": 20, "wait_time": 20}))
    batch = Batch(scenario_id=sc.id, status="closed", opens_at=now - timedelta(minutes=1), closes_at=now, trigger="disruption")
    session.add(batch)
    await session.flush()
    return Ctx(sc, hub, d1, d2, svcs, batch, now)


async def add_pax(session: AsyncSession, ctx: Ctx, name: str, *, c1: str | None = None, c2: str | None = None,
                  any_fastest: bool = False, party: int = 1, wheelchair: bool = False, medical: bool = False,
                  elderly: bool = False, with_children: bool = False, deadline: datetime | None = None,
                  waited_min: float = 0, allow_auto: bool = True, dest: str = "DST", state: str = "REQUESTED") -> Passenger:
    ctx.n += 1
    p = Passenger(scenario_id=ctx.sc.id, name=name, email=f"{name.lower()}-{ctx.n}@t.test", ticket_id=f"T-{ctx.sc.id}-{ctx.n}",
                  is_seeded=False, party_size=party, hub_node_id=ctx.hub.id,
                  destination_node_id=ctx.dest.id if dest == "DST" else ctx.dest2.id, wheelchair=wheelchair, elderly=elderly,
                  with_children=with_children, medical=medical, connection_deadline_at=deadline, allow_auto=allow_auto,
                  state=state, affected_at=ctx.now - timedelta(minutes=waited_min),
                  registered_at=ctx.now - timedelta(days=1) + timedelta(seconds=ctx.n))
    session.add(p)
    await session.flush()
    session.add(Request(scenario_id=ctx.sc.id, batch_id=ctx.batch.id, passenger_id=p.id,
                        choice1_service_id=ctx.services[c1].id if c1 else None,
                        choice2_service_id=ctx.services[c2].id if c2 else None, any_fastest=any_fastest, status="queued",
                        created_at=ctx.now))
    ctx.pax[name] = p
    return p


async def outcome(session: AsyncSession, ctx: Ctx) -> dict[str, tuple]:
    """name -> (state, service_code | None, choice_rank | None, seat_count)"""
    out = {}
    codes = {sv.id: c for c, sv in ctx.services.items()}
    for name, p in ctx.pax.items():
        await session.refresh(p)
        a = (await session.execute(select(Allocation).where(Allocation.passenger_id == p.id, Allocation.status.in_(("held", "confirmed"))))).scalars().first()
        out[name] = (p.state, codes[a.service_id] if a else None, a.choice_rank if a else None, a.seat_count if a else 0)
    return out
