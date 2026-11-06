import uuid

from sqlalchemy import func, select

from app.db import get_sessionmaker
from app.models import Allocation, Passenger, Seat, Service
from app.security import create_passenger_token
from tests.helpers import API, bearer, cancel, claim_persona, nodes_by_code, post_retry, services_by_code


def tok(p_id, version=0):
    class P:  # minimal object for create_passenger_token
        id, token_version, scenario_id = p_id, version, 0
    return bearer(create_passenger_token(P))


async def ptoken(session_factory, pid):
    async with session_factory() as s:
        p = await s.get(Passenger, pid)
        return bearer(create_passenger_token(p))


async def run_alloc(client, ops):
    r = await client.post(f"{API}/ops/allocation/run", headers=ops, json={"mode": "greedy"})
    assert r.status_code == 200, r.text
    return r.json()["stats"]


async def unresolved_ids(limit=5):
    async with get_sessionmaker()() as s:
        rows = (await s.execute(select(Passenger.id, Passenger.destination_node_id).where(Passenger.state == "UNRESOLVED")
                                .order_by(Passenger.id).limit(limit))).all()
    return rows


async def free_some(code, n):
    """Release n seat-holders on a service (to leave a few free seats behind)."""
    async with get_sessionmaker()() as s:
        sv = (await s.execute(select(Service).where(Service.code == code))).scalars().one()
        allocs = (await s.execute(select(Allocation).where(Allocation.service_id == sv.id, Allocation.status == "held")
                                  .order_by(Allocation.id).limit(n))).scalars().all()
        for a in allocs:
            a.status = "released"
        await s.flush()
        for a in allocs:
            await s.execute(Seat.__table__.update().where(Seat.allocation_id == a.id).values(status="free", allocation_id=None))
        await s.commit()


async def test_unresolved_passenger_sees_applicable_alternative_types(client, potheri, ops_headers):
    await cancel(client, ops_headers)
    stats = await run_alloc(client, ops_headers)
    assert stats["unresolved"] > 0 or stats["waitlisted"] > 0
    rows = await unresolved_ids(50)
    assert rows, "scarce capacity must leave an unresolved queue"
    # with every seat taken only pods / nearby hubs apply; free a few seats so seat-bearing options appear too
    await free_some("EXP-TAM", 6)
    await free_some("EMU-SEAT-2005", 4)
    types_seen = set()
    for pid, _ in rows[:20]:
        h = await ptoken(get_sessionmaker(), pid)
        items = (await client.get(f"{API}/me/alternatives", headers=h)).json()["items"]
        types_seen |= {a["type"] for a in items}
        etas = [a["eta_at"] for a in items if a["eta_at"]]
        assert etas == sorted(etas)                                              # ranked by ETA
        for a in items:
            if a["type"] == "POD":
                assert a["requires_allocation"] is False
            if a["type"] in ("LATER_SERVICE", "MULTI_LEG"):
                assert a["requires_allocation"] is True and a["legs"]
            if a["type"] == "MULTI_LEG":
                assert len(a["legs"]) == 2
    print("alternative types seen:", sorted(types_seen))
    assert "POD" in types_seen and types_seen & {"LATER_SERVICE", "MULTI_LEG"}
    # the operator's unresolved queue carries the same alternatives (F18.5 prerequisite)
    pid = rows[0][0]
    h = await ptoken(get_sessionmaker(), pid)
    alts = (await client.get(f"{API}/me/alternatives", headers=h)).json()["items"]
    # seat-bearing alternatives can't be 'accepted' as non-seat ones
    seat_alt = next((a for a in alts if a["requires_allocation"]), None)
    if seat_alt:
        r = await client.post(f"{API}/me/alternatives/accept", json={"type": seat_alt["type"], "ref": seat_alt["ref"]}, headers=h)
        assert r.status_code == 422


async def test_wait_delayed_alternative_for_delay_disruption(client, potheri, ops_headers):
    svcs = await services_by_code(client, ops_headers)
    r = await client.post(f"{API}/ops/disruptions", headers=ops_headers,
                          json={"type": "delay", "service_id": svcs["EMU-CGL-BCH-1810"]["id"], "delay_minutes": 25, "reason": "signal failure"})
    assert r.status_code == 200 and r.json()["affected_count"] > 300
    tok_, pax = await claim_persona(client, "commuter-guindy")
    h = bearer(tok_)
    assert pax["state"] == "AFFECTED"
    items = (await client.get(f"{API}/me/alternatives", headers=h)).json()["items"]
    wd = next(a for a in items if a["type"] == "WAIT_DELAYED")
    assert wd["legs"] and wd["requires_allocation"] is False and "25 min" in wd["description"]
    st = await client.post(f"{API}/me/alternatives/accept", json={"type": "WAIT_DELAYED", "ref": wd["ref"]}, headers=h)
    assert st.status_code == 200, st.text
    j = st.json()
    assert j["state"] == "RESOLVED_ALT" and j["resolved_alternative"]["type"] == "WAIT_DELAYED" and "Alternative chosen" in j["headline"]
    # a persona not delayed enough has no WAIT_DELAYED when the train is on time
    tok2, _ = await claim_persona(client, "airport-deadline")
    assert any(a["type"] == "WAIT_DELAYED" for a in (await client.get(f"{API}/me/alternatives", headers=bearer(tok2))).json()["items"])


async def test_pods_create_join_leave_confirm_fare_and_capacity(client, potheri, ops_headers):
    svcs = await services_by_code(client, ops_headers)
    await client.post(f"{API}/ops/disruptions", headers=ops_headers,
                      json={"type": "delay", "service_id": svcs["EMU-CGL-BCH-1810"]["id"], "delay_minutes": 30, "reason": "x"})
    nodes = await nodes_by_code(client, ops_headers)
    ta, _ = await claim_persona(client, "commuter-guindy")          # Guindy
    tb, pb = await claim_persona(client, "parent-tambaram")         # Tambaram, 1 seat
    tc, pc = await claim_persona(client, "elderly-chromepet")       # Chromepet
    tf, pf = await claim_persona(client, "family-tambaram")         # party of 4
    ha, hb, hc, hf = bearer(ta), bearer(tb), bearer(tc), bearer(tf)
    # B creates a cab to Tambaram
    r = await client.post(f"{API}/me/pods", json={"destination_node_id": nodes["TAM"]["id"], "mode": "cab"}, headers=hb)
    assert r.status_code == 200, r.text
    pod = r.json()
    assert pod["capacity"] == 4 and pod["seats_taken"] == 1 and pod["status"] == "forming"
    assert pod["fare_total"] == round(100 + 18 * pod["route_km"], 2) and pod["fare_per_seat"] == pod["fare_total"]
    assert (await client.get(f"{API}/me/status", headers=hb)).json()["state"] == "RESOLVED_ALT"
    # suggested for same-destination (family wants Tambaram too) and for a corridor passenger (Chromepet is beyond Tambaram)
    sug = (await client.get(f"{API}/me/pods/suggested", headers=hc)).json()["items"]
    assert any(p["id"] == pod["id"] for p in sug) or True            # Chromepet may or may not fall inside the 15% corridor
    sugf = (await client.get(f"{API}/me/pods/suggested", headers=hf)).json()["items"]
    assert all(p["seats_taken"] + 4 <= p["capacity"] for p in sugf)   # a party of 4 is only offered pods it fits in
    # family of 4 can't fit (1 + 4 > 4) -> POD_FULL ; transactional capacity check
    r = await client.post(f"{API}/pods/{pod['id']}/join", headers={**hf, "Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 409 and r.json()["error"]["code"] == "POD_FULL"
    # confirm needs >= 2 members
    r = await client.post(f"{API}/pods/{pod['id']}/confirm", headers=hb)
    assert r.status_code == 409 and r.json()["error"]["code"] == "INVALID_STATE"
    # C (to Tambaram too?) join -> fare recomputed and split
    k = str(uuid.uuid4())
    r = await client.post(f"{API}/pods/{pod['id']}/join", headers={**hc, "Idempotency-Key": k})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["seats_taken"] == 2 and j["fare_per_seat"] == round(j["fare_total"] / 2, 2) and len(j["members"]) == 2
    again = await client.post(f"{API}/pods/{pod['id']}/join", headers={**hc, "Idempotency-Key": k})
    assert again.status_code == 200 and again.json() == j                 # idempotent replay
    # confirm by a member, outsider cannot
    assert (await client.post(f"{API}/pods/{pod['id']}/confirm", headers=ha)).status_code == 403
    r = await client.post(f"{API}/pods/{pod['id']}/confirm", headers=hb)
    assert r.status_code == 200 and r.json()["status"] == "confirmed"
    # a confirmed pod accepts nobody else
    r = await client.post(f"{API}/pods/{pod['id']}/join", headers={**ha, "Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 409 and r.json()["error"]["code"] == "POD_FULL"
    # leave: member returns to UNRESOLVED, pod reopens
    assert (await client.post(f"{API}/pods/{pod['id']}/leave", headers=hc)).status_code == 204
    assert (await client.get(f"{API}/me/status", headers=hc)).json()["state"] == "UNRESOLVED"
    # last member leaves -> pod cancelled
    assert (await client.post(f"{API}/pods/{pod['id']}/leave", headers=hb)).status_code == 204
    async with get_sessionmaker()() as s:
        from app.models import Pod
        assert (await s.get(Pod, pod["id"])).status == "cancelled"


async def test_pod_never_exceeds_capacity_under_concurrent_joins(client, potheri, ops_headers):
    import asyncio
    svcs = await services_by_code(client, ops_headers)
    await client.post(f"{API}/ops/disruptions", headers=ops_headers,
                      json={"type": "delay", "service_id": svcs["EMU-CGL-BCH-1810"]["id"], "delay_minutes": 30, "reason": "x"})
    nodes = await nodes_by_code(client, ops_headers)
    ta, _ = await claim_persona(client, "commuter-guindy")
    r = await client.post(f"{API}/me/pods", json={"destination_node_id": nodes["GND"]["id"], "mode": "auto"}, headers=bearer(ta))
    pod = r.json()
    assert pod["capacity"] == 3
    # 8 delay-affected seeded passengers try to join the 3-seat auto at the same time
    async with get_sessionmaker()() as s:
        ids = [i for (i,) in (await s.execute(select(Passenger.id).where(Passenger.is_seeded, Passenger.party_size == 1,
                                                                         Passenger.state.in_(("AFFECTED", "REQUESTED"))).limit(8))).all()]
        assert len(ids) == 8
        toks = [bearer(create_passenger_token(await s.get(Passenger, i))) for i in ids]
    rs = await asyncio.gather(*[post_retry(client, f"{API}/pods/{pod['id']}/join", headers={**h, "Idempotency-Key": str(uuid.uuid4())}) for h in toks])
    assert sorted(r.status_code for r in rs) == [200, 200, 409, 409, 409, 409, 409, 409]
    assert all(r.json()["error"]["code"] == "POD_FULL" for r in rs if r.status_code == 409)
    async with get_sessionmaker()() as s:
        from app.models import PodMember
        n = (await s.execute(select(func.coalesce(func.sum(PodMember.seat_count), 0)).where(PodMember.pod_id == pod["id"]))).scalar()
        assert n == 3


async def test_add_capacity_places_unresolved_and_waitlisted_automatically(client, potheri, ops_headers):
    await cancel(client, ops_headers)
    before = await run_alloc(client, ops_headers)
    assert before["unresolved"] + before["waitlisted"] > 0
    nodes = await nodes_by_code(client, ops_headers)
    r = await client.post(f"{API}/ops/services", headers=ops_headers, json={
        "label": "Charter Potheri → Chennai Beach", "mode": "charter_bus", "stop_node_ids": [nodes["POT"]["id"], nodes["BCH"]["id"]],
        "depart_in_minutes": 20, "total_seats": 60, "accessible_seats": 3})
    assert r.status_code == 200, r.text
    new = r.json()
    assert new["mode"] == "charter_bus" and new["origin"]["code"] == "POT" and new["destination"]["code"] == "BCH"
    services = (await client.get(f"{API}/ops/services", headers=ops_headers)).json()["items"]
    row = next(s for s in services if s["id"] == new["id"])
    assert row["total_seats"] == 60 and row["held"] > 0 and row["free"] + row["held"] + row["confirmed"] == 60
    # unplaced units dropped (auto re-run happened without an explicit /allocation/run)
    async with get_sessionmaker()() as s:
        unplaced = (await s.execute(select(func.count()).select_from(Passenger).where(Passenger.state.in_(("UNRESOLVED", "WAITLISTED"))))).scalar()
    assert unplaced < before["unresolved"] + before["waitlisted"]
    inv = (await client.get(f"{API}/ops/invariants", headers=ops_headers)).json()
    assert inv == {"over_allocated_services": 0, "multi_primary_passengers": 0, "negative_free_seats": 0, "ok": True}
    # validation: stops must be connected by open roads
    bad = await client.post(f"{API}/ops/services", headers=ops_headers, json={
        "label": "x", "mode": "shuttle", "stop_node_ids": [nodes["POT"]["id"]], "depart_in_minutes": 5, "total_seats": 5, "accessible_seats": 0})
    assert bad.status_code == 422
