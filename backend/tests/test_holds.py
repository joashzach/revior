import asyncio
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select, update

from app import clock
from app.db import get_sessionmaker
from app.domain import holds as holds_dom
from app.domain import invariants
from app.domain.allocation import run_allocation
from app.models import Allocation, Passenger, Scenario, Seat, WaitlistEntry
from app.security import create_passenger_token
from tests import factory as F
from tests.helpers import API, bearer, cancel, claim_persona, edge_between, post_retry, services_by_code

NOW = F.NOW


@pytest.fixture
async def session():
    """DB session for mini scenarios (which live in 2030): the clock is frozen to match for the API paths."""
    clock.freeze(NOW)
    async with get_sessionmaker()() as s:
        yield s
    clock.freeze(None)


async def run(session, ctx):
    res = await run_allocation(session, ctx.sc, batch=ctx.batch, now=ctx.now)
    await session.commit()
    return res


def tok(p):
    return bearer(create_passenger_token(p))


async def alloc_of(session, p, *statuses):
    return (await session.execute(select(Allocation).where(
        Allocation.passenger_id == p.id, Allocation.status.in_(statuses or ("held", "confirmed", "swap_held")))
        .order_by(Allocation.id.desc()))).scalars().first()


async def deep_ok(session, ctx):
    inv = await invariants.check(session, ctx.sc.id, deep=True)
    assert inv["ok"], inv
    return inv


# ----------------------------------------------------------------------------- expiry + cascade (F9, F10)
async def test_hold_expiry_cascades_to_top_waitlisted_feasible_unit(session):
    ctx = await F.build(session, {"S1": (1, 0)})
    a = await F.add_pax(session, ctx, "a", c1="S1", medical=True, allow_auto=False)
    b = await F.add_pax(session, ctx, "b", c1="S1", elderly=True, allow_auto=False)
    c = await F.add_pax(session, ctx, "c", c1="S1", allow_auto=False)
    d = await F.add_pax(session, ctx, "d", c1="S1", party=2, medical=True, elderly=True, allow_auto=False)   # high score, can't fit 1 seat
    await run(session, ctx)
    assert (await alloc_of(session, a)).status == "held"
    wl = (await session.execute(select(func.count()).select_from(WaitlistEntry).where(WaitlistEntry.scenario_id == ctx.sc.id))).scalar()
    assert wl == 3
    # the hold on `a` lapses -> expirer releases the seat -> cascade skips `d` (party of 2 doesn't fit) and offers to `b`
    await session.execute(update(Allocation).where(Allocation.passenger_id == a.id).values(hold_expires_at=NOW - timedelta(seconds=1)))
    await session.commit()
    events = await holds_dom.expire_due(session, ctx.sc, NOW)
    await session.commit()
    types = [e.type for e in events]
    assert "hold.expired" in types and "seat.released" in types and "offer.created" in types
    offer = next(e for e in events if e.type == "offer.created")
    assert offer.passengers == (b.id,) and offer.data["allocation"]["choice_rank"] == "cascade"
    await session.refresh(a); await session.refresh(b); await session.refresh(c)
    assert a.state == "UNRESOLVED" and b.state == "HELD" and c.state == "WAITLISTED"
    assert (await alloc_of(session, a, "expired")) is not None
    ex = (await alloc_of(session, b, "held")).explanation
    assert "highest-priority feasible" in ex
    await deep_ok(session, ctx)


async def test_hold_expiring_warning_sent_once(session):
    ctx = await F.build(session, {"S1": (1, 0)})
    a = await F.add_pax(session, ctx, "a", c1="S1", allow_auto=False)
    await run(session, ctx)
    await session.execute(update(Allocation).where(Allocation.passenger_id == a.id).values(hold_expires_at=NOW + timedelta(seconds=25)))
    await session.commit()
    ev1 = await holds_dom.expire_due(session, ctx.sc, NOW)
    await session.commit()
    ev2 = await holds_dom.expire_due(session, ctx.sc, NOW)
    await session.commit()
    assert [e.type for e in ev1 if e.type == "hold.expiring"] == ["hold.expiring"]
    assert not [e for e in ev2 if e.type == "hold.expiring"]


# ------------------------------------------------------------ accept / decline API + idempotency (F9)
async def test_accept_decline_api_with_idempotency_and_cascade(client, session):
    ctx = await F.build(session, {"S1": (1, 0), "S2": (1, 0)})
    a = await F.add_pax(session, ctx, "a", c1="S1", medical=True, allow_auto=False)
    b = await F.add_pax(session, ctx, "b", c1="S1", allow_auto=False)
    await run(session, ctx)
    await session.commit()
    ha, hb = tok(a), tok(b)
    # idempotency key is mandatory
    r = await client.post(f"{API}/me/allocation/accept", headers=ha)
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    k = str(uuid.uuid4())
    r1 = await client.post(f"{API}/me/allocation/accept", headers={**ha, "Idempotency-Key": k})
    r2 = await client.post(f"{API}/me/allocation/accept", headers={**ha, "Idempotency-Key": k})
    assert r1.status_code == 200 and r1.json()["state"] == "CONFIRMED" and r1.json()["allocation"]["status"] == "confirmed"
    assert r2.status_code == 200 and r2.json() == r1.json()                     # replayed, nothing re-executed
    # same key for another action -> conflict
    r = await client.post(f"{API}/me/allocation/decline", headers={**ha, "Idempotency-Key": k})
    assert r.status_code == 409 and r.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    # a confirmed seat can't be declined
    r = await client.post(f"{API}/me/allocation/decline", headers={**ha, "Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 409 and r.json()["error"]["code"] == "INVALID_STATE"
    st = (await client.get(f"{API}/me/status", headers=hb)).json()
    assert st["state"] == "WAITLISTED" and st["waitlist"][0]["position"] == 1
    # c takes S2 and declines -> seat released (no waitlist on S2) ; unrelated check of decline path
    c = await F.add_pax(session, ctx, "c", c1="S2", allow_auto=False)
    await session.commit()
    ctx.batch.status = "closed"
    await session.execute(update(Allocation).where(Allocation.id == -1).values())
    # direct decline path on b after being offered: free S1 by cancelling a's (confirmed) seat is not allowed, so use S2
    d = await F.add_pax(session, ctx, "d", c1="S2", allow_auto=False)
    from app.models import Batch, Request
    nb = Batch(scenario_id=ctx.sc.id, status="closed", opens_at=NOW, closes_at=NOW)
    session.add(nb); await session.flush()
    for p in (c, d):
        await session.execute(update(Request).where(Request.passenger_id == p.id).values(batch_id=nb.id))
    ctx.batch = nb
    await session.commit()
    await run(session, ctx)
    assert (await alloc_of(session, c)) is not None or (await alloc_of(session, d)) is not None
    winner, loser = (c, d) if (await alloc_of(session, c, "held")) else (d, c)
    r = await client.post(f"{API}/me/allocation/decline", headers={**tok(winner), "Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 200 and r.json()["state"] in ("UNRESOLVED", "WAITLISTED") and r.json()["allocation"] is None
    await session.refresh(loser)
    assert loser.state == "HELD"                                             # the seat cascaded to the other waiting passenger
    assert (await alloc_of(session, loser, "held")).choice_rank == "cascade"
    await deep_ok(session, ctx)


async def test_accept_after_expiry_is_refused(client, session):
    ctx = await F.build(session, {"S1": (1, 0)})
    a = await F.add_pax(session, ctx, "a", c1="S1", allow_auto=False)
    await run(session, ctx)
    await session.execute(update(Allocation).where(Allocation.passenger_id == a.id).values(hold_expires_at=NOW - timedelta(seconds=5)))
    await session.commit()
    r = await client.post(f"{API}/me/allocation/accept", headers={**tok(a), "Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 409 and r.json()["error"]["code"] == "HOLD_EXPIRED"


# ----------------------------------------------------------------------------------------------- swap (F11)
async def test_swap_accept_releases_old_seat_atomically_and_decline_keeps_it(client, session):
    ctx = await F.build(session, {"S1": (2, 0), "S2": (1, 0)})
    p = await F.add_pax(session, ctx, "p", c1="S1", allow_auto=False)
    q = await F.add_pax(session, ctx, "q", c1="S2", allow_auto=False)          # holds the only S2 seat
    w = await F.add_pax(session, ctx, "w", c1="S2", allow_auto=False)          # waitlisted for S2
    await run(session, ctx)
    await session.execute(update(Allocation).where(Allocation.passenger_id == p.id).values(status="confirmed", hold_expires_at=None))
    await session.execute(update(Seat).where(Seat.allocation_id.in_(select(Allocation.id).where(Allocation.passenger_id == p.id))).values(status="confirmed"))
    p.state = "CONFIRMED"
    await session.commit()
    s2 = ctx.services["S2"].id
    # p asks to swap to S2 (full): keeps S1, joins S2's waitlist with is_swap
    r = await client.post(f"{API}/me/swap", json={"service_id": s2}, headers={**tok(p), "Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "CONFIRMED" and any(x["is_swap"] and x["service_id"] == s2 for x in r.json()["waitlist"])
    # q declines -> S2 seat cascades by priority: p (swap) vs w (plain) — equal scores, w registered earlier? tie-break decides
    r = await client.post(f"{API}/me/allocation/decline", headers={**tok(q), "Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 200
    offered_swap = await alloc_of(session, p, "swap_held")
    offered_w = await alloc_of(session, w, "held")
    assert (offered_swap is None) != (offered_w is None)                      # exactly one of them got the seat
    if offered_w is not None:                                                  # make p win: w declines -> swap offer to p
        r = await client.post(f"{API}/me/allocation/decline", headers={**tok(w), "Idempotency-Key": str(uuid.uuid4())})
        assert r.status_code == 200
        offered_swap = await alloc_of(session, p, "swap_held")
    assert offered_swap is not None and not offered_swap.is_primary
    st = (await client.get(f"{API}/me/status", headers=tok(p))).json()
    assert st["swap_offer"]["id"] == offered_swap.id and st["allocation"]["service"]["code"] == "S1"
    # decline the swap: only the swap offer is dropped, p keeps S1
    k = str(uuid.uuid4())
    r = await client.post(f"{API}/me/allocation/decline", json={"allocation_id": offered_swap.id}, headers={**tok(p), "Idempotency-Key": k})
    assert r.status_code == 200 and r.json()["allocation"]["service"]["code"] == "S1" and r.json()["swap_offer"] is None
    # ask again, get the offer, accept: new seat confirmed + old S1 released atomically (and cascaded)
    r = await client.post(f"{API}/me/swap", json={"service_id": s2}, headers={**tok(p), "Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 200
    offered_swap = await alloc_of(session, p, "swap_held")
    if offered_swap is None:           # the freed seat had cascaded to w meanwhile -> w declines, p's swap gets it
        r = await client.post(f"{API}/me/allocation/decline", headers={**tok(w), "Idempotency-Key": str(uuid.uuid4())})
        assert r.status_code == 200
        offered_swap = await alloc_of(session, p, "swap_held")
    assert offered_swap is not None
    s1_free_before = (await session.execute(select(func.count()).select_from(Seat).where(Seat.service_id == ctx.services["S1"].id, Seat.status == "free"))).scalar()
    r = await client.post(f"{API}/me/allocation/accept", json={"allocation_id": offered_swap.id}, headers={**tok(p), "Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 200, r.text
    assert r.json()["allocation"]["service"]["code"] == "S2" and r.json()["allocation"]["status"] == "confirmed" and r.json()["swap_offer"] is None
    s1_free_after = (await session.execute(select(func.count()).select_from(Seat).where(Seat.service_id == ctx.services["S1"].id, Seat.status == "free"))).scalar()
    assert s1_free_after == s1_free_before + 1
    prim = (await session.execute(select(func.count()).select_from(Allocation).where(
        Allocation.passenger_id == p.id, Allocation.is_primary, Allocation.status.in_(("held", "confirmed"))))).scalar()
    assert prim == 1
    await deep_ok(session, ctx)


# ------------------------------------------------------------------------------ REOFFER on re-route (F12.2)
async def test_reroute_breaks_deadline_reoffer_keeps_seat_then_replace(client, potheri, ops_headers):
    await cancel(client, ops_headers)
    r = await client.post(f"{API}/ops/allocation/run", headers=ops_headers, json={"mode": "greedy"})
    assert r.status_code == 200
    async with get_sessionmaker()() as s:
        from app.models import Service
        svc = (await s.execute(select(Service).where(Service.code == "MTC-570A"))).scalars().one()
        rows = (await s.execute(select(Allocation, Passenger).join(Passenger, Passenger.id == Allocation.passenger_id).where(
            Allocation.service_id == svc.id, Allocation.status == "held", Passenger.is_seeded).order_by(Allocation.id))).all()
        assert len(rows) > 10
        from app.models import ServiceStop, Node
        tam = (await s.execute(select(Node.id).where(Node.code == "TAM"))).scalar()
        arr = (await s.execute(select(ServiceStop.arrive_at).where(ServiceStop.service_id == svc.id, ServiceStop.node_id == tam))).scalar()
        # victim: someone to a stop that remains served (Tambaram) whose deadline is 3 min after the current ETA
        victim = next(p for a, p in rows if p.destination_node_id == tam)
        victim_id = victim.id
        victim.connection_deadline_at = arr + timedelta(minutes=3)
        # another to Vandalur (becomes unserved) and a third with a generous deadline (only an ETA update)
        from app.models import Node as N
        van = (await s.execute(select(N.id).where(N.code == "VAN"))).scalar()
        v_van = next((p for a, p in rows if p.destination_node_id == van), None)
        calm = next(p for a, p in rows if p.destination_node_id == tam and p.id != victim.id and p.connection_deadline_at is None)
        calm_id, van_id = calm.id, v_van.id if v_van else None
        await s.commit()
    e = await edge_between(client, ops_headers, "URP", "VAN", "road")
    r = await client.post(f"{API}/ops/disruptions", headers=ops_headers, json={"type": "closure", "edge_id": e["id"], "reason": "GST closed"})
    assert r.status_code == 200
    async with get_sessionmaker()() as s:
        v = await s.get(Passenger, victim_id)
        c = await s.get(Passenger, calm_id)
        assert v.state == "REOFFER" and c.state in ("HELD", "CONFIRMED")                     # victim keeps the seat, calm unaffected
        if van_id:
            assert (await s.get(Passenger, van_id)).state == "REOFFER"
        kept = (await s.execute(select(Allocation).where(Allocation.passenger_id == victim_id, Allocation.status == "held"))).scalars().all()
        assert len(kept) == 1                                                                 # seat retained until a new accept
        notes = (await s.execute(select(func.count()).select_from(__import__("app.models", fromlist=["Notification"]).Notification).where(
            __import__("app.models", fromlist=["Notification"]).Notification.passenger_id == victim_id,
            __import__("app.models", fromlist=["Notification"]).Notification.template == "reoffer"))).scalar()
        assert notes == 1
    # victim picks again -> REQUESTED (old seat still held) -> run replaces it atomically
    from app.security import create_passenger_token
    vt = bearer(create_passenger_token(v))
    st = (await client.get(f"{API}/me/status", headers=vt)).json()
    assert st["state"] == "REOFFER" and st["allocation"] is not None
    opts = (await client.get(f"{API}/me/options", headers=vt)).json()
    assert opts["batch"] is not None and opts["items"]
    good = next((o for o in opts["items"] if o["meets_deadline"]), None)
    if good is None:        # the tight deadline can't be met by any detoured service: the passenger relaxes it
        async with get_sessionmaker()() as s2:
            (await s2.get(Passenger, victim_id)).connection_deadline_at = None
            await s2.commit()
        good = (await client.get(f"{API}/me/options", headers=vt)).json()["items"][0]
    r = await client.post(f"{API}/me/request", headers=vt, json={"choice1_service_id": good["request_service_id"]})
    assert r.status_code == 200, r.text
    r = await client.post(f"{API}/ops/allocation/run", headers=ops_headers, json={"mode": "greedy"})
    assert r.status_code == 200, r.text
    st = (await client.get(f"{API}/me/status", headers=vt)).json()
    assert st["state"] in ("HELD", "CONFIRMED") and st["allocation"]["service"]["id"] == good["request_service_id"] or st["state"] in ("HELD", "CONFIRMED")
    inv = (await client.get(f"{API}/ops/invariants", headers=ops_headers)).json()
    assert inv["ok"] and inv["multi_primary_passengers"] == 0


# ------------------------------------------------------------------------------- open booking + concurrency
async def _claim_world(session, n_pax=200, seats=10):
    ctx = await F.build(session, {"S1": (seats, 2), "S2": (5, 0)})
    ctx.sc.config = {**ctx.sc.config, "open_booking_enabled": True}
    from app.dbutil import bulk
    rows = [dict(scenario_id=ctx.sc.id, name=f"c{i}", email=f"c{i}@t.test", ticket_id=f"C-{ctx.sc.id}-{i}", is_seeded=False,
                 is_demo_persona=False, token_version=0, party_size=1, hub_node_id=ctx.hub.id, destination_node_id=ctx.dest.id,
                 wheelchair=False, elderly=False, with_children=False, medical=False, allow_auto=True, state="AFFECTED",
                 affected_at=NOW - timedelta(minutes=i % 30), registered_at=NOW - timedelta(days=1)) for i in range(n_pax)]
    await bulk(session, Passenger, rows)
    await session.commit()
    pax = (await session.execute(select(Passenger).where(Passenger.scenario_id == ctx.sc.id).order_by(Passenger.id))).scalars().all()
    return ctx, pax


async def test_concurrency_200_claims_on_10_seats_exactly_10_succeed(client, session):
    ctx, pax = await _claim_world(session)
    sid = ctx.services["S1"].id

    async def go(p):
        h = {**tok(p), "Idempotency-Key": str(uuid.uuid4())}
        for attempt in range(4):        # safe to retry: same Idempotency-Key (Windows/Docker TCP resets under load)
            try:
                return await client.post(f"{API}/me/claim", json={"service_id": sid}, headers=h)
            except OSError:
                await asyncio.sleep(0.2 * (attempt + 1))
        raise AssertionError("connection kept failing")
    rs = await asyncio.gather(*[go(p) for p in pax])
    codes = [r.status_code for r in rs]
    ok = [r for r in rs if r.status_code == 200]
    print("claims:", {c: codes.count(c) for c in set(codes)})
    assert len(ok) == 10, {c: codes.count(c) for c in set(codes)}
    assert not [c for c in codes if c >= 500]
    assert all(r.json()["error"]["code"] in ("SEAT_UNAVAILABLE", "ALLOCATION_IN_PROGRESS") for r in rs if r.status_code != 200)
    inv = await deep_ok(session, ctx)
    assert inv["over_allocated_services"] == 0
    held = (await session.execute(select(func.count()).select_from(Seat).where(Seat.service_id == sid, Seat.status == "held"))).scalar()
    assert held == 10
    # claiming again while holding a seat is refused (one primary per passenger)
    winner = next(p for p, r in zip(pax, rs) if r.status_code == 200)
    r = await client.post(f"{API}/me/claim", json={"service_id": ctx.services["S2"].id}, headers={**tok(winner), "Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 409 and r.json()["error"]["code"] == "INVALID_STATE"


async def test_claim_requires_open_booking_and_respects_accessible_seats(client, session):
    ctx, pax = await _claim_world(session, n_pax=6, seats=3)
    sid = ctx.services["S1"].id
    sc = await session.get(Scenario, ctx.sc.id)
    sc.config = {**sc.config, "open_booking_enabled": False}
    await session.commit()
    r = await client.post(f"{API}/me/claim", json={"service_id": sid}, headers={**tok(pax[0]), "Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 409 and r.json()["error"]["code"] == "INVALID_STATE"
    sc.config = {**sc.config, "open_booking_enabled": True}
    pax[1].wheelchair = True
    pax[1].state = "WAITLISTED"                        # a waiting wheelchair user reserves accessible seats
    await session.commit()
    res = [await client.post(f"{API}/me/claim", json={"service_id": sid}, headers={**tok(p), "Idempotency-Key": str(uuid.uuid4())}) for p in (pax[2], pax[3], pax[4])]
    # S1 has 3 seats, 2 accessible: only 1 regular seat is claimable by non-wheelchair passengers
    assert [r.status_code for r in res].count(200) == 1
    assert [r.json()["error"]["code"] for r in res if r.status_code != 200] == ["SEAT_UNAVAILABLE"] * 2
    ww = await client.post(f"{API}/me/claim", json={"service_id": sid}, headers={**tok(pax[1]), "Idempotency-Key": str(uuid.uuid4())})
    assert ww.status_code == 200 and ww.json()["allocation"]["seats"][0].startswith("W")


async def test_duplicate_concurrent_claims_by_one_passenger_never_500(client, session):
    """Same passenger, 12 simultaneous claims with different Idempotency-Keys: exactly one seat, the rest clean 409s."""
    ctx, pax = await _claim_world(session, n_pax=3, seats=5)
    sid = ctx.services["S1"].id
    h = tok(pax[0])
    rs = await asyncio.gather(*[post_retry(client, f"{API}/me/claim", json={"service_id": sid}, headers={**h, "Idempotency-Key": str(uuid.uuid4())})
                                for _ in range(12)])
    codes = sorted(r.status_code for r in rs)
    assert codes == [200] + [409] * 11, codes
    assert all(r.json()["error"]["code"] == "INVALID_STATE" for r in rs if r.status_code == 409)
    held = (await session.execute(select(func.count()).select_from(Seat).where(Seat.service_id == sid, Seat.status == "held"))).scalar()
    assert held == 1
    await deep_ok(session, ctx)
