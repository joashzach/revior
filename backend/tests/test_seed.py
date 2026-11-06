import time

from sqlalchemy import func, select

from app.db import get_sessionmaker
from app.models import Passenger, Seat, Service


async def test_reset_fast_and_deterministic(client, ops_headers, potheri):
    first = potheri
    assert first["counts"]["passengers"] >= 400
    assert first["counts"]["personas"] == 10
    assert first["duration_ms"] < 5000
    t = time.perf_counter()
    r = await client.post("/api/v1/ops/scenarios/potheri-demo/reset", headers=ops_headers)
    assert (time.perf_counter() - t) < 5
    assert r.json()["counts"] == first["counts"]
    print("reset counts", r.json())


async def test_calibrated_capacity(potheri):
    async with get_sessionmaker()() as s:
        svcs = (await s.execute(select(Service).where(Service.has_seat_inventory))).scalars().all()
        assert len(svcs) >= 10
        for sv in svcs:
            n = (await s.execute(select(func.count()).select_from(Seat).where(Seat.service_id == sv.id))).scalar()
            assert n == sv.total_seats > 0
        from app.models import Scenario
        assert (await s.execute(select(func.count()).select_from(Passenger).join(Scenario, Scenario.id == Passenger.scenario_id)
                                .where(Passenger.is_demo_persona, Scenario.slug == "potheri-demo"))).scalar() == 10
