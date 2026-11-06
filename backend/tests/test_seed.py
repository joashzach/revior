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


CAPS = {"bus": 50, "shuttle": 30, "charter_bus": 50, "local_train": 60}


async def test_capacity_is_realistic_with_extra_vehicles_not_bigger_ones(potheri):
    from app.models import Scenario
    async with get_sessionmaker()() as s:
        svcs = (await s.execute(select(Service).join(Scenario, Scenario.id == Service.scenario_id).where(
            Service.has_seat_inventory, Scenario.slug == "potheri-demo"))).scalars().all()
    assert len(svcs) >= 15
    for sv in svcs:
        assert 0 < sv.total_seats <= CAPS[sv.mode], (sv.code, sv.mode, sv.total_seats)
        assert 2 <= sv.accessible_seats <= 4 and sv.accessible_seats <= sv.total_seats, (sv.code, sv.accessible_seats)
    codes = {sv.code for sv in svcs}
    assert {"MTC-570A", "MTC-570A-2"} <= codes                       # demand beyond one bus -> a second bus on the same route
    by_code = {sv.code: sv for sv in svcs}
    assert by_code["MTC-570A-2"].label.startswith(by_code["MTC-570A"].label)
    assert max(sv.total_seats for sv in svcs if sv.mode == "bus") == 50


async def test_judges_find_a_few_free_seats_and_an_unresolved_queue_exists(client, potheri, ops_headers):
    from tests.helpers import cancel
    await cancel(client, ops_headers)
    r = await client.post(f"{API}/ops/allocation/run", headers=ops_headers, json={"mode": "greedy"})
    assert r.status_code == 200
    cap = (await client.get(f"{API}/ops/capacity", headers=ops_headers)).json()["items"]
    popular = [c for c in cap if c["service"]["mode"] in ("bus", "shuttle", "charter_bus")]
    assert any(1 <= c["free"] <= 4 for c in popular)                 # 2-3 seats left on popular judge choices
    k = (await client.get(f"{API}/ops/kpis", headers=ops_headers)).json()
    assert k["unresolved"] + k["waitlisted"] > 0                     # at least one destination is under capacity
    assert all(c["total_seats"] <= CAPS[c["service"]["mode"]] for c in cap)


API = "/api/v1"
