"""Measure p50/p95 latency of the passenger read endpoints (PRD §15: p95 < 200 ms) over real HTTP.

  python scripts/bench_reads.py --base-url http://localhost:8000 --ops-password change-me [--n 100] [--concurrency 10]

Resets the scenario, cancels the featured train, runs the allocation (so /me/status etc. have real data), then fires
`--n` requests per endpoint from a pool of passengers.
"""
import argparse
import asyncio
import statistics
import time

import httpx


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round((len(xs) - 1) * q)))]


async def main(base: str, pw: str, n: int, conc: int):
    async with httpx.AsyncClient(base_url=base.rstrip("/") + "/api/v1", timeout=60, limits=httpx.Limits(max_connections=conc * 2)) as c:
        ops = (await c.post("/auth/ops-login", json={"password": pw})).json()["token"]
        oh = {"Authorization": f"Bearer {ops}"}
        await c.post("/ops/scenarios/potheri-demo/reset", headers=oh)
        svcs = {s["code"]: s for s in (await c.get("/ops/services", headers=oh)).json()["items"]}
        await c.post("/ops/disruptions", headers=oh, json={"type": "cancellation", "service_id": svcs["EMU-CGL-BCH-1810"]["id"], "reason": "bench"})
        await c.post("/ops/allocation/run", headers=oh, json={"mode": "greedy"})
        toks = []
        for p in (await c.get("/demo/personas")).json()["items"]:
            r = await c.post("/auth/demo-claim", json={"persona_id": p["id"]})
            toks.append(r.json()["token"])
        endpoints = ["/me", "/me/trip", "/me/status", "/me/options", "/me/why", "/me/notifications", "/me/alternatives"]
        print(f"{'endpoint':22s} {'n':>4s} {'p50 ms':>8s} {'p95 ms':>8s} {'max ms':>8s}")
        worst = 0.0
        for ep in endpoints:
            lat: list[float] = []
            sem = asyncio.Semaphore(conc)

            async def one(i):
                async with sem:
                    for attempt in range(4):          # retry only transport resets (Docker Desktop port-proxy flakiness)
                        t = time.perf_counter()
                        try:
                            r = await c.get(ep, headers={"Authorization": f"Bearer {toks[i % len(toks)]}"})
                            break
                        except httpx.TransportError:
                            await asyncio.sleep(0.2)
                    lat.append((time.perf_counter() - t) * 1000)
                    assert r.status_code == 200, (ep, r.status_code, r.text[:200])
            await asyncio.gather(*[one(i) for i in range(n)])
            p95 = pct(lat, 0.95)
            worst = max(worst, p95)
            print(f"{ep:22s} {n:4d} {statistics.median(lat):8.1f} {p95:8.1f} {max(lat):8.1f}")
        print(f"\nworst p95 = {worst:.1f} ms (target < 200 ms)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--ops-password", default="change-me")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--concurrency", type=int, default=10)
    a = ap.parse_args()
    asyncio.run(main(a.base_url, a.ops_password, a.n, a.concurrency))
