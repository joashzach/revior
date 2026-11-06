"""Verify / correct node coordinates against OpenStreetMap (Nominatim) -> seed/<scenario>/coordinate_overrides.json.

For every node we look for the railway station (or, for road-only junctions, the named place) in OSM, accept a hit
only if it lies within --max-km of the hand-entered estimate, and record the OSM position with ``verified: true``.
Nodes we cannot confirm keep their estimate and stay ``verified: false``. Afterwards run:

    python scripts/build_seed_data.py       # applies the overrides, regenerates nodes.json + edges.json
    python scripts/fetch_polylines.py       # re-fetch the OSRM road polylines for the corrected positions

Usage: python scripts/verify_coordinates.py [potheri secondary] [--max-km 12]
Nominatim usage policy: <= 1 request/second, identifying User-Agent (we sleep 1.1 s between requests).
"""
import argparse
import json
import math
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent / "seed"
UA = {"User-Agent": "revior-hackathon-coordinate-verifier/1.0 (https://github.com/revior; contact: team@revior.example)"}
API = "https://nominatim.openstreetmap.org/search"
HINT = {"potheri": "Tamil Nadu", "secondary": "Maharashtra"}
# OSM often uses different transliterations
ALT = {"Guduvanchery": ["Guduvancheri", "Guduvanchery"], "Kattankulathur": ["Kattangulathur", "Kattankulathur"],
       "Urapakkam": ["Urapakkam", "Urappakkam"], "Chengalpattu": ["Chengalpattu", "Chengalpet", "Chengalpattu Junction"],
       "Maraimalai Nagar": ["Maraimalai Nagar", "Maraimalainagar"], "Singaperumal Koil": ["Singaperumal Koil", "Singaperumalkoil"],
       "Tirusulam (Airport)": ["Tirusulam", "Trisulam"], "Mumbai CSMT": ["Chhatrapati Shivaji Maharaj Terminus", "CSMT"]}


def km(a, b):
    r = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def search(client: httpx.Client, q: str):
    time.sleep(1.1)
    r = client.get(API, params={"q": q, "format": "jsonv2", "limit": 5, "countrycodes": "in"}, headers=UA, timeout=30)
    r.raise_for_status()
    return r.json()


def candidates(node: dict, hint: str) -> list[str]:
    base = node["name"].split(" (")[0].replace(" Jn", " Junction")
    names = ALT.get(node["name"], ALT.get(base, [base]))
    out = []
    for name in names:
        if node["kind"] == "rail_station":
            out += [f"{name} railway station", f"{name} railway station, {hint}", f"{name} station, {hint}"]
        else:
            out += [f"{name}, {hint}"]
    for name in names:           # locality fallback (accepted only when very close to our estimate)
        out.append(f"{name}, {hint}")
    return out


def level(x: dict, node: dict) -> str | None:
    """station = an OSM railway/public-transport object or a stop literally named '...railway station';
    locality = the named place (suburb/town) — weaker evidence, only accepted close to the estimate."""
    name = x.get("display_name", "").lower()
    if x.get("category") in ("railway", "public_transport") or "railway station" in name or "junction" in name and "railway" in name:
        return "station" if node["kind"] == "rail_station" else "place"
    if x.get("category") in ("place", "boundary") or x.get("type") in ("suburb", "town", "village", "locality", "neighbourhood"):
        return "locality"
    return None


def run(key: str, max_km: float) -> None:
    d = ROOT / key
    nodes = json.loads((d / "nodes.json").read_text(encoding="utf-8"))
    out, ok = {}, 0
    with httpx.Client() as client:
        for n in nodes:
            est = (n["lat"], n["lng"])
            hit, locality, station_hit = None, None, None
            for q in candidates(n, HINT[key]):
                try:
                    res = search(client, q)
                except Exception as exc:  # noqa: BLE001
                    print(f"  {n['code']}: query failed ({exc.__class__.__name__})")
                    continue
                for x in res:
                    pos = (float(x["lat"]), float(x["lon"]))
                    lv = level(x, n)
                    if lv is None or km(est, pos) > (max_km if lv != "locality" else 3.0):
                        continue
                    if n["kind"] == "rail_station" and lv == "locality" and station_hit:
                        continue
                    if lv in ("station", "place"):
                        hit = (pos, x, q, lv)
                        break
                    station_hit = station_hit or None
                    locality = locality or (pos, x, q, lv)
                if hit:
                    break
            hit = hit or locality
            if hit:
                pos, x, q, lv = hit
                out[n["code"]] = {"lat": round(pos[0], 6), "lng": round(pos[1], 6), "verified": True, "source": "osm-nominatim",
                                  "osm": f"{x.get('osm_type')}/{x.get('osm_id')}", "match_level": lv, "match": x["display_name"][:100],
                                  "moved_km": round(km(est, pos), 2)}
                ok += 1
                print(f"  {n['code']:5s} {lv:8s} moved {km(est, pos):5.2f} km  ({est[0]:.4f},{est[1]:.4f}) -> ({pos[0]:.4f},{pos[1]:.4f})  {x['display_name'][:60]}")
            else:
                print(f"  {n['code']:5s} NOT confirmed (kept estimate, verified=false)")
    (d / "coordinate_overrides.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{key}: {ok}/{len(nodes)} nodes verified -> {d / 'coordinate_overrides.json'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("scenarios", nargs="*", default=["potheri", "secondary"])
    ap.add_argument("--max-km", type=float, default=12.0)
    a = ap.parse_args()
    for k in a.scenarios:
        run(k, a.max_km)
    sys.exit(0)
