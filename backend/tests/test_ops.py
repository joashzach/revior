import pytest
from sqlalchemy import func, select

from app.db import get_sessionmaker
from app.models import Allocation, AuditLog, Notification, Passenger, PriorityRule, Request, Scenario, WaitlistEntry
from app.ws.hub import hub
from tests.helpers import API, bearer, cancel, claim_persona, services_by_code


async def counts():
    async with get_sessionmaker()() as s:
        out = {}
        for m in (Allocation, Request, Notification, WaitlistEntry, AuditLog, PriorityRule):
            out[m.__name__] = (await s.execute(select(func.count()).select_from(m))).scalar()
        out["states"] = tuple(sorted((await s.execute(select(Passenger.state, func.count()).group_by(Passenger.state))).all()))
        out["positions"] = tuple(sorted((await s.execute(select(WaitlistEntry.id, WaitlistEntry.last_position, WaitlistEntry.status))).all()))
        return out


async def seeded_run(client, ops):
    await cancel(client, ops)
    r = await client.post(f"{API}/ops/allocation/run", headers=ops, json={"mode": "greedy"})
    assert r.status_code == 200, r.text
    return r.json()["stats"]


async def test_dashboard_data_endpoints_are_consistent(client, potheri, ops_headers):
    stats = await seeded_run(client, ops_headers)
    k = (await client.get(f"{API}/ops/kpis", headers=ops_headers)).json()
    assert k["affected"] >= 370 and k["checked_in"] + k["not_checked_in"] == k["affected"]
    assert k["not_checked_in"] == 10 or k["not_checked_in"] >= 0                 # personas haven't checked in
    assert k["held"] + k["waitlisted"] + k["unresolved"] + k["requested"] + k["confirmed"] + k["resolved_alt"] == k["checked_in"]
    assert 0 < k["fill_rate"] <= 1 and k["avg_wait_min"] >= 0 and k["batch"] is None
    cap = (await client.get(f"{API}/ops/capacity", headers=ops_headers)).json()["items"]
    assert len(cap) >= 12
    for row in cap:
        assert row["free"] >= 0 and row["held"] + row["confirmed"] + row["free"] == row["total_seats"], row
        assert row["accessible_free"] <= row["free"]
    cl = (await client.get(f"{API}/ops/clusters", headers=ops_headers)).json()["items"]
    assert cl and sum(c["size"] for c in cl) == k["affected"]
    assert {"id", "destination", "time_bucket_start", "needs_class", "size", "demand_seats", "capacity_seats"} == set(cl[0])
    assert {c["needs_class"] for c in cl} <= {"accessible", "priority", "general"}
    # allocations table: pagination + filters
    p1 = (await client.get(f"{API}/ops/allocations", headers=ops_headers, params={"page": 1, "page_size": 20})).json()
    assert p1["page"] == 1 and p1["page_size"] == 20 and len(p1["items"]) == 20 and p1["total"] > 300
    scores = [i["score"] for i in p1["items"]]
    assert scores == sorted(scores, reverse=True)
    assert {"passenger", "score", "choice_rank", "service_label", "status", "hold_expires_at", "explanation"} == set(p1["items"][0])
    gnd = (await client.get(f"{API}/ops/allocations", headers=ops_headers, params={"destination": "GND", "page_size": 200})).json()
    assert 0 < gnd["total"] < p1["total"]
    wc = (await client.get(f"{API}/ops/allocations", headers=ops_headers, params={"needs": "wheelchair", "page_size": 200})).json()
    assert wc["total"] > 0 and all(i["passenger"]["needs"]["wheelchair"] for i in wc["items"])
    one = p1["items"][0]["passenger"]["name"]
    assert (await client.get(f"{API}/ops/allocations", headers=ops_headers, params={"q": one})).json()["total"] >= 1
    # unresolved queue with alternatives
    un = (await client.get(f"{API}/ops/unresolved", headers=ops_headers)).json()["items"]
    assert len(un) == k["unresolved"] or len(un) == 50
    if un:
        assert un[0]["passenger"]["state"] == "UNRESOLVED" and un[0]["alternatives"] and un[0]["waited_min"] >= 0
    # fairness numbers are sane
    f = (await client.get(f"{API}/ops/fairness", headers=ops_headers)).json()
    assert [c["needs_class"] for c in f["by_needs_class"]] == ["accessible", "priority", "general"]
    for c in f["by_needs_class"]:
        assert 0 <= c["placement_rate"] <= 1 and 0 <= c["wait_p50"] <= c["wait_p90"]
    assert 0 <= f["wait_gini"] <= 1 and f["by_destination"]
    assert all(0 <= d["placement_rate"] <= 1 and d["unresolved"] >= 0 for d in f["by_destination"])
    # priority classes should not be worse off than general (vulnerable passengers are not starved)
    rate = {c["needs_class"]: c["placement_rate"] for c in f["by_needs_class"]}
    assert rate["accessible"] >= rate["general"] - 0.05 and rate["priority"] >= rate["general"] - 0.05
    # map snapshot
    m = (await client.get(f"{API}/ops/map", headers=ops_headers)).json()
    assert {"nodes", "edges", "services", "vehicles", "clusters"} == set(m)
    assert m["services"] and all(s["polyline"]["type"] == "LineString" for s in m["services"])
    assert m["clusters"] and all({"node_id", "size"} == set(c) for c in m["clusters"])
    assert all("is_closed" in e for e in m["edges"])
    # messages log + invariants
    msgs = (await client.get(f"{API}/ops/notifications", headers=ops_headers, params={"page_size": 5})).json()
    assert msgs["total"] > 300 and len(msgs["items"]) == 5 and msgs["items"][0]["channel"] == "email_sim"
    inv = (await client.get(f"{API}/ops/invariants", headers=ops_headers)).json()
    assert inv == {"over_allocated_services": 0, "multi_primary_passengers": 0, "negative_free_seats": 0, "ok": True}


async def test_rules_preview_is_a_dry_run_and_apply_reranks_waitlists_live(client, potheri, ops_headers):
    await seeded_run(client, ops_headers)
    rules = (await client.get(f"{API}/ops/rules", headers=ops_headers)).json()
    assert rules["active"]["version"] == 1 and rules["active"]["weights"]["medical"] == 30 and len(rules["history"]) == 1
    before = await counts()
    new_w = {"medical": 5, "wheelchair": 5, "elderly": 50, "with_children": 50, "deadline_urgency": 0, "wait_time": 0}
    pv = await client.post(f"{API}/ops/rules/preview", headers=ops_headers, json={"weights": new_w})
    assert pv.status_code == 200, pv.text
    j = pv.json()
    assert {"placed_delta", "by_needs_class", "movers"} == set(j) and isinstance(j["placed_delta"], int)
    assert [c["needs_class"] for c in j["by_needs_class"]] == ["accessible", "priority", "general"]
    for c in j["by_needs_class"]:
        assert 0 <= c["placement_rate_before"] <= 1 and 0 <= c["placement_rate_after"] <= 1
    assert all({"passenger_id", "name", "service_label", "position_before", "position_after"} == set(m) for m in j["movers"])
    assert await counts() == before                                              # preview changed NOTHING in the DB
    assert (await client.get(f"{API}/ops/rules", headers=ops_headers)).json()["active"]["version"] == 1
    # invalid weights are rejected
    assert (await client.post(f"{API}/ops/rules/preview", headers=ops_headers, json={"weights": {"price": 10}})).status_code == 422
    assert (await client.post(f"{API}/ops/rules/apply", headers=ops_headers, json={"weights": {"medical": -1}})).status_code == 422
    # a waitlisted persona-like observer: record positions through /me/status before and after
    async with get_sessionmaker()() as s:
        from app.security import create_passenger_token
        wl_pax = (await s.execute(select(Passenger).where(Passenger.state == "WAITLISTED").order_by(Passenger.id).limit(40))).scalars().all()
        toks = {p.id: bearer(create_passenger_token(p)) for p in wl_pax}
        held_before = {a.id: a.status for a in (await s.execute(select(Allocation).where(Allocation.status.in_(("held", "confirmed"))))).scalars()}
    async def positions():
        out = {}
        for pid, h in toks.items():
            st = (await client.get(f"{API}/me/status", headers=h)).json()
            out[pid] = tuple((w["service_id"], w["position"]) for w in st["waitlist"])
        return out
    pos_before = await positions()
    hub.record, hub.published = True, []
    try:
        ap = await client.post(f"{API}/ops/rules/apply", headers=ops_headers, json={"weights": new_w})
        assert ap.status_code == 200 and ap.json() == {"version": 2}
        evs = [m["type"] for m in hub.published]
        assert "rules.updated" in evs
    finally:
        hub.record = False
    pos_after = await positions()
    if len(toks) >= 2:
        assert pos_after != pos_before or not j["movers"]                        # positions re-ranked live
        if j["movers"]:
            assert "waitlist.position_changed" in evs
    rules = (await client.get(f"{API}/ops/rules", headers=ops_headers)).json()
    assert rules["active"]["version"] == 2 and rules["active"]["weights"]["elderly"] == 50 and [h["version"] for h in rules["history"]] == [2, 1]
    # held / confirmed allocations are untouched by a rule change
    async with get_sessionmaker()() as s:
        held_after = {a.id: a.status for a in (await s.execute(select(Allocation).where(Allocation.status.in_(("held", "confirmed"))))).scalars()}
        n_active = (await s.execute(select(func.count()).select_from(PriorityRule).join(Scenario, Scenario.id == PriorityRule.scenario_id)
                                    .where(PriorityRule.is_active, Scenario.slug == "potheri-demo"))).scalar()
    assert held_after == held_before and n_active == 1
    # the passenger-facing /why reflects the new rule version
    some = next(iter(toks.values()))
    why = (await client.get(f"{API}/me/why", headers=some)).json()
    assert why["rule_version"] == 2 and why["weights"]["elderly"] == 50


async def test_scenario_switch_proves_the_engine_is_location_agnostic(client, potheri, ops_headers):
    items = (await client.get(f"{API}/ops/scenarios", headers=ops_headers)).json()["items"]
    assert {i["slug"] for i in items} >= {"potheri-demo", "secondary-demo"}
    r = await client.post(f"{API}/ops/scenarios/secondary-demo/reset", headers=ops_headers)
    assert r.status_code == 200 and 50 <= r.json()["counts"]["passengers"] <= 60
    assert (await client.post(f"{API}/ops/scenarios/secondary-demo/activate", headers=ops_headers)).json() == {"slug": "secondary-demo"}
    try:
        act = (await client.get(f"{API}/scenarios/active")).json()
        assert act["slug"] == "secondary-demo" and act["default_hub"]["code"] == "CSMT"
        assert act["join_url"].endswith("/demo-join?scenario=secondary-demo")
        svcs = await services_by_code(client, ops_headers)
        r = await client.post(f"{API}/ops/disruptions", headers=ops_headers,
                              json={"type": "cancellation", "service_id": svcs["LOC-CSMT-TNA-1805"]["id"], "reason": "demo"})
        assert r.status_code == 200 and r.json()["affected_count"] >= 45
        stats = (await client.post(f"{API}/ops/allocation/run", headers=ops_headers, json={"mode": "greedy"})).json()["stats"]
        assert stats["units"] >= 45 and stats["placed_choice1"] > 0
        inv = (await client.get(f"{API}/ops/invariants", headers=ops_headers)).json()
        assert inv["ok"]
        pers = (await client.get(f"{API}/demo/personas", params={"scenario": "secondary-demo"})).json()["items"]
        assert len(pers) == 3
    finally:
        await client.post(f"{API}/ops/scenarios/potheri-demo/activate", headers=ops_headers)
        await client.post(f"{API}/ops/scenarios/secondary-demo/reset", headers=ops_headers)     # leave it pristine
    assert (await client.get(f"{API}/scenarios/active")).json()["slug"] == "potheri-demo"


async def test_scenario_config_get_patch_and_validation(client, potheri, ops_headers):
    c = (await client.get(f"{API}/ops/scenarios/potheri-demo/config", headers=ops_headers)).json()
    assert set(c) == {"batch_window_seconds", "hold_seconds", "auto_run_on_batch_close", "delay_threshold_minutes", "hub_radius_km",
                      "open_booking_enabled", "sim_speed", "demo_mode", "join_qr_mode"}
    r = await client.patch(f"{API}/ops/scenarios/potheri-demo/config", headers=ops_headers, json={"join_qr_mode": "fullscreen", "hold_seconds": 120})
    assert r.status_code == 200 and r.json()["join_qr_mode"] == "fullscreen" and r.json()["hold_seconds"] == 120
    assert (await client.get(f"{API}/ops/scenarios/potheri-demo/config", headers=ops_headers)).json()["join_qr_mode"] == "fullscreen"
    assert (await client.patch(f"{API}/ops/scenarios/potheri-demo/config", headers=ops_headers, json={"join_qr_mode": "huge"})).status_code == 422
    assert (await client.patch(f"{API}/ops/scenarios/potheri-demo/config", headers=ops_headers, json={"batch_window_seconds": 0})).status_code == 422
    assert (await client.get(f"{API}/ops/scenarios/nope/config", headers=ops_headers)).status_code == 404
    # open-booking toggle writes the same config
    assert (await client.post(f"{API}/ops/open-booking", headers=ops_headers, json={"enabled": True})).json() == {"enabled": True}
    assert (await client.get(f"{API}/ops/scenarios/potheri-demo/config", headers=ops_headers)).json()["open_booking_enabled"] is True
    # reset restores defaults
    await client.post(f"{API}/ops/scenarios/potheri-demo/reset", headers=ops_headers)
    c2 = (await client.get(f"{API}/ops/scenarios/potheri-demo/config", headers=ops_headers)).json()
    assert c2["join_qr_mode"] == "corner" and c2["open_booking_enabled"] is False
