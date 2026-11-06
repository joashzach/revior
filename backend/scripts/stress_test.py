"""Revior stress test (PRD F23.1): 1000 concurrent requests, open-booking claims on a 10-seat service plus
accept/decline/duplicate traffic, fired with httpx.AsyncClient. Pass criteria (F23.2): confirmed+held seats <= capacity
at every instant, zero 5xx, invariants all zero.

The test world is an isolated throw-away scenario created through the app's own code (DATABASE_URL / JWT_SECRET must
match the target server) and deleted afterwards.

Usage:
  python scripts/stress_test.py                          # in-process against the app (no server needed)
  python scripts/stress_test.py --base-url http://localhost:8000   # over real HTTP against a running server
  python scripts/stress_test.py --requests 1000 --seats 10
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("AUTO_BOOTSTRAP", "false")
os.environ.setdefault("RUN_BACKGROUND_LOOPS", "false")

import httpx  # noqa: E402

from app.db import dispose_engine  # noqa: E402
from app.domain import stress  # noqa: E402


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--requests", type=int, default=1000)
    ap.add_argument("--seats", type=int, default=10)
    a = ap.parse_args()
    world = await stress.build_world(a.requests, a.seats)
    try:
        if a.base_url:
            client = httpx.AsyncClient(base_url=a.base_url, limits=httpx.Limits(max_connections=200))
        else:
            from app.main import app
            client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://stress")

        async def emit(kind, data):
            if kind == "stress.progress":
                print(f"  progress: {data}", flush=True)

        async with client:
            res = await stress.run_stress(client, world, requests=a.requests, emit=emit)
    finally:
        await stress.cleanup(world["scenario_id"])
        await dispose_engine()
    print(json.dumps(res, indent=2))
    print(f"\n{'PASS' if res['passed'] else 'FAIL'}: {res['total']} requests, {res['capacity']} seats, "
          f"{res['over_allocations']} over-allocations, {res['five_xx']} 5xx, invariants_ok={res['invariants_ok']}")
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
