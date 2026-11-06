import pytest
from sqlalchemy import func, select

from app.db import get_sessionmaker
from app.models import Batch, Notification, Passenger, Request, Service
from tests.helpers import API, bearer, cancel, claim_persona, edge_between, nodes_by_code, services_by_code


async def count(model, *where):
    async with get_sessionmaker()() as s:
        return (await s.execute(select(func.count()).select_from(model).where(*where))).scalar()


async def test_cancel_featured_flags_everyone_opens_batch_and_seeds_requests(client, potheri, ops_headers):
    svcs = await services_by_code(client, ops_headers)
    prev = (await client.get(f"{API}/ops/disruptions/preview", headers=ops_headers,
                             params={"type": "cancellation", "service_id": svcs["EMU-CGL-BCH-1810"]["id"]})).json()
    r = await cancel(client, ops_headers)
    assert r["affected_count"] >= 370, r["affected_count"]
    assert prev["affected_count"] == r["affected_count"]          # preview == reality
    assert sum(x["count"] for x in prev["by_destination"]) == r["affected_count"]
    assert r["batch"]["status"] == "open"
    async with get_sessionmaker()() as s:
        affected = (await s.execute(select(func.count()).select_from(Passenger).where(
            Passenger.state.in_(("AFFECTED", "REQUESTED"))))).scalar()
        requested = (await s.execute(select(func.count()).select_from(Request).where(Request.status == "queued"))).scalar()
        batches = (await s.execute(select(Batch).where(Batch.status == "open"))).scalars().all()
        seeded_aff = (await s.execute(select(func.count()).select_from(Passenger).where(
            Passenger.is_seeded, Passenger.state == "REQUESTED"))).scalar()
        notes = (await s.execute(select(func.count()).select_from(Notification).where(
            Notification.template == "disruption_alert"))).scalar()
    assert affected == r["affected_count"] and len(batches) == 1       # one open batch only
    assert requested == seeded_aff and requested >= 360               # every seeded affected passenger has a request
    assert notes == r["affected_count"]
    # personas are not seeded: affected but "not checked in"
    tok, pax = await claim_persona(client, "wheelchair-guindy")
    trip = (await client.get(f"{API}/me/trip", headers=bearer(tok))).json()
    assert pax["state"] == "AFFECTED"
    assert trip["ticket"]["service"]["status"] == "cancelled" and "cancelled" in trip["headline"]
    assert trip["disruption"]["type"] == "cancellation"
    # second cancel of the same service is rejected; listing shows the disruption
    svc_id = svcs["EMU-CGL-BCH-1810"]["id"]
    r2 = await client.post(f"{API}/ops/disruptions", headers=ops_headers, json={"type": "cancellation", "service_id": svc_id})
    assert r2.status_code == 409
    lst = (await client.get(f"{API}/ops/disruptions", headers=ops_headers)).json()["items"]
    assert lst[0]["affected_count"] == r["affected_count"] and lst[0]["resolved_at"] is None


async def test_registration_during_active_disruption_goes_straight_to_affected(client, potheri, ops_headers):
    await cancel(client, ops_headers)
    dest = (await client.get(f"{API}/destinations", params={"q": "Guindy"})).json()["items"][0]["id"]
    r = await client.post(f"{API}/auth/register", json={"name": "Late", "email": "late@example.com", "password": "secret1",
                                                        "destination_node_id": dest, "needs": {}, "party_size": 1})
    assert r.status_code == 200 and r.json()["passenger"]["state"] == "AFFECTED"
    opts = await client.get(f"{API}/me/options", headers=bearer(r.json()["token"]))
    assert opts.status_code == 200 and opts.json()["batch"]["status"] == "open"


async def test_delay_threshold_and_deadline_break(client, potheri, ops_headers):
    svcs = await services_by_code(client, ops_headers)
    sid = svcs["EMU-CGL-BCH-1810"]["id"]
    q = {"type": "delay", "service_id": sid}
    p15 = (await client.get(f"{API}/ops/disruptions/preview", headers=ops_headers, params={**q, "delay_minutes": 15})).json()
    p25 = (await client.get(f"{API}/ops/disruptions/preview", headers=ops_headers, params={**q, "delay_minutes": 25})).json()
    # 15 min < 20 min threshold: only passengers whose connection deadline breaks are affected
    async with get_sessionmaker()() as s:
        dl = (await s.execute(select(func.count()).select_from(Passenger).where(
            Passenger.ticket_service_id == sid, Passenger.connection_deadline_at.is_not(None)))).scalar()
        total = (await s.execute(select(func.count()).select_from(Passenger).where(Passenger.ticket_service_id == sid))).scalar()
    assert 0 <= p15["affected_count"] <= dl and p15["affected_count"] < total * 0.5
    assert p25["affected_count"] == total                      # >= threshold: everyone on the train
    # a deadline-less passenger (not affected at 15) only sees a delay pill
    r = await client.post(f"{API}/ops/disruptions", headers=ops_headers,
                          json={"type": "delay", "service_id": sid, "delay_minutes": 15, "reason": "signal failure"})
    assert r.status_code == 200 and r.json()["affected_count"] == p15["affected_count"]
    tok, _ = await claim_persona(client, "commuter-guindy")        # no deadline
    trip = (await client.get(f"{API}/me/trip", headers=bearer(tok))).json()
    assert trip["ticket"]["service"]["status"] == "delayed" and trip["ticket"]["service"]["delay_minutes"] == 15
    assert "late" in trip["headline"].lower() and (await client.get(f"{API}/me", headers=bearer(tok))).json()["state"] == "BOOKED"


async def test_rail_closure_short_terminates_and_flags_passengers_beyond(client, potheri, ops_headers):
    e = await edge_between(client, ops_headers, "CHR", "PLV", "rail")
    prev = (await client.get(f"{API}/ops/disruptions/preview", headers=ops_headers,
                             params={"type": "closure", "edge_id": e["id"]})).json()
    r = await client.post(f"{API}/ops/disruptions", headers=ops_headers, json={"type": "closure", "edge_id": e["id"], "reason": "track fault"})
    assert r.status_code == 200
    assert r.json()["affected_count"] == prev["affected_count"] > 100
    svcs = await services_by_code(client, ops_headers)
    nodes = await nodes_by_code(client, ops_headers)
    feat = svcs["EMU-CGL-BCH-1810"]
    assert feat["status"] == "rerouted" and feat["destination"]["code"] == "CHR"     # short-terminated at Chromepet
    net = (await client.get(f"{API}/ops/network", headers=ops_headers)).json()
    assert next(x for x in net["edges"] if x["id"] == e["id"])["is_closed"] is True
    async with get_sessionmaker()() as s:
        # passengers to Tambaram / Chromepet are NOT affected, those beyond are
        rows = (await s.execute(select(Passenger.destination_node_id, Passenger.state).where(
            Passenger.is_seeded, Passenger.ticket_service_id == feat["id"]))).all()
    by = {}
    for d, st in rows:
        by.setdefault(d, set()).add(st)
    assert by[nodes["TAM"]["id"]] == {"BOOKED"} and by[nodes["CHR"]["id"]] == {"BOOKED"}
    assert "BOOKED" not in by[nodes["GND"]["id"]]
    # a bus to Guindy cannot use rail; unaffected by rail closure
    assert svcs["MTC-570A"]["status"] == "scheduled"


async def test_road_closure_reroutes_bus_with_new_polyline_and_skips_stop(client, potheri, ops_headers):
    before = await services_by_code(client, ops_headers)
    e = await edge_between(client, ops_headers, "URP", "VAN", "road")
    r = await client.post(f"{API}/ops/disruptions", headers=ops_headers, json={"type": "closure", "edge_id": e["id"], "reason": "GST Road closed near Vandalur"})
    assert r.status_code == 200, r.text
    after = await services_by_code(client, ops_headers)
    for code in ("MTC-570A", "MTC-599", "EXP-TAM"):
        assert after[code]["status"] == "rerouted", code
        assert after[code]["polyline"] != before[code]["polyline"], code
    # a bus not crossing the closed edge is untouched (airport shuttle is also GST via vias -> rerouted too)
    assert after["CHR-EGM"]["status"] in ("rerouted", "scheduled")
    # ETA grew (detour is longer) and Vandalur is no longer served by the stopping bus
    assert after["MTC-570A"]["arrive_at"] > before["MTC-570A"]["arrive_at"]
    async with get_sessionmaker()() as s:
        from app.models import ServiceStop
        sid = after["MTC-570A"]["id"]
        stops = (await s.execute(select(ServiceStop).where(ServiceStop.service_id == sid).order_by(ServiceStop.seq))).scalars().all()
    nodes = await nodes_by_code(client, ops_headers)
    van = next(x for x in stops if x.node_id == nodes["VAN"]["id"])
    assert van.is_skipped
    assert {nodes["NED"]["id"], nodes["MUD"]["id"]} <= {x.node_id for x in stops if x.is_via}
    # reopening restores the edge (routes are not reverted)
    d = r.json()["disruption"]["id"]
    assert (await client.post(f"{API}/ops/disruptions/{d}/resolve", headers=ops_headers)).status_code == 200
    net = (await client.get(f"{API}/ops/network", headers=ops_headers)).json()
    assert next(x for x in net["edges"] if x["id"] == e["id"])["is_closed"] is False


async def test_options_direct_multileg_and_request_rules(client, potheri, ops_headers):
    await cancel(client, ops_headers)
    tok, pax = await claim_persona(client, "student-beach")            # destination Chennai Beach
    h = bearer(tok)
    opts = (await client.get(f"{API}/me/options", headers=h)).json()
    items = opts["items"]
    assert items and all(i["request_service_id"] for i in items)
    direct = [i for i in items if not i["is_multi_leg"]]
    multi = [i for i in items if i["is_multi_leg"]]
    assert direct and multi
    assert all(len(i["legs"]) == 1 and i["transfers"] == 0 for i in direct)
    m = multi[0]
    assert len(m["legs"]) == 2 and m["transfers"] == 1
    assert m["legs"][1]["depart_at"] >= m["legs"][0]["arrive_at"]
    etas = [i["eta_at"] for i in items]
    assert etas == sorted(etas)
    assert opts["batch"]["status"] == "open"
    # request validation
    assert (await client.post(f"{API}/me/request", json={"any_fastest": False}, headers=h)).status_code == 422
    assert (await client.post(f"{API}/me/request", json={"choice1_service_id": 999999}, headers=h)).status_code == 422
    c1, c2 = items[0]["request_service_id"], items[1]["request_service_id"]
    r = await client.post(f"{API}/me/request", json={"choice1_service_id": c1, "choice2_service_id": c2}, headers=h)
    assert r.status_code == 200, r.text
    req1 = r.json()
    assert (await client.get(f"{API}/me", headers=h)).json()["state"] == "REQUESTED"
    # re-submitting while the batch is open replaces the request (idempotent per passenger per batch)
    r = await client.post(f"{API}/me/request", json={"choice1_service_id": c2, "any_fastest": True}, headers=h)
    assert r.status_code == 200 and r.json()["id"] == req1["id"] and r.json()["choice1_service_id"] == c2
    assert await count(Request, Request.passenger_id == pax["id"]) == 1


async def test_wheelchair_only_sees_accessible_and_late_request_opens_new_batch(client, potheri, ops_headers):
    tok, _ = await claim_persona(client, "wheelchair-guindy")
    await cancel(client, ops_headers)
    h = bearer(tok)
    for o in (await client.get(f"{API}/me/options", headers=h)).json()["items"]:
        assert o["accessible"] and o["accessible_seats_left"] >= 0
    # close the open batch, then a late arrival opens a new one
    assert (await client.post(f"{API}/ops/batches/current/close", headers=ops_headers)).json()["status"] == "closed"
    cur = (await client.get(f"{API}/ops/batches/current", headers=ops_headers)).json()
    assert cur["batch"]["status"] == "closed"
    c1 = (await client.get(f"{API}/me/options", headers=h)).json()["items"][0]["request_service_id"]
    r = await client.post(f"{API}/me/request", json={"choice1_service_id": c1}, headers=h)
    assert r.status_code == 200 and r.json()["batch"]["status"] == "open"
    assert await count(Batch, Batch.status == "open") == 1
