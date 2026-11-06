import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from datetime import timedelta

import httpx
import pytest
import websockets
from sqlalchemy import select, update

from app import clock
from app.db import get_sessionmaker
from app.jobs import loops
from app.models import Allocation, Passenger, Service
from app.security import create_passenger_token
from app.ws.events import EVENT_TYPES
from app.ws.hub import Connection, hub
from tests.helpers import API, bearer, cancel, claim_persona, edge_between, services_by_code

BACKEND = os.path.dirname(os.path.dirname(__file__))


def types(since=0):
    return [m["type"] for m in hub.published[since:]]


@pytest.fixture
def recorder():
    hub.record, hub.published = True, []
    yield hub
    hub.record = False


async def test_event_sequence_for_demo_steps_1_to_9(client, potheri, ops_headers, recorder):
    # 1 — judge claims a persona -> ops sees the judge appear
    ta, pa = await claim_persona(client, "wheelchair-guindy")
    r = await client.post(f"{API}/auth/demo-claim", json={"persona_id": pa["id"] + 1})
    assert r.status_code == 200
    assert {"persona.claimed", "passenger.registered"} <= set(types())
    pc = next(m for m in hub.published if m["type"] == "passenger.registered")
    assert pc["_ops"] is True and pc["scenario"] == "potheri-demo" and "ts" in pc
    tb = r.json()["token"]
    # 2 — cancel the train -> every phone flips
    start = len(hub.published)
    await cancel(client, ops_headers)
    seen = set(types(start))
    assert {"service.status_changed", "disruption.created", "batch.opened", "notification.created"} <= seen
    sc_ev = next(m for m in hub.published[start:] if m["type"] == "service.status_changed")
    assert sc_ev["data"]["status"] == "cancelled" and pa["id"] in sc_ev["_to"] and sc_ev["_ops"]
    # 3 — both judges choose
    for t in (ta, tb):
        opts = (await client.get(f"{API}/me/options", headers=bearer(t))).json()["items"]
        assert (await client.post(f"{API}/me/request", headers=bearer(t), json={"choice1_service_id": opts[0]["request_service_id"]})).status_code == 200
    # 4 — batch window closes -> batch_closer closes and auto-runs the allocation
    start = len(hub.published)
    handled = await loops.batch_closer_once(now=clock.utcnow() + timedelta(hours=1))
    assert handled == 1
    seen = set(types(start))
    assert {"batch.closed", "allocation.run_started", "allocation.result", "allocation.run_completed", "waitlist.position_changed"} & seen
    assert {"batch.closed", "allocation.run_started", "allocation.result", "allocation.run_completed"} <= seen
    order = types(start)
    assert order.index("allocation.run_started") < order.index("allocation.run_completed")
    res = next(m for m in hub.published[start:] if m["type"] == "allocation.result" and pa["id"] in m["_to"])
    assert res["data"]["state"] in ("HELD", "WAITLISTED", "UNRESOLVED") and res["data"]["explanation"]
    # 6 — one judge declines / the other receives the freed seat (cascade) or ops sees the release
    st = (await client.get(f"{API}/me/status", headers=bearer(ta))).json()
    start = len(hub.published)
    if st["state"] == "HELD":
        r = await client.post(f"{API}/me/allocation/decline", headers={**bearer(ta), "Idempotency-Key": str(uuid.uuid4())})
        assert r.status_code == 200
        assert {"allocation.declined", "seat.released"} <= set(types(start))
    # hold expiry path: 30 s warning, then expiry
    tbs = (await client.get(f"{API}/me/status", headers=bearer(tb))).json()
    if tbs["state"] == "HELD":
        exp = clock.utcnow().replace(microsecond=0)
        async with get_sessionmaker()() as s:
            await s.execute(update(Allocation).where(Allocation.passenger_id == pa["id"] + 1, Allocation.status == "held")
                            .values(hold_expires_at=exp + timedelta(seconds=20)))
            await s.commit()
        start = len(hub.published)
        await loops.hold_expirer_once(now=exp)
        assert "hold.expiring" in types(start)
        start = len(hub.published)
        await loops.hold_expirer_once(now=exp + timedelta(seconds=30))
        assert {"hold.expired", "seat.released"} <= set(types(start))
    # 7 — close a road: buses re-route, ETAs update
    start = len(hub.published)
    e = await edge_between(client, ops_headers, "URP", "VAN", "road")
    assert (await client.post(f"{API}/ops/disruptions", headers=ops_headers, json={"type": "closure", "edge_id": e["id"], "reason": "x"})).status_code == 200
    seen = set(types(start))
    assert {"service.rerouted", "eta.updated", "service.status_changed", "disruption.created"} <= seen
    rr = next(m for m in hub.published[start:] if m["type"] == "service.rerouted")
    assert rr["data"]["polyline"]["type"] == "LineString" and rr["data"]["skipped_stops"] is not None
    # 8 / 9 — rules editor + add capacity (events completed in Stage 8 tests) ; every event type is in the catalogue
    assert set(types()) <= set(EVENT_TYPES)


async def test_kpi_broadcaster_is_debounced_and_vehicle_positions_flow(client, potheri, ops_headers, recorder):
    ops_conn = Connection("operator", 0)
    hub.add(ops_conn)
    try:
        await cancel(client, ops_headers)                      # marks KPI dirty
        n = await loops.kpi_broadcaster_once()
        assert n == 1
        n2 = await loops.kpi_broadcaster_once()               # nothing changed since -> no new snapshot (debounce)
        assert n2 == 0
        msgs = []
        while not ops_conn.queue.empty():
            msgs.append(ops_conn.queue.get_nowait())
        kpi = [m for m in msgs if m["type"] == "kpi.updated"]
        assert len(kpi) == 1 and kpi[0]["data"]["affected"] > 300 and kpi[0]["data"]["batch"]["status"] == "open"
        # simulator: advance to 20 minutes after t0: the earliest buses are running and move along their polyline
        svcs = await services_by_code(client, ops_headers)
        async with get_sessionmaker()() as s:
            from app.models import Scenario
            sc = (await s.execute(select(Scenario).where(Scenario.slug == "potheri-demo"))).scalars().one()
            t0 = sc.t0
        await loops.simulator_tick_once(now=t0 + timedelta(minutes=19))
        await loops.simulator_tick_once(now=t0 + timedelta(minutes=24))
        msgs = []
        while not ops_conn.queue.empty():
            msgs.append(ops_conn.queue.get_nowait())
        pos = [m for m in msgs if m["type"] == "vehicle.positions"]
        status = [m for m in msgs if m["type"] == "service.status_changed"]
        assert pos and all({"service_id", "lat", "lng", "progress"} <= set(i) for m in pos for i in m["data"]["items"])
        assert any(i["service_id"] == svcs["MTC-570A"]["id"] for m in pos for i in m["data"]["items"])
        assert any(m["data"]["status"] == "running" for m in status)
        p1 = [i["progress"] for m in pos for i in m["data"]["items"] if i["service_id"] == svcs["MTC-570A"]["id"]]
        assert p1 == sorted(p1) and p1[-1] > p1[0] >= 0                      # moves forward over time
        after = await services_by_code(client, ops_headers)
        assert after["MTC-570A"]["status"] == "running"
    finally:
        hub.remove(ops_conn)


async def test_departing_service_drops_waitlist_and_expires_holds(client, potheri, ops_headers):
    await cancel(client, ops_headers)
    r = await client.post(f"{API}/ops/allocation/run", headers=ops_headers, json={"mode": "greedy"})
    assert r.status_code == 200
    async with get_sessionmaker()() as s:
        from app.models import Scenario, WaitlistEntry
        sc = (await s.execute(select(Scenario).where(Scenario.slug == "potheri-demo"))).scalars().one()
        held_before = (await s.execute(select(Allocation).where(Allocation.status == "held"))).scalars().all()
        assert held_before
    await loops.simulator_tick_once(now=sc.t0 + timedelta(hours=3))        # everything has departed / arrived
    async with get_sessionmaker()() as s:
        still = (await s.execute(select(Allocation).where(Allocation.status == "held"))).scalars().all()
        wl = (await s.execute(select(WaitlistEntry))).scalars().all()
        svc_status = {x.status for x in (await s.execute(select(Service).where(Service.scenario_id == sc.id))).scalars()}
    assert not still and not [w for w in wl if w.status == "active"]
    assert svc_status <= {"completed", "cancelled"}


# ------------------------------------------------------------------------------------ real WebSocket transport
def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_server():
    port = _free_port()
    env = {**os.environ, "RUN_BACKGROUND_LOOPS": "true", "AUTO_BOOTSTRAP": "false", "LOG_LEVEL": "WARNING", "BATCH_WINDOW_SECONDS": "3"}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--workers", "1"],
                            cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            if httpx.get(f"{base}/api/v1/health", timeout=1).status_code == 200:
                break
        except Exception:
            time.sleep(0.5)
    else:
        proc.kill()
        raise RuntimeError("uvicorn did not start")
    yield base
    proc.terminate()
    proc.wait(10)


async def recv_until(ws, wanted: set[str], timeout=20, collected=None):
    got = collected if collected is not None else []
    end = time.time() + timeout
    while time.time() < end and not wanted <= {m["type"] for m in got}:
        try:
            m = json.loads(await asyncio.wait_for(ws.recv(), 3))
        except asyncio.TimeoutError:
            continue
        got.append(m)
    return got


async def test_real_websockets_demo_flow(live_server, potheri):
    base = live_server
    ws_base = base.replace("http", "ws")
    async with httpx.AsyncClient(base_url=f"{base}/api/v1", timeout=30) as c:
        ops = (await c.post("/auth/ops-login", json={"password": "ops-test"})).json()["token"]
        oh = {"Authorization": f"Bearer {ops}"}
        cfg_ = await c.patch("/ops/scenarios/potheri-demo/config", headers=oh, json={"batch_window_seconds": 3, "auto_run_on_batch_close": True})
        assert cfg_.status_code == 200 and cfg_.json()["batch_window_seconds"] == 3 and cfg_.json()["join_qr_mode"] == "corner"
        claim = (await c.post("/auth/demo-claim", json={"surprise": True})).json()
        pt, pid = claim["token"], claim["passenger"]["id"]
        ph = {"Authorization": f"Bearer {pt}"}
        # bad tokens are refused with close code 4401
        async with websockets.connect(f"{ws_base}/ws/passenger?token=garbage") as bad:
            with pytest.raises(websockets.ConnectionClosed) as ei:
                await bad.recv()
            assert ei.value.rcvd.code == 4401
        async with websockets.connect(f"{ws_base}/ws/passenger?token={pt}") as pws, \
                websockets.connect(f"{ws_base}/ws/ops?token={ops}") as ows:
            await pws.send(json.dumps({"type": "ping"}))
            pong = json.loads(await asyncio.wait_for(pws.recv(), 5))
            assert pong["type"] == "pong"
            svcs = {s["code"]: s for s in (await c.get("/ops/services", headers=oh)).json()["items"]}
            r = await c.post("/ops/disruptions", headers=oh, json={"type": "cancellation", "service_id": svcs["EMU-CGL-BCH-1810"]["id"], "reason": "test"})
            assert r.status_code == 200
            pmsgs = await recv_until(pws, {"service.status_changed", "disruption.created", "batch.opened", "notification.created"})
            assert {"service.status_changed", "disruption.created", "batch.opened", "notification.created"} <= {m["type"] for m in pmsgs}
            assert all({"type", "ts", "scenario", "data"} <= set(m) for m in pmsgs)
            omsgs = await recv_until(ows, {"disruption.created", "kpi.updated"})
            assert {"disruption.created", "kpi.updated"} <= {m["type"] for m in omsgs}
            # request; the 3-second batch window then closes by itself and the real batch_closer loop runs the allocation
            opts = (await c.get("/me/options", headers=ph)).json()["items"]
            assert (await c.post("/me/request", headers=ph, json={"choice1_service_id": opts[0]["request_service_id"]})).status_code == 200
            pm2 = await recv_until(pws, {"allocation.result"}, timeout=25)
            assert "allocation.result" in {m["type"] for m in pm2}
            om2 = await recv_until(ows, {"allocation.run_completed", "batch.closed"}, timeout=10)
            assert {"allocation.run_completed"} <= {m["type"] for m in om2}
            # logging out kills the socket (token_version bump)
            assert (await c.post("/auth/logout", headers=ph)).status_code == 204
            with pytest.raises(websockets.ConnectionClosed):
                for _ in range(10):
                    await asyncio.wait_for(pws.recv(), 3)
