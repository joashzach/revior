"""One-off helper that emits seed/<scenario>/nodes.json + edges.json (hand-edit afterwards if needed).

Coordinates are approximate (from public knowledge of the stations), flagged `verified: false`.
Usage: python scripts/build_seed_data.py
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "seed"


def hav(a, b):
    r = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dphi, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def apply_overrides(name, nodes):
    """coordinate_overrides.json (written by scripts/verify_coordinates.py) holds OSM-confirmed positions."""
    f = ROOT / name / "coordinate_overrides.json"
    if not f.exists():
        return nodes
    ov = json.loads(f.read_text(encoding="utf-8"))
    for n in nodes:
        o = ov.get(n["code"])
        if o:
            n.update(lat=o["lat"], lng=o["lng"], verified=bool(o.get("verified")))
    return nodes


def build(name, nodes, rail_chain, road_chain, extra_edges, walk_edges, road_name_fn):
    nodes = apply_overrides(name, nodes)
    pos = {n["code"]: (n["lat"], n["lng"]) for n in nodes}
    edges = []

    def add(a, b, mode, km=None, minutes=None, road=None):
        d = km if km is not None else hav(pos[a], pos[b]) * (1.25 if mode == "road" else 1.1)
        if minutes is None:
            minutes = max(2.0, d / 0.7) if mode == "rail" else (d / 0.45 if mode == "road" else d / 0.08)
        edges.append({"from": a, "to": b, "mode": mode, "distance_km": round(d, 2),
                      "base_minutes": round(minutes, 1), "road_name": road, "bidirectional": True})

    for a, b in zip(rail_chain, rail_chain[1:]):
        add(a, b, "rail")
    for a, b in zip(road_chain, road_chain[1:]):
        add(a, b, "road", road=road_name_fn(a, b))
    for a, b, km, mins, road in extra_edges:
        add(a, b, "road", km, mins, road)
    for a, b, km, mins in walk_edges:
        add(a, b, "walk", km, mins)
    d = ROOT / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "nodes.json").write_text(json.dumps(nodes, indent=1))
    (d / "edges.json").write_text(json.dumps(edges, indent=1))
    print(name, len(nodes), "nodes", len(edges), "edges")


def N(code, name, lat, lng, kind="rail_station", hub=False, default=False):
    return {"code": code, "name": name, "lat": lat, "lng": lng, "kind": kind,
            "is_hub": hub, "is_default_hub": default, "verified": False}


potheri_nodes = [
    N("CGL", "Chengalpattu", 12.6819, 79.9888), N("PRN", "Paranur", 12.7173, 79.9958),
    N("SPK", "Singaperumal Koil", 12.7476, 80.0092), N("MMN", "Maraimalai Nagar", 12.7937, 80.0240, hub=True),
    N("KTM", "Kattankulathur", 12.8139, 80.0366, hub=True), N("POT", "Potheri", 12.8231, 80.0442, hub=True, default=True),
    N("GUD", "Guduvanchery", 12.8436, 80.0602, hub=True), N("URP", "Urapakkam", 12.8625, 80.0630),
    N("VAN", "Vandalur", 12.8914, 80.0817), N("PER", "Perungalathur", 12.9055, 80.0890),
    N("TAM", "Tambaram", 12.9249, 80.1177), N("CHR", "Chromepet", 12.9516, 80.1403),
    N("PLV", "Pallavaram", 12.9675, 80.1491), N("TIR", "Tirusulam (Airport)", 12.9823, 80.1639),
    N("GND", "Guindy", 13.0067, 80.2206), N("MBM", "Mambalam", 13.0386, 80.2217),
    N("EGM", "Egmore", 13.0732, 80.2609), N("BCH", "Chennai Beach", 13.0950, 80.2907),
    N("NED", "Nedungundram Jn (Outer Ring Rd)", 12.8730, 80.0950, kind="bus_stop"),
    N("MUD", "Mudichur Jn (Vandalur-Kelambakkam Rd)", 12.9000, 80.1050, kind="bus_stop"),
]
rail = ["CGL", "PRN", "SPK", "MMN", "KTM", "POT", "GUD", "URP", "VAN", "PER", "TAM", "CHR", "PLV", "TIR", "GND", "MBM", "EGM", "BCH"]
build(
    "potheri", potheri_nodes, rail, rail,
    [("URP", "NED", 7.0, 11.0, "Outer Ring Road"), ("NED", "MUD", 5.5, 8.0, "Vandalur-Kelambakkam Road"),
     ("MUD", "PER", 3.5, 6.0, "Vandalur-Kelambakkam Road"), ("MUD", "TAM", 5.0, 8.5, "Mudichur Road")],
    [("POT", "KTM", 2.3, 28), ("POT", "GUD", 3.6, 45), ("KTM", "MMN", 3.9, 48)],
    lambda a, b: "Anna Salai" if a in ("MBM", "EGM") else "GST Road",
)

mum_nodes = [
    N("CSMT", "Mumbai CSMT", 18.9398, 72.8355, hub=True, default=True), N("BYC", "Byculla", 18.9764, 72.8326, hub=True),
    N("DDR", "Dadar", 19.0178, 72.8478), N("KRL", "Kurla", 19.0652, 72.8795),
    N("GTK", "Ghatkopar", 19.0860, 72.9081), N("TNA", "Thane", 19.1860, 72.9755),
]
mum_rail = ["CSMT", "BYC", "DDR", "KRL", "GTK", "TNA"]
build("secondary", mum_nodes, mum_rail, mum_rail, [], [("CSMT", "BYC", 3.2, 38)],
      lambda a, b: "Eastern Express Highway" if a in ("KRL", "GTK") else "LBS / P D'Mello Road")
