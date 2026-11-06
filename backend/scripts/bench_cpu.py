"""Per-request CPU time + wall latency of passenger reads, in-process (no network, no Docker proxy).

CPU time (`process_time`) is immune to a busy host, so it shows what the code itself costs; wall time shows what the
box delivered while measuring. On an idle machine wall ~ CPU + DB round trips.

  python scripts/bench_cpu.py [--n 60]      (needs a seeded scenario; it resets + cancels + allocates first)
"""
import argparse
import asyncio
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("AUTO_BOOTSTRAP", "false")
os.environ.setdefault("RUN_BACKGROUND_LOOPS", "false")

import httpx  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import dispose_engine  # noqa: E402
from app.main import app  # noqa: E402


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round((len(xs) - 1) * q)))]


async def main(n: int):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://bench/api/v1", timeout=120) as c:
        ops = (await c.post("/auth/ops-login", json={"password": get_settings().OPS_PASSWORD})).json()["token"]
        oh = {"Authorization": f"Bearer {ops}"}
        await c.post("/ops/scenarios/potheri-demo/activate", headers=oh)
        await c.post("/ops/scenarios/potheri-demo/reset", headers=oh)
        svcs = {s["code"]: s for s in (await c.get("/ops/services", headers=oh)).json()["items"]}
        await c.post("/ops/disruptions", headers=oh, json={"type": "cancellation", "service_id": svcs["EMU-CGL-BCH-1810"]["id"], "reason": "bench"})
        await c.post("/ops/allocation/run", headers=oh, json={"mode": "greedy"})
        toks = [(await c.post("/auth/demo-claim", json={"persona_id": p["id"]})).json()["token"] for p in (await c.get("/demo/personas")).json()["items"]]
        print(f"{'endpoint':20s} {'CPU ms/req':>10s} {'wall p50':>9s} {'wall p95':>9s}   (n={n}, sequential, in-process)")
        for ep in ["/me", "/me/trip", "/me/status", "/me/options", "/me/why", "/me/notifications", "/me/alternatives"]:
            cpu, wall = [], []
            for i in range(n):
                h = {"Authorization": f"Bearer {toks[i % len(toks)]}"}
                c0, w0 = time.process_time(), time.perf_counter()
                r = await c.get(ep, headers=h)
                cpu.append((time.process_time() - c0) * 1000)
                wall.append((time.perf_counter() - w0) * 1000)
                assert r.status_code == 200, (ep, r.status_code)
            print(f"{ep:20s} {statistics.mean(cpu):10.1f} {statistics.median(wall):9.1f} {pct(wall, 0.95):9.1f}")
    await dispose_engine()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=60)
    asyncio.run(main(ap.parse_args().n))
