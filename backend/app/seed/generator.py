"""Deterministic passenger generator + capacity calibration (PRD §11).

Pure functions: no DB access, driven by ``passengers.yaml`` and ``random.Random(rng_seed)``.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any


def _weighted(rng: random.Random, weights: dict[str, float]) -> str:
    keys = sorted(weights)  # sorted -> deterministic regardless of dict order
    return rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]


def candidate_services(hub: int, dest: int, serving: dict[str, list[int]], popularity: dict[str, float],
                       eta: dict[str, dict[int, float]] | None = None, deadline_min: float | None = None) -> dict[str, float]:
    """Inventory services (by code) that go hub -> dest in stop order, weighted by popularity. When a
    deadline is given, services arriving after it are excluded (the engine treats that as a hard constraint)."""
    out = {}
    for code, stops in serving.items():
        w = popularity.get(code, 0)
        if w <= 0 or hub not in stops or dest not in stops:
            continue
        if stops.index(hub) < stops.index(dest):
            if deadline_min is not None and eta and eta.get(code, {}).get(dest, 0) > deadline_min - 1:
                continue
            out[code] = w
    return out


def generate_passengers(
    cfg: dict[str, Any],
    rng: random.Random,
    *,
    t0: datetime,
    hub_id: int,
    node_ids: dict[str, int],
    featured_code: str,
    local_codes: list[str],
    serving: dict[str, list[int]],
    popularity: dict[str, float],
    eta: dict[str, dict[int, float]] | None = None,
    load_cap: dict[str, int] | None = None,
    opens_after: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """``load_cap``: max first-choice seat demand per vehicle (vehicle size minus the leftover seats). A vehicle that
    is full is not offered as a choice, so demand spills onto the extra vehicles generated on the same route."""
    load_cap = load_cap or {}
    opens_after = opens_after or {}
    n = int(cfg["count"])
    dest_w = {k: float(v) for k, v in cfg["destinations"].items()}
    total_w = sum(dest_w.values())
    airport = cfg.get("airport_node")
    p_air_dest = dest_w.get(airport, 0) / total_w if airport else 0
    dl = cfg["deadline"]
    p_dl_air = min(1.0, dl["share"] * dl["airport_share"] / p_air_dest) if p_air_dest else 0
    p_dl_other = min(1.0, dl["share"] * (1 - dl["airport_share"]) / max(1e-9, 1 - p_air_dest))
    needs = cfg["needs"]
    group_idx = set(rng.sample(range(n), min(cfg["groups"]["count"], n)))
    ch = cfg["choices"]
    others = cfg.get("other_ticket_services") or []
    firsts, lasts = cfg["first_names"], cfg["last_names"]
    out: list[dict[str, Any]] = []
    load: dict[str, int] = {}  # running first-choice seat demand per service (congestion-aware choice)
    for i in range(n):
        first, last = rng.choice(firsts), rng.choice(lasts)
        dest_code = _weighted(rng, dest_w)
        party = rng.randint(cfg["groups"]["min_size"], cfg["groups"]["max_size"]) if i in group_idx else 1
        wc = rng.random() < needs["wheelchair"]
        elderly = rng.random() < needs["elderly"]
        kids = rng.random() < needs["with_children"] or (party >= 3 and rng.random() < 0.35)
        medical = rng.random() < needs["medical"]
        has_dl = rng.random() < (p_dl_air if dest_code == airport else p_dl_other)
        deadline = None
        deadline_min = None
        if has_dl:
            lo, hi = dl["airport_minutes"] if dest_code == airport else dl["other_minutes"]
            deadline_min = rng.randint(lo, hi)
            deadline = t0 + timedelta(minutes=deadline_min)
        ticket = featured_code if (not others or rng.random() < cfg["featured_share"]) else rng.choice(others)
        dest_id = node_ids[dest_code]
        cands = candidate_services(hub_id, dest_id, serving, popularity, eta, deadline_min)
        def opened(k: str) -> bool:
            """an extra vehicle opens once the previous one on the route is mostly full (or can't take this party)"""
            prev = opens_after.get(k)
            if prev is None:
                return True
            return load.get(prev, 0) >= 0.8 * load_cap.get(prev, 0) or load.get(prev, 0) + party > load_cap.get(prev, 10 ** 9)
        cands = {k: w / (1 + load.get(k, 0) / 35.0) for k, w in cands.items()
                 if load.get(k, 0) + party <= load_cap.get(k, 10 ** 9) and opened(k)}
        roll = rng.random()
        plan: dict[str, Any] = {"c1": None, "c2": None, "any": False}
        if not cands:
            plan["any"] = True
        elif roll < ch["both"]:
            plan["c1"] = _weighted(rng, cands)
            load[plan["c1"]] = load.get(plan["c1"], 0) + party
            rest = {k: v for k, v in cands.items() if k != plan["c1"]}
            plan["c2"] = _weighted(rng, rest) if rest else None
        elif roll < ch["both"] + ch["any_fastest"]:
            plan["any"] = True
            # remember where "any, fastest" will land (earliest arrival) so capacity can be calibrated for it
            plan["fast"] = min(cands, key=lambda c: (eta.get(c, {}).get(dest_id, 1e9), c)) if (eta and cands) else None
            if plan["fast"]:
                load[plan["fast"]] = load.get(plan["fast"], 0) + party
        else:
            plan["c1"] = _weighted(rng, cands)
            load[plan["c1"]] = load.get(plan["c1"], 0) + party
        out.append({
            "name": f"{first} {last}", "email": f"{first}.{last}.{i + 1}@seed.revior.test".lower(),
            "phone": f"+9190000{i:05d}", "ticket_id": f"SP-{100000 + i}", "is_seeded": True,
            "party_size": party, "destination_code": dest_code, "ticket_code": ticket,
            "wheelchair": wc, "elderly": elderly, "with_children": kids, "medical": medical,
            "connection_deadline_at": deadline, "allow_auto": True, "seed_plan": plan,
            "registered_at": t0 - timedelta(days=1) + timedelta(seconds=i),
        })
    return out


def calibrate_capacity(
    service_defs: list[dict[str, Any]],
    passengers: list[dict[str, Any]],
    featured_code: str,
    leftover: int,
    scarce_ratio: float,
    caps_by_mode: dict[str, int],
) -> dict[str, tuple[int, int]]:
    """Seats per vehicle = its first-choice demand + leftover (judges compete for the last few seats), never above
    the realistic size of the vehicle type. `scarce` vehicles get ratio x demand so at least one destination is
    under-supplied. Extra vehicles (clones) nobody needs are dropped. Returns {code: (seats, accessible)}."""
    demand: dict[str, int] = {}
    wc_demand: dict[str, int] = {}
    for p in passengers:
        if p["ticket_code"] != featured_code:
            continue
        c1 = p["seed_plan"]["c1"] or p["seed_plan"].get("fast")
        if c1:
            demand[c1] = demand.get(c1, 0) + p["party_size"]
            if p["wheelchair"]:
                wc_demand[c1] = wc_demand.get(c1, 0) + 1
    out: dict[str, tuple[int, int]] = {}
    for s in service_defs:
        if not s.get("inventory"):
            continue
        cap = int(caps_by_mode.get(s["mode"], 60))
        code = s["code"]
        base, acc = int(s.get("seats", 40)), int(s.get("accessible_seats", 2))
        if s.get("calibrate") and demand.get(code, 0) > 0:
            d = demand[code]
            seats = max(10, int(d * scarce_ratio)) if s.get("scarce") else d + leftover
            base, acc = seats, max(2, wc_demand.get(code, 0) + 1)
        elif s.get("clone_of"):
            continue                      # an extra vehicle nobody needed
        base = min(base, cap)
        out[code] = (base, min(max(2, acc), 4, base))
    return out


def expand_vehicles(service_defs: list[dict[str, Any]], stagger_min: int = 6) -> list[dict[str, Any]]:
    """`vehicles: N` on a seat-bearing service generates N-1 extra vehicles on the same route (own code/label,
    departing `stagger_min` later each) instead of enlarging one vehicle."""
    out: list[dict[str, Any]] = []
    for d in service_defs:
        out.append(d)
        for k in range(2, int(d.get("vehicles", 1)) + 1):
            c = {**d, "code": f"{d['code']}-{k}", "label": f"{d['label']} ({k})", "clone_of": d["code"]}
            c.pop("vehicles", None)
            if "anchor" in c:
                c["anchor"] = {**c["anchor"], "offset_min": c["anchor"]["offset_min"] + stagger_min * (k - 1)}
            else:
                c["origin_offset_min"] = c.get("origin_offset_min", 0) + stagger_min * (k - 1)
            out.append(c)
    return out
