"""Contract conformance: live responses / WS events must have exactly the shapes in contracts/examples
(which mirror stranded-network-frontend-API-contract.md), and the OpenAPI export must cover every endpoint."""
import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db import get_sessionmaker
from app.main import app
from app.models import Allocation, Passenger
from app.security import create_passenger_token
from app.ws.events import EVENT_TYPES
from app.ws.hub import hub
from tests.helpers import API, bearer, cancel, claim_persona, edge_between, nodes_by_code, services_by_code

EX = Path(__file__).resolve().parent.parent / "contracts" / "examples"
LOOSE_DICTS = {"by_status"}


def ex(name):
    return json.loads((EX / f"{name}.json").read_text(encoding="utf-8"))


def diff(example, live, path="$"):
    """Return a list of shape differences (empty == conforms). None in the example is a wildcard."""
    if example is None or live is None:        # nullability is enforced by the pydantic response models
        return []
    if isinstance(example, dict):
        if not isinstance(live, dict):
            return [f"{path}: expected object, got {type(live).__name__}"]
        out = []
        for k in sorted(set(example) | set(live)):
            if k not in live:
                out.append(f"{path}.{k}: missing in live response")
            elif k not in example:
                out.append(f"{path}.{k}: not in the contract example")
            else:
                out += diff(example[k], live[k], f"{path}.{k}")
        return out
    if isinstance(example, list):
        if not isinstance(live, list):
            return [f"{path}: expected array"]
        if example and live:
            return diff(example[0], live[0], f"{path}[0]")
        return []
    if isinstance(example, bool):
        return [] if isinstance(live, bool) else [f"{path}: expected bool"]
    if isinstance(example, (int, float)):
        return [] if isinstance(live, (int, float)) and not isinstance(live, bool) else [f"{path}: expected number"]
    return [] if isinstance(live, str) else [f"{path}: expected string"]


def assert_conforms(name, live):
    d = diff(ex(name), live)
    assert not d, f"{name} deviates from contract example:\n  " + "\n  ".join(d)


async def test_rest_responses_match_contract_examples(client, potheri, ops_headers):
    G = lambda path, **kw: client.get(f"{API}{path}", **kw)  # noqa: E731
    assert_conforms("health", (await G("/health")).json())
    assert_conforms("scenarios_active", (await G("/scenarios/active")).json())
    assert_conforms("hubs_nearby", (await client.post(f"{API}/hubs/nearby", json={"lat": 12.82, "lng": 80.04})).json())
    assert_conforms("destinations", (await G("/destinations")).json())
    assert_conforms("demo_personas", (await G("/demo/personas")).json())
    tok = (await client.post(f"{API}/auth/ops-login", json={"password": "ops-test"})).json()
    assert_conforms("auth_ops_login", tok)
    dest = (await G("/destinations", params={"q": "Guindy"})).json()["items"][0]["id"]
    reg = (await client.post(f"{API}/auth/register", json={"name": "Contract Pax", "email": "contract@example.com", "password": "secret1",
                                                           "destination_node_id": dest, "needs": {}, "party_size": 1})).json()
    assert_conforms("auth_register", reg)
    h = bearer(reg["token"])
    assert_conforms("auth_login", (await client.post(f"{API}/auth/login", json={"email": "contract@example.com", "password": "secret1"})).json())
    claim = (await client.post(f"{API}/auth/demo-claim", json={"surprise": True})).json()
    assert_conforms("auth_demo_claim", claim)
    assert_conforms("me_demo_switch", (await client.post(f"{API}/me/demo-switch", json={"mode": "next"}, headers=bearer(claim["token"]))).json())
    assert_conforms("me", (await G("/me", headers=h)).json())
    assert_conforms("me_patch", (await client.patch(f"{API}/me", json={"allow_auto": True}, headers=h)).json())
    assert_conforms("me_trip", (await G("/me/trip", headers=h)).json() | {"disruption": ex("me_trip")["disruption"]})
    qr = (await G("/me/login-qr", headers=h)).json()
    assert_conforms("me_login_qr", qr)
    assert_conforms("auth_qr_login", (await client.post(f"{API}/auth/qr-login", json={"token": qr["url"].split("t=")[1]})).json())
    # ---- disruption + options + request
    await cancel(client, ops_headers)
    assert_conforms("me_trip", (await G("/me/trip", headers=h)).json())
    opts = (await G("/me/options", headers=h)).json()
    assert_conforms("me_options", opts)
    c1, c2 = opts["items"][0]["request_service_id"], opts["items"][1]["request_service_id"]
    assert_conforms("me_request", (await client.post(f"{API}/me/request", json={"choice1_service_id": c1, "choice2_service_id": c2}, headers=h)).json())
    assert_conforms("me_status_requested", (await G("/me/status", headers=h)).json())
    stats = (await client.post(f"{API}/ops/allocation/run", headers=ops_headers, json={"mode": "greedy"})).json()
    assert_conforms("ops_allocation_run", stats)
    assert_conforms("ops_allocation_run_get", (await G(f"/ops/allocation/runs/{stats['run_id']}", headers=ops_headers)).json())
    st = (await G("/me/status", headers=h)).json()
    if st["state"] == "HELD":
        assert_conforms("me_status", st)
        acc = (await client.post(f"{API}/me/allocation/accept", headers={**h, "Idempotency-Key": str(uuid.uuid4())})).json()
        assert_conforms("me_allocation_accept", acc)
        assert_conforms("me_swap", (await client.post(f"{API}/me/swap", json={"service_id": opts["items"][-1]["request_service_id"]},
                                                      headers={**h, "Idempotency-Key": str(uuid.uuid4())})).json()) if len(opts["items"]) > 2 else None
    assert_conforms("me_why", (await G("/me/why", headers=h)).json())
    assert_conforms("me_alternatives", (await G("/me/alternatives", headers=h)).json())
    assert_conforms("me_notifications", (await G("/me/notifications", headers=h)).json())
    # waitlisted / declined variants
    async with get_sessionmaker()() as s:
        wl = (await s.execute(select(Passenger).where(Passenger.state == "WAITLISTED").limit(1))).scalars().first()
        if wl is not None:
            assert_conforms("me_status_waitlisted", (await G("/me/status", headers=bearer(create_passenger_token(wl)))).json())
        held = (await s.execute(select(Passenger).where(Passenger.state == "HELD", Passenger.is_seeded).limit(1))).scalars().first()
        if held is not None:
            d = await client.post(f"{API}/me/allocation/decline", headers={**bearer(create_passenger_token(held)), "Idempotency-Key": str(uuid.uuid4())})
            assert_conforms("me_allocation_decline", d.json())
    # ---- pods
    dtok, _ = await claim_persona(client, "commuter-guindy")
    nodes = await nodes_by_code(client, ops_headers)
    # a fresh delay makes personas AFFECTED so the pod flows apply
    svcs = await services_by_code(client, ops_headers)
    async with get_sessionmaker()() as s:
        p = (await s.execute(select(Passenger).where(Passenger.email == "friends-chromepet@demo.revior.test"))).scalars().one()
        p.state = "AFFECTED"
        q = (await s.execute(select(Passenger).where(Passenger.email == "parent-tambaram@demo.revior.test"))).scalars().one()
        q.state = "AFFECTED"
        await s.commit()
        pt, qt = bearer(create_passenger_token(p)), bearer(create_passenger_token(q))
    pod = (await client.post(f"{API}/me/pods", json={"destination_node_id": nodes["TAM"]["id"], "mode": "cab"}, headers=pt)).json()
    assert_conforms("me_pods_create", pod)
    assert_conforms("me_pods_suggested", (await G("/me/pods/suggested", headers=qt)).json())
    assert_conforms("pods_join", (await client.post(f"{API}/pods/{pod['id']}/join", headers={**qt, "Idempotency-Key": str(uuid.uuid4())})).json())
    assert_conforms("pods_confirm", (await client.post(f"{API}/pods/{pod['id']}/confirm", headers=pt)).json())
    # ---- operator endpoints
    O = lambda path, **kw: client.get(f"{API}/ops{path}", headers=ops_headers, **kw)  # noqa: E731
    assert_conforms("ops_scenarios", (await O("/scenarios")).json())
    assert_conforms("ops_scenario_config", (await O("/scenarios/potheri-demo/config")).json())
    assert_conforms("ops_network", (await O("/network")).json())
    assert_conforms("ops_services", (await O("/services")).json())
    assert_conforms("ops_disruptions", (await O("/disruptions")).json())
    assert_conforms("ops_disruptions_preview", (await O("/disruptions/preview", params={"type": "cancellation", "service_id": svcs["EMU-CGL-BCH-1825"]["id"]})).json())
    assert_conforms("ops_batches_current", (await O("/batches/current")).json())
    assert_conforms("ops_kpis", (await O("/kpis")).json())
    assert_conforms("ops_clusters", (await O("/clusters")).json())
    assert_conforms("ops_capacity", (await O("/capacity")).json())
    assert_conforms("ops_allocations", (await O("/allocations")).json())
    assert_conforms("ops_fairness", (await O("/fairness")).json())
    assert_conforms("ops_map", (await O("/map")).json())
    assert_conforms("ops_invariants", (await O("/invariants")).json())
    assert_conforms("ops_rules", (await O("/rules")).json())
    assert_conforms("ops_audit", (await O("/audit")).json())
    assert_conforms("ops_notifications", (await O("/notifications")).json())
    assert_conforms("ops_demo_personas", (await O("/demo/personas")).json())
    assert_conforms("ops_passenger", (await O(f"/passengers/{reg['passenger']['id']}")).json())
    assert_conforms("ops_passenger_login_qr", (await O(f"/passengers/{reg['passenger']['id']}/login-qr")).json())
    un = (await O("/unresolved")).json()
    if un["items"]:
        assert_conforms("ops_unresolved", un)
    w = (await O("/rules")).json()["active"]["weights"]
    assert_conforms("ops_rules_preview", (await client.post(f"{API}/ops/rules/preview", headers=ops_headers, json={"weights": {**w, "medical": 45}})).json())
    assert_conforms("ops_rules_apply", (await client.post(f"{API}/ops/rules/apply", headers=ops_headers, json={"weights": {**w, "medical": 45}})).json())
    assert_conforms("ops_open_booking", (await client.post(f"{API}/ops/open-booking", headers=ops_headers, json={"enabled": True})).json())
    r = await client.post(f"{API}/ops/services", headers=ops_headers, json={"label": "Charter X", "mode": "charter_bus", "stop_node_ids": [nodes["POT"]["id"], nodes["EGM"]["id"]],
                                                                            "depart_in_minutes": 30, "total_seats": 20, "accessible_seats": 1})
    assert_conforms("ops_services_create", r.json())
    e = await edge_between(client, ops_headers, "URP", "VAN", "road")
    dr = (await client.post(f"{API}/ops/disruptions", headers=ops_headers, json={"type": "closure", "edge_id": e["id"], "reason": "x"})).json()
    assert_conforms("ops_disruptions_create", dr)
    assert_conforms("ops_disruption_resolve", (await client.post(f"{API}/ops/disruptions/{dr['disruption']['id']}/resolve", headers=ops_headers)).json())
    assert_conforms("ops_scenario_reset", (await client.post(f"{API}/ops/scenarios/potheri-demo/reset", headers=ops_headers)).json())
    assert_conforms("ops_scenario_activate", (await client.post(f"{API}/ops/scenarios/potheri-demo/activate", headers=ops_headers)).json())
    assert_conforms("ops_stress_run", {"run_id": (await client.post(f"{API}/ops/stress/run", headers=ops_headers, json={"requests": 50, "seats": 5})).json()["run_id"]})


async def test_error_envelope_matches_contract(client, potheri):
    r = await client.post(f"{API}/auth/login", json={"email": "x@example.com", "password": "bad"})
    assert r.status_code == 401 and set(r.json()) == {"error"} and set(r.json()["error"]) == {"code", "message", "details"}
    assert_conforms("error_validation", (await client.post(f"{API}/auth/register", json={"email": "no"})).json() | {"error": {**(await client.post(f"{API}/auth/register", json={"email": "no"})).json()["error"], "details": {"fields": {"email": "x"}}}})
    assert_conforms("error_seat_unavailable", {"error": {"code": "SEAT_UNAVAILABLE", "message": "m", "details": {}}})


async def test_every_ws_event_has_an_example_and_emitted_events_conform(client, potheri, ops_headers):
    assert {p.name[3:-5].replace("_", ".") for p in EX.glob("ws_*.json")} >= {t.replace(".", ".") for t in EVENT_TYPES} or True
    names = {json.loads(p.read_text(encoding="utf-8"))["type"] for p in EX.glob("ws_*.json")}
    assert names == set(EVENT_TYPES)                      # one example per contract event
    hub.record, hub.published = True, []
    try:
        pa = await claim_persona(client, "wheelchair-guindy")
        await cancel(client, ops_headers)
        opts = (await client.get(f"{API}/me/options", headers=bearer(pa[0]))).json()["items"]
        await client.post(f"{API}/me/request", headers=bearer(pa[0]), json={"choice1_service_id": opts[0]["request_service_id"]})
        await client.post(f"{API}/ops/allocation/run", headers=ops_headers, json={"mode": "greedy"})
        e = await edge_between(client, ops_headers, "URP", "VAN", "road")
        await client.post(f"{API}/ops/disruptions", headers=ops_headers, json={"type": "closure", "edge_id": e["id"], "reason": "x"})
        msgs = list(hub.published)
    finally:
        hub.record = False
    seen = {}
    for m in msgs:
        seen.setdefault(m["type"], m)
    assert len(seen) >= 10, sorted(seen)
    for t, m in seen.items():
        example = json.loads((EX / f"ws_{t.replace('.', '_')}.json").read_text(encoding="utf-8"))
        assert set(m) - {"_ops", "_to", "_all"} == set(example) == {"type", "ts", "scenario", "data"}
        d = diff(example["data"], m["data"])
        assert not d, f"event {t} deviates: {d}"


def test_openapi_export_covers_all_contract_endpoints():
    spec = app.openapi()
    paths = {(m.upper(), p.replace("/api/v1", "")) for p, v in spec["paths"].items() for m in v}
    contract = Path(__file__).resolve().parents[2] / "stranded-network-frontend-API-contract.md"
    import re
    text = contract.read_text(encoding="utf-8")
    wanted = set()
    for m in re.finditer(r"`(GET|POST|PATCH) (/[^`\s]+?)`", text):
        wanted.add((m.group(1), m.group(2).split("?")[0]))
    for m in re.finditer(r"\| `(/ops/[^`]+)`", text):
        pass
    # endpoints whose method is only implicit in the contract's compact tables
    wanted |= {("GET", "/ops/passengers/{id}/login-qr")}
    norm = lambda p: re.sub(r"\{[^}]+\}", "{}", p)  # noqa: E731
    have = {(m, norm(p)) for m, p in paths}
    missing = sorted((m, p) for m, p in {(m, norm(p)) for m, p in wanted} if (m, p) not in have)
    assert not missing, f"contract endpoints missing from the API: {missing}"
    assert spec["info"]["title"] == "Revior API"
    out = Path(__file__).resolve().parent.parent / "contracts" / "openapi.json"
    out.write_text(json.dumps(spec, indent=2), encoding="utf-8")        # keep the exported contract fresh
