"""Scenario seeding + deterministic reset (PRD F1.2, §11)."""
from __future__ import annotations

import json
import random
import time
from datetime import timedelta
from pathlib import Path

import structlog
from sqlalchemy import insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.adapters.mock import MockAdapter, SEED_ROOT
from app.config import get_settings
from app.db import acquire_xact_lock
from app.dbutil import bulk
from app.domain import routing as rt
from app.errors import AppError
from app.models import (Edge, Group, Node, Passenger, PriorityRule, Scenario, Seat, Service, ServiceStop)
from app.security import hash_password_sync
from app.seed.generator import calibrate_capacity, expand_vehicles, generate_passengers
from app.services.scenarios import default_config

log = structlog.get_logger()

SEED_SCENARIOS = ["potheri", "secondary"]  # seed/<key>/ directories; first one is the default

_WIPE = [
    "DELETE FROM batches WHERE scenario_id=:s", "DELETE FROM allocation_runs WHERE scenario_id=:s",
    "DELETE FROM pods WHERE scenario_id=:s", "DELETE FROM passengers WHERE scenario_id=:s",
    "DELETE FROM groups WHERE scenario_id=:s", "DELETE FROM disruptions WHERE scenario_id=:s",
    "DELETE FROM services WHERE scenario_id=:s", "DELETE FROM edges WHERE scenario_id=:s",
    "DELETE FROM nodes WHERE scenario_id=:s", "DELETE FROM priority_rules WHERE scenario_id=:s",
    "DELETE FROM audit_log WHERE scenario_id=:s", "DELETE FROM notifications WHERE scenario_id=:s",
]


async def ensure_scenarios(session: AsyncSession) -> list[Scenario]:
    """Create scenario rows (without data) for every seed directory; activate the default."""
    default_slug = get_settings().DEFAULT_SCENARIO
    existing = {s.slug: s for s in (await session.execute(select(Scenario))).scalars()}
    for key in SEED_SCENARIOS:
        meta = MockAdapter(key).load_services().scenario
        if meta["slug"] in existing:
            continue
        sc = Scenario(slug=meta["slug"], name=meta["name"], seed_key=key, is_active=False,
                      rng_seed=int(meta.get("rng_seed", 42)), config=default_config(), t0=clock.utcnow())
        session.add(sc)
        existing[meta["slug"]] = sc
    await session.flush()
    if not any(s.is_active for s in existing.values()):
        existing.get(default_slug, next(iter(existing.values()))).is_active = True
    await session.flush()
    return list(existing.values())


async def reset_scenario(session: AsyncSession, slug: str) -> dict:
    t_start = time.perf_counter()
    sc = (await session.execute(select(Scenario).where(Scenario.slug == slug).with_for_update())).scalars().first()
    if sc is None:
        raise AppError("NOT_FOUND", f"Unknown scenario '{slug}'")
    await acquire_xact_lock(session, "alloc", sc.id)  # wait for a running allocation
    for stmt in _WIPE:
        await session.execute(text(stmt), {"s": sc.id})

    settings = get_settings()
    ad = MockAdapter(sc.seed_key)
    net, catalog, gen_cfg, rules = ad.load_network(), ad.load_services(), ad.load_generator_config(), ad.load_rules()
    rng = random.Random(sc.rng_seed)
    t0 = clock.utcnow()

    # ---- nodes
    node_rows = [dict(scenario_id=sc.id, code=n["code"], name=n["name"], lat=n["lat"], lng=n["lng"],
                      kind=n["kind"], is_hub=n.get("is_hub", False),
                      is_default_hub=n.get("is_default_hub", False), coord_verified=n.get("verified", False))
                 for n in net.nodes]
    node_id = {code: i for i, code in await bulk(session, Node, node_rows, (Node.id, Node.code))}
    node_xy = {node_id[n["code"]]: (n["lat"], n["lng"]) for n in net.nodes}
    station_ids = {node_id[n["code"]] for n in net.nodes if n["kind"] == "rail_station"}

    # ---- edges (both directions; reverse polyline mirrored)
    edge_rows, edge_infos, geom = [], [], {}
    for e in net.edges:
        a, b = node_id[e["from"]], node_id[e["to"]]
        fwd = net.road_polylines.get(f"{e['from']}-{e['to']}") or [
            [node_xy[a][1], node_xy[a][0]], [node_xy[b][1], node_xy[b][0]]]
        pairs = [(a, b, fwd)] + ([(b, a, list(reversed(fwd)))] if e.get("bidirectional", True) else [])
        for u, v, pl in pairs:
            edge_rows.append(dict(scenario_id=sc.id, from_node_id=u, to_node_id=v, mode=e["mode"],
                                  distance_km=e["distance_km"], base_minutes=e["base_minutes"],
                                  road_name=e.get("road_name"), polyline=pl, is_closed=False))
            edge_infos.append(rt.EdgeInfo(0, u, v, e["mode"], e["base_minutes"], e["distance_km"], False))
            geom[(e["mode"], u, v)] = pl
    await bulk(session, Edge, edge_rows)
    graphs = {m: rt.build_graph(edge_infos, {m}) for m in ("rail", "road")}

    # ---- services (routes + schedule)
    dwell = catalog.dwell_minutes
    svc_defs = expand_vehicles(catalog.services)
    svc_rows, svc_routes, serving, popularity, eta = [], {}, {}, {}, {}
    for d in svc_defs:
        mode_graph = graphs["rail" if d["mode"] == "local_train" else "road"]
        gmode = "rail" if d["mode"] == "local_train" else "road"
        stop_codes = d.get("route") or d["stops"]
        route = rt.expand_route(mode_graph, [node_id[c] for c in stop_codes], bool(d.get("stop_all")), station_ids)
        if "anchor" in d:
            off = rt.offset_for_anchor(route, mode_graph, dwell, node_id[d["anchor"]["node"]])
            origin = t0 + timedelta(minutes=d["anchor"]["offset_min"] - off)
        else:
            origin = t0 + timedelta(minutes=d.get("origin_offset_min", 0))
        rt.schedule_route(route, mode_graph, dwell, origin)
        pl = rt.polyline_for_route([s.node_id for s in route],
                                   {(u, v): g for (m, u, v), g in geom.items() if m == gmode}, node_xy)
        svc_routes[d["code"]] = route
        serving[d["code"]] = [s.node_id for s in route if not s.is_via]
        eta[d["code"]] = {s.node_id: (s.arrive_at - t0).total_seconds() / 60 for s in route if not s.is_via}
        popularity[d["code"]] = float(d.get("popularity", 1)) if d.get("inventory") else 0
        svc_rows.append(dict(scenario_id=sc.id, code=d["code"], label=d["label"], mode=d["mode"], status="scheduled",
                             has_seat_inventory=bool(d.get("inventory")), depart_at=route[0].depart_at,
                             arrive_at=route[-1].arrive_at, polyline=pl, created_by="seed", version=1,
                             total_seats=0, accessible_seats=0, delay_minutes=0))
    # ---- passengers (plan first: the plan decides which vehicles exist and how big they are)
    meta = catalog.scenario
    hub_id = node_id[gen_cfg["hub"]]
    featured = meta["featured_service"]
    local_codes = [d["code"] for d in svc_defs if d["mode"] == "local_train" and not d.get("inventory")]
    caps_by_mode = {"bus": 50, "shuttle": 30, "charter_bus": 50, "local_train": 60, **(gen_cfg.get("vehicle_caps") or {})}
    leftover = int(gen_cfg.get("demo_leftover_seats", 3))
    load_cap = {d["code"]: caps_by_mode[d["mode"]] - leftover for d in svc_defs if d.get("inventory") and d.get("calibrate")}
    opens_after = {d["code"]: (d["clone_of"] if d["code"].endswith("-2") else d["clone_of"] + "-" + str(int(d["code"].rsplit("-", 1)[1]) - 1))
                   for d in svc_defs if d.get("clone_of")}
    gen = generate_passengers(gen_cfg, rng, t0=t0, hub_id=hub_id, node_ids=node_id, featured_code=featured,
                              local_codes=local_codes, serving=serving, popularity=popularity, eta=eta, load_cap=load_cap,
                              opens_after=opens_after)
    if gen_cfg.get("capacity_mode") == "calibrated":
        caps = calibrate_capacity(svc_defs, gen, featured, leftover, float(gen_cfg.get("scarce_capacity_ratio", 0.7)),
                                  caps_by_mode)
    else:
        caps = {d["code"]: (min(int(d.get("seats", 40)), caps_by_mode[d["mode"]]), min(max(2, int(d.get("accessible_seats", 2))), 4))
                for d in svc_defs if d.get("inventory") and not d.get("clone_of")}
    keep = {r["code"] for r in svc_rows if (not r["has_seat_inventory"]) or r["code"] in caps}
    svc_rows = [dict(r, total_seats=caps.get(r["code"], (0, 0))[0], accessible_seats=caps.get(r["code"], (0, 0))[1])
                for r in svc_rows if r["code"] in keep]
    svc_id = {code: i for i, code in await bulk(session, Service, svc_rows, (Service.id, Service.code))}
    await bulk(session, ServiceStop, [dict(service_id=svc_id[code], seq=i, node_id=s.node_id, arrive_at=s.arrive_at,
                                           depart_at=s.depart_at, is_skipped=False, is_via=s.is_via)
                                      for code, route in svc_routes.items() if code in keep for i, s in enumerate(route)])
    # groups
    gids = []
    big = [p for p in gen if p["party_size"] > 1]
    if big:
        res = await bulk(session, Group, [dict(scenario_id=sc.id, size=p["party_size"]) for p in big], (Group.id,))
        gids = [r[0] for r in res]
    group_of = {id(p): gids[i] for i, p in enumerate(big)}

    rows = []
    for p in gen:
        rows.append(dict(
            scenario_id=sc.id, name=p["name"], email=p["email"], password_hash=None, phone=p["phone"],
            ticket_id=p["ticket_id"], is_seeded=True, is_demo_persona=False, token_version=0,
            persona_title=None, persona_emoji=None, persona_summary=None, persona_claimed_at=None,
            group_id=group_of.get(id(p)), party_size=p["party_size"], hub_node_id=hub_id,
            destination_node_id=node_id[p["destination_code"]], ticket_service_id=svc_id[p["ticket_code"]],
            wheelchair=p["wheelchair"], elderly=p["elderly"], with_children=p["with_children"],
            medical=p["medical"], connection_deadline_at=p["connection_deadline_at"], allow_auto=True,
            state="BOOKED", registered_at=p["registered_at"], seed_plan=p["seed_plan"]))
    # demo personas (judges) — not "seeded": they make their own requests
    persona_hash = hash_password_sync(settings.DEMO_PERSONA_PASSWORD)
    used_tickets = {p["ticket_id"] for p in gen}
    persona_defs = gen_cfg.get("personas", [])
    persona_rows = []
    for i, pd in enumerate(persona_defs):
        while True:
            tid = f"VT-{rng.randrange(16**6):06X}"
            if tid not in used_tickets:
                used_tickets.add(tid)
                break
        nd = pd.get("needs", {})
        dl = pd.get("deadline_minutes")
        persona_rows.append(dict(
            scenario_id=sc.id, name=pd["name"], email=f"{pd['slug']}@demo.revior.test", password_hash=persona_hash,
            phone=None, ticket_id=tid, is_seeded=False, is_demo_persona=True, persona_title=pd["title"],
            persona_emoji=pd["emoji"], persona_summary=pd["summary"], persona_claimed_at=None, token_version=0,
            party_size=pd.get("party_size", 1), hub_node_id=hub_id, destination_node_id=node_id[pd["destination"]],
            ticket_service_id=svc_id[featured], wheelchair=nd.get("wheelchair", False),
            elderly=nd.get("elderly", False), with_children=nd.get("with_children", False),
            medical=nd.get("medical", False),
            connection_deadline_at=(t0 + timedelta(minutes=dl)) if dl else None, allow_auto=True,
            state="BOOKED", registered_at=t0 - timedelta(hours=1) + timedelta(seconds=i), seed_plan=None))
    await bulk(session, Passenger, rows + persona_rows)

    # ---- seats
    seat_rows = []
    for code, (total, acc) in caps.items():
        sid = svc_id[code]
        seat_rows += [dict(service_id=sid, seat_no=f"W{i:02d}", is_accessible=True, status="free") for i in range(1, acc + 1)]
        seat_rows += [dict(service_id=sid, seat_no=f"{i:03d}", is_accessible=False, status="free")
                      for i in range(1, total - acc + 1)]
    await bulk(session, Seat, seat_rows)

    # ---- rules, scenario row
    await bulk(session, PriorityRule, [dict(scenario_id=sc.id, version=1, weights=rules, is_active=True)])
    sc.t0 = t0
    sc.default_hub_node_id = node_id[meta["default_hub"]]
    sc.featured_service_id = svc_id[featured]
    sc.config = default_config()
    await session.flush()

    counts = {"passengers": len(rows) + len(persona_rows), "services": len(svc_rows), "personas": len(persona_rows)}
    _write_judge_logins(sc, ad.dir, persona_defs, persona_rows)
    ms = int((time.perf_counter() - t_start) * 1000)
    log.info("scenario_reset", scenario=slug, duration_ms=ms, **counts,
             capacity={c: v[0] for c, v in caps.items()}, polylines=ad.polyline_source())
    return {"duration_ms": ms, "counts": counts, "capacity": {c: {"seats": v[0], "accessible": v[1]} for c, v in caps.items()}}


def _write_judge_logins(sc: Scenario, seed_dir: Path, persona_defs: list[dict], persona_rows: list[dict]) -> None:
    s = get_settings()
    lines = [f"# Judge backup logins — {sc.name} (`{sc.slug}`)", "",
             f"Demo personas share one password: `{s.DEMO_PERSONA_PASSWORD}` (env `DEMO_PERSONA_PASSWORD`).",
             "Log in at `/login` with the persona e-mail, or use the persona picker at `/demo-join`.", "",
             "| Persona | E-mail | Ticket |", "|---|---|---|"]
    for pd, row in zip(persona_defs, persona_rows):
        lines.append(f"| {pd['emoji']} {pd['title']} | `{row['email']}` | `{row['ticket_id']}` |")
    try:
        (seed_dir / "judge_logins.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:  # read-only image
        log.warning("judge_logins_not_written", dir=str(seed_dir))
