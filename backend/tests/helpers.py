"""Shared test helpers (API-level)."""
from __future__ import annotations

API = "/api/v1"


def bearer(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


async def services_by_code(client, ops) -> dict:
    items = (await client.get(f"{API}/ops/services", headers=ops)).json()["items"]
    return {s["code"]: s for s in items}


async def nodes_by_code(client, ops) -> dict:
    return {n["code"]: n for n in (await client.get(f"{API}/ops/network", headers=ops)).json()["nodes"]}


async def edge_between(client, ops, a: str, b: str, mode: str):
    net = (await client.get(f"{API}/ops/network", headers=ops)).json()
    ids = {n["code"]: n["id"] for n in net["nodes"]}
    for e in net["edges"]:
        if e["mode"] == mode and {e["from_node_id"], e["to_node_id"]} == {ids[a], ids[b]}:
            return e
    raise AssertionError(f"no {mode} edge {a}-{b}")


async def cancel(client, ops, code="EMU-CGL-BCH-1810", reason="Waterlogging near Guduvanchery"):
    svcs = await services_by_code(client, ops)
    r = await client.post(f"{API}/ops/disruptions", headers=ops,
                          json={"type": "cancellation", "service_id": svcs[code]["id"], "reason": reason})
    assert r.status_code == 200, r.text
    return r.json()


async def claim_persona(client, slug_email: str):
    r = await client.post(f"{API}/auth/login", json={"email": f"{slug_email}@demo.revior.test", "password": "revior-demo"})
    assert r.status_code == 200, r.text
    j = r.json()
    return j["token"], j["passenger"]


async def post_retry(client, url: str, attempts: int = 4, **kw):
    """POST that retries transport-level failures (Windows/Docker TCP resets under heavy load). Callers pass an
    Idempotency-Key, so a retried mutation can never be applied twice."""
    import asyncio
    for i in range(attempts):
        try:
            return await client.post(url, **kw)
        except OSError:
            await asyncio.sleep(0.2 * (i + 1))
    raise AssertionError("connection kept failing")
