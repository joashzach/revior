import asyncio
import uuid

import pytest

from app.domain.state import can, transition
from app.errors import AppError
from app.models import Passenger
from app.security import auth_limiter, register_limiter
from tests.helpers import post_retry

API = "/api/v1"


@pytest.fixture(autouse=True)
def _reset_limiters():
    register_limiter.reset()
    auth_limiter.reset()


async def _dest(client, code="TAM", hub=None):
    r = await client.get(f"{API}/destinations", params={"q": code})
    assert r.status_code == 200, r.text
    return r.json()["items"][0]["id"]


def bearer(tok):
    return {"Authorization": f"Bearer {tok}"}


async def register(client, email="a@example.com", dest_code="TAM", **kw):
    body = {"name": "Test Pax", "email": email, "password": "secret1", "destination_node_id": await _dest(client, dest_code),
            "needs": {}, "party_size": 1, **kw}
    return await client.post(f"{API}/auth/register", json=body)


async def test_register_trip_on_featured_service(client, potheri):
    r = await register(client)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["ticket"]["ticket_id"].startswith("VT-")
    assert j["ticket"]["service"]["code"] == "EMU-CGL-BCH-1810"
    assert j["passenger"]["state"] == "BOOKED" and j["passenger"]["hub"]["code"] == "POT"
    trip = await client.get(f"{API}/me/trip", headers=bearer(j["token"]))
    assert trip.status_code == 200
    t = trip.json()
    assert t["ticket"]["service"]["code"] == "EMU-CGL-BCH-1810" and t["disruption"] is None
    assert t["headline"].startswith("On time")


async def test_register_validation_and_duplicates(client, potheri):
    assert (await register(client, "dup@example.com")).status_code == 200
    r = await register(client, "DUP@example.com")
    assert r.status_code == 409 and r.json()["error"]["code"] == "EMAIL_TAKEN"
    r = await client.post(f"{API}/auth/register", json={"name": "x", "email": "bad", "password": "123", "destination_node_id": 1})
    assert r.status_code == 422
    e = r.json()["error"]
    assert e["code"] == "VALIDATION_ERROR" and "email" in e["details"]["fields"] and "password" in e["details"]["fields"]
    r = await register(client, "far@example.com", party_size=9)
    assert r.status_code == 422


async def test_login_and_logout_invalidates_token(client, potheri):
    reg = (await register(client, "login@example.com")).json()
    r = await client.post(f"{API}/auth/login", json={"email": "login@example.com", "password": "nope"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_CREDENTIALS"
    r = await client.post(f"{API}/auth/login", json={"email": "nobody@example.com", "password": "nope"})
    assert r.json()["error"]["code"] == "INVALID_CREDENTIALS"
    r = await client.post(f"{API}/auth/login", json={"email": "LOGIN@example.com", "password": "secret1"})
    assert r.status_code == 200
    tok = r.json()["token"]
    assert (await client.get(f"{API}/me", headers=bearer(tok))).status_code == 200
    assert (await client.post(f"{API}/auth/logout", headers=bearer(tok))).status_code == 204
    # token_version bumped: both the old registration token and the login token are dead
    for t in (tok, reg["token"]):
        r = await client.get(f"{API}/me", headers=bearer(t))
        assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHORIZED"


async def test_roles_are_enforced(client, potheri, ops_headers):
    tok = (await register(client, "role@example.com")).json()["token"]
    assert (await client.get(f"{API}/ops/scenarios", headers=bearer(tok))).status_code == 403
    assert (await client.get(f"{API}/me", headers=ops_headers)).status_code == 403
    assert (await client.get(f"{API}/me")).status_code == 401
    assert (await client.get(f"{API}/ops/scenarios")).status_code == 401
    r = await client.post(f"{API}/auth/ops-login", json={"password": "wrong"})
    assert r.status_code == 401


async def test_login_qr_roundtrip_and_revocation(client, potheri, ops_headers):
    reg = (await register(client, "qr@example.com")).json()
    r = await client.get(f"{API}/me/login-qr", headers=bearer(reg["token"]))
    assert r.status_code == 200
    url = r.json()["url"]
    assert "/qr-login?t=" in url
    raw = url.split("t=")[1]
    ok = await client.post(f"{API}/auth/qr-login", json={"token": raw})
    assert ok.status_code == 200 and ok.json()["passenger"]["email"] == "qr@example.com"
    assert (await client.get(f"{API}/me", headers=bearer(ok.json()["token"]))).status_code == 200
    # a fresh QR revokes the previous one
    url2 = (await client.get(f"{API}/me/login-qr", headers=bearer(reg["token"]))).json()["url"]
    bad = await client.post(f"{API}/auth/qr-login", json={"token": raw})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "QR_TOKEN_INVALID"
    assert (await client.post(f"{API}/auth/qr-login", json={"token": url2.split("t=")[1]})).status_code == 200
    # tokens are stored hashed
    from sqlalchemy import select
    from app.db import get_sessionmaker
    from app.models import LoginToken
    async with get_sessionmaker()() as s:
        hashes = [t.token_hash for t in (await s.execute(select(LoginToken))).scalars()]
    assert raw not in hashes and all(len(h) == 64 for h in hashes)
    # operator can mint a QR for any passenger
    pid = reg["passenger"]["id"]
    r = await client.get(f"{API}/ops/passengers/{pid}/login-qr", headers=ops_headers)
    assert r.status_code == 200 and "qr-login" in r.json()["url"]
    assert (await client.post(f"{API}/auth/qr-login", json={"token": "garbage"})).json()["error"]["code"] == "QR_TOKEN_INVALID"


async def test_hub_nearby_radius_and_default_fallback(client, potheri):
    # near Kattankulathur: hubs within 10 km, nearest first, Potheri pre-selected
    r = await client.post(f"{API}/hubs/nearby", json={"lat": 12.8056, "lng": 80.0266})   # OSM-verified Kattankulathur
    j = r.json()
    codes = [h["hub"]["code"] for h in j["hubs"]]
    assert j["reason"] == "nearest" and codes[0] == "KTM" and "POT" in codes and "CGL" not in codes
    assert j["selected_hub_id"] == next(h["hub"]["id"] for h in j["hubs"] if h["hub"]["code"] == "POT")
    dists = [h["distance_km"] for h in j["hubs"]]
    assert dists == sorted(dists)
    # far away (Delhi) -> default only
    j = (await client.post(f"{API}/hubs/nearby", json={"lat": 28.6, "lng": 77.2})).json()
    assert j["reason"] == "default" and len(j["hubs"]) == 1 and j["hubs"][0]["hub"]["code"] == "POT"
    assert j["hubs"][0]["distance_km"] is None
    # no coordinates (location denied)
    j = (await client.post(f"{API}/hubs/nearby", json={})).json()
    assert j["reason"] == "default" and j["hubs"][0]["is_default"] is True


async def test_destinations_search(client, potheri):
    items = (await client.get(f"{API}/destinations", params={"hub": "POT"})).json()["items"]
    names = {i["name"] for i in items}
    assert {"Tambaram", "Guindy", "Chennai Beach"} <= names and "Potheri" not in names
    items = (await client.get(f"{API}/destinations", params={"q": "tam"})).json()["items"]
    assert [i["name"] for i in items] == ["Tambaram"]


async def test_demo_personas_claim_atomic_and_switch(client, potheri, ops_headers):
    items = (await client.get(f"{API}/demo/personas")).json()["items"]
    assert len(items) == 10 and not any(i["is_taken"] for i in items)
    pid = items[0]["id"]
    # two judges tap the same persona at once -> exactly one wins, the other PERSONA_TAKEN
    rs = await asyncio.gather(*[client.post(f"{API}/auth/demo-claim", json={"persona_id": pid}) for _ in range(5)])
    codes = sorted(r.status_code for r in rs)
    assert codes == [200, 409, 409, 409, 409], [r.text for r in rs]
    assert all(r.json()["error"]["code"] == "PERSONA_TAKEN" for r in rs if r.status_code == 409)
    win = next(r for r in rs if r.status_code == 200).json()
    assert win["persona"]["is_taken"] and win["passenger"]["is_demo_persona"]
    assert (await client.get(f"{API}/demo/personas")).json()["items"][0]["is_taken"] is True
    tok = win["token"]
    # switch: old token dies, new token works, old persona is free again
    sw = await client.post(f"{API}/me/demo-switch", json={"mode": "next"}, headers=bearer(tok))
    assert sw.status_code == 200, sw.text
    new = sw.json()
    assert new["passenger"]["id"] != pid
    assert (await client.get(f"{API}/me", headers=bearer(tok))).status_code == 401
    assert (await client.get(f"{API}/me", headers=bearer(new["token"]))).status_code == 200
    taken = {i["id"]: i["is_taken"] for i in (await client.get(f"{API}/demo/personas")).json()["items"]}
    assert taken[pid] is False and taken[new["passenger"]["id"]] is True
    # pick a specific persona
    other = next(i for i in items if i["id"] not in (pid, new["passenger"]["id"]))
    sw = await client.post(f"{API}/me/demo-switch", json={"mode": "pick", "persona_id": other["id"]}, headers=bearer(new["token"]))
    assert sw.status_code == 200 and sw.json()["passenger"]["id"] == other["id"]
    # picking a taken one fails and does not release the caller
    r = await client.post(f"{API}/me/demo-switch", json={"mode": "pick", "persona_id": new["passenger"]["id"] + 0}, headers=bearer(sw.json()["token"]))
    assert r.status_code in (200, 409)
    # operator release -> that phone gets 401
    r = await client.post(f"{API}/ops/demo/personas/{other['id']}/release", headers=ops_headers)
    assert r.status_code == 204
    assert (await client.get(f"{API}/me", headers=bearer(sw.json()["token"]))).status_code == 401
    r = await client.get(f"{API}/ops/demo/personas", headers=ops_headers)
    assert r.status_code == 200 and "claimed_at" in r.json()["items"][0]
    assert (await client.post(f"{API}/ops/demo/personas/release-all", headers=ops_headers)).status_code == 204
    assert not any(i["is_taken"] for i in (await client.get(f"{API}/demo/personas")).json()["items"])


async def test_surprise_autocreates_when_pool_empty(client, potheri):
    for _ in range(10):
        assert (await client.post(f"{API}/auth/demo-claim", json={"surprise": True})).status_code == 200
    r = await client.post(f"{API}/auth/demo-claim", json={"surprise": True})
    assert r.status_code == 200
    assert r.json()["passenger"]["is_demo_persona"] and r.json()["passenger"]["ticket_id"].startswith("VT-")
    assert len((await client.get(f"{API}/demo/personas")).json()["items"]) == 11


async def test_persona_email_login_and_password(client, potheri):
    r = await client.post(f"{API}/auth/login", json={"email": "wheelchair-guindy@demo.revior.test", "password": "revior-demo"})
    assert r.status_code == 200 and r.json()["passenger"]["needs"]["wheelchair"] is True


async def test_rate_limit_on_register(client, potheri):
    from app.config import get_settings
    get_settings().REGISTER_RATE_LIMIT = "3/minute"
    try:
        codes = [(await register(client, f"rl{i}@example.com")).status_code for i in range(5)]
    finally:
        get_settings().REGISTER_RATE_LIMIT = "20/minute"
    assert codes[:3] == [200, 200, 200] and codes[3:] == [429, 429]


async def test_patch_me_only_in_allowed_states(client, potheri):
    reg = (await register(client, "patch@example.com")).json()
    h = bearer(reg["token"])
    gd = await _dest(client, "GND")
    r = await client.patch(f"{API}/me", json={"destination_node_id": gd, "needs": {"elderly": True}}, headers=h)
    assert r.status_code == 200 and r.json()["destination"]["code"] == "GND" and r.json()["needs"]["elderly"]
    async with __import__("app.db", fromlist=["x"]).get_sessionmaker()() as s:
        p = await s.get(Passenger, reg["passenger"]["id"])
        p.state = "HELD"
        await s.commit()
    r = await client.patch(f"{API}/me", json={"party_size": 2}, headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "INVALID_STATE"


def test_state_machine_unit():
    p = Passenger(state="BOOKED")
    assert can("BOOKED", "AFFECTED") and not can("BOOKED", "HELD")
    with pytest.raises(AppError) as e:
        transition(p, "CONFIRMED")
    assert e.value.code == "INVALID_STATE" and e.value.status_code == 409
    assert transition(p, "AFFECTED") is True and p.state == "AFFECTED"
    assert transition(p, "REQUESTED") and transition(p, "HELD") and transition(p, "CONFIRMED")
    assert transition(p, "BOOKED", force=True) and p.state == "BOOKED"


async def test_twenty_parallel_claims_of_one_persona_exactly_one_wins(client, potheri):
    pid = (await client.get(f"{API}/demo/personas")).json()["items"][3]["id"]
    rs = await asyncio.gather(*[post_retry(client, f"{API}/auth/demo-claim", json={"persona_id": pid}) for _ in range(20)])
    assert sorted(r.status_code for r in rs) == [200] + [409] * 19, [r.status_code for r in rs]
    assert all(r.json()["error"]["code"] == "PERSONA_TAKEN" for r in rs if r.status_code == 409)
    winner = next(r for r in rs if r.status_code == 200).json()
    assert winner["passenger"]["id"] == pid
    # the pool shows it taken exactly once and the same persona cannot be picked again via switch either
    items = {i["id"]: i["is_taken"] for i in (await client.get(f"{API}/demo/personas")).json()["items"]}
    assert items[pid] is True and sum(items.values()) == 1
    other = await client.post(f"{API}/auth/demo-claim", json={"surprise": True})
    assert other.status_code == 200 and other.json()["passenger"]["id"] != pid


async def test_batch_open_and_pod_update_notifications(client, potheri, ops_headers):
    from tests.helpers import cancel, claim_persona
    ta, pa = await claim_persona(client, "commuter-guindy")
    await cancel(client, ops_headers)
    notes = (await client.get(f"{API}/me/notifications", headers=bearer(ta))).json()["items"]
    assert {"disruption_alert", "batch_open"} <= {n["template"] for n in notes}
    assert "close at" in next(n for n in notes if n["template"] == "batch_open")["body"]
    tb, _ = await claim_persona(client, "parent-tambaram")
    tc, _ = await claim_persona(client, "family-tambaram")
    tam = (await client.get(f"{API}/destinations", params={"q": "Tambaram"})).json()["items"][0]["id"]
    pod = (await client.post(f"{API}/me/pods", json={"destination_node_id": tam, "mode": "auto"}, headers=bearer(tb))).json()
    r = await client.post(f"{API}/pods/{pod['id']}/join", headers={**bearer(ta), "Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 200, r.text
    got = (await client.get(f"{API}/me/notifications", headers=bearer(tb))).json()["items"]
    assert any(n["template"] == "pod_update" and pa["name"] in n["body"] for n in got)
