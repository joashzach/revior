import asyncio

import httpx

from app.domain import stress
from app.main import app
from app.ws.hub import hub
from tests.helpers import API


async def test_stress_300_requests_10_seats_zero_over_allocation():
    world = await stress.build_world(300, 10)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://stress") as c:
            res = await stress.run_stress(c, world, requests=300)
    finally:
        await stress.cleanup(world["scenario_id"])
    print("stress:", res)
    assert res["total"] == 300 and res["five_xx"] == 0 and res["over_allocations"] == 0
    assert res["confirmed"] <= 10 and res["invariants_ok"] and res["multi_primary"] == 0 and res["passed"]
    assert set(res["by_status"]) <= {200, 409}                    # only success or a clean business conflict


async def test_stress_endpoint_streams_progress_and_result(client, potheri, ops_headers):
    hub.record, hub.published = True, []
    try:
        r = await client.post(f"{API}/ops/stress/run", headers=ops_headers, json={"requests": 200, "seats": 10})
        assert r.status_code == 200 and r.json()["run_id"].startswith("stress-")
        for _ in range(240):
            if any(m["type"] == "stress.result" for m in hub.published):
                break
            await asyncio.sleep(0.5)
        types = [m["type"] for m in hub.published]
        assert "stress.result" in types and "stress.progress" in types
        res = next(m for m in hub.published if m["type"] == "stress.result")["data"]
        assert res == {"total": 200, "confirmed": res["confirmed"], "capacity": 10, "over_allocations": 0, "five_xx": 0, "passed": True}
        assert res["confirmed"] <= 10
        prog = next(m for m in hub.published if m["type"] == "stress.progress")["data"]
        assert set(prog) == {"sent", "ok", "conflicts", "errors"}
    finally:
        hub.record = False
    inv = (await client.get(f"{API}/ops/invariants", headers=ops_headers)).json()
    assert inv["ok"]                                              # the demo scenario was never touched


async def test_stress_refused_outside_demo_mode(client, potheri, ops_headers):
    await client.patch(f"{API}/ops/scenarios/potheri-demo/config", headers=ops_headers, json={"demo_mode": False})
    r = await client.post(f"{API}/ops/stress/run", headers=ops_headers, json={"requests": 10, "seats": 2})
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"
    await client.patch(f"{API}/ops/scenarios/potheri-demo/config", headers=ops_headers, json={"demo_mode": True})
