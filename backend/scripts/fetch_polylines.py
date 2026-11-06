"""Fetch OSRM road polylines ONCE (offline, before the demo) -> seed/<scenario>/road_polylines.json.

Runtime never calls OSRM (PRD §10.4). Rail edges are always straight lines. When OSRM is
unreachable (or a route fails) the edge falls back to a straight line and the file records
``"source": "fallback"`` (or ``"partial"``) so the stage report can say so honestly.

Usage:  python scripts/fetch_polylines.py [potheri secondary]
"""
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent / "seed"
OSRM = "https://router.project-osrm.org/route/v1/driving/{a};{b}?overview=full&geometries=geojson"


def fetch(client: httpx.Client, a, b):
    r = client.get(OSRM.format(a=f"{a[1]},{a[0]}", b=f"{b[1]},{b[0]}"), timeout=15)
    r.raise_for_status()
    data = r.json()
    if data.get("code") != "Ok":
        raise RuntimeError(data.get("code"))
    return data["routes"][0]["geometry"]["coordinates"]


def run(key: str) -> None:
    d = ROOT / key
    nodes = {n["code"]: (n["lat"], n["lng"]) for n in json.loads((d / "nodes.json").read_text())}
    edges = [e for e in json.loads((d / "edges.json").read_text()) if e["mode"] == "road"]
    out, ok, failed = {}, 0, 0
    with httpx.Client(headers={"User-Agent": "revior-hackathon-seed/1.0"}) as client:
        for e in edges:
            key_ = f"{e['from']}-{e['to']}"
            try:
                out[key_] = fetch(client, nodes[e["from"]], nodes[e["to"]])
                ok += 1
            except Exception as exc:  # noqa: BLE001
                print(f"  {key_}: fallback straight line ({exc.__class__.__name__})")
                out[key_] = [[nodes[e["from"]][1], nodes[e["from"]][0]], [nodes[e["to"]][1], nodes[e["to"]][0]]]
                failed += 1
            time.sleep(0.3)  # be polite to the public demo server
    source = "osrm" if failed == 0 and ok else ("partial" if ok else "fallback")
    (d / "road_polylines.json").write_text(json.dumps({"source": source, "edges": out}))
    print(f"{key}: {ok} fetched, {failed} straight-line fallbacks -> source={source}")


if __name__ == "__main__":
    for k in (sys.argv[1:] or ["potheri", "secondary"]):
        run(k)
