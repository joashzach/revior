"""Journey search: direct + multi-leg options for a passenger (PRD F4.2–F4.3, §10.2)."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any

from app.domain.snapshot import Snapshot, iso
from app.models import Passenger

TRANSFER_MIN = 10          # minimum minutes between legs (transfer penalty)
MAX_MULTI_LEG = 5
# a service that has already left its ORIGIN may still be ahead of the passenger's hub (hub departure >= now is checked)
OK_STATUS = ("scheduled", "delayed", "rerouted", "running")


@dataclass
class OptionData:
    key: str
    request_sid: int
    legs: list[tuple[int, int, int]]          # (service_id, from_node, to_node)
    depart_at: datetime                        # effective departure from the hub
    eta_at: datetime
    transfers: int
    label: str
    mode: str
    seats_left: int = 0
    accessible_left: int = 0
    is_full: bool = False
    meets_deadline: bool = True
    accessible: bool = False

    @property
    def is_multi_leg(self) -> bool:
        return len(self.legs) > 1


def _operating(snap: Snapshot, sid: int) -> bool:
    return snap.services[sid].status in OK_STATUS


def compute_options(snap: Snapshot, p: Passenger, now: datetime, counts: dict[int, dict[str, int]] | None = None,
                    *, hub_id: int | None = None, dest_id: int | None = None,
                    cache: dict | None = None) -> list[OptionData]:
    """All seat-bearing alternatives from hub -> destination, ranked by (ETA, transfers, id).

    Direct: inventory service that stops at hub then destination. Multi-leg (<=1 transfer): inventory leg1
    hub->T plus any leg2 T->dest departing >= leg1 arrival + 10 min. Wheelchair passengers only see services
    with accessible seats. Options that miss the connection deadline are returned with
    ``meets_deadline=False`` (the request endpoint refuses them)."""
    hub = hub_id or p.hub_node_id
    dest = dest_id or p.destination_node_id
    counts = counts or {}
    base_key = (hub, dest, bool(p.wheelchair))
    if cache is not None and base_key in cache:           # the journey search is identical for this key
        return _decorate(snap, p, [replace(o) for o in cache[base_key]], counts)
    out: list[OptionData] = []

    def eff(dt: datetime, sid: int) -> datetime:
        return snap.effective(dt, sid)

    direct_ids: set[int] = set()
    for sid, sv in snap.services.items():
        if not sv.has_seat_inventory or not _operating(snap, sid):
            continue
        if p.wheelchair and sv.accessible_seats <= 0:
            continue
        pair = snap.serves_in_order(sid, hub, dest)
        if not pair:
            continue
        dep = eff(pair[0].depart_at, sid)
        if dep < now:
            continue
        direct_ids.add(sid)
        out.append(OptionData(f"S{sid}", sid, [(sid, hub, dest)], dep, eff(pair[1].arrive_at, sid), 0, sv.label, sv.mode))

    # multi-leg: leg1 inventory hub -> T, leg2 T -> dest
    multi: list[OptionData] = []
    for sid, sv in snap.services.items():
        if sid in direct_ids or not sv.has_seat_inventory or not _operating(snap, sid):
            continue
        if p.wheelchair and sv.accessible_seats <= 0:
            continue
        st1 = snap.served(sid)
        ids1 = [s.node_id for s in st1]
        if hub not in ids1:
            continue
        hub_stop = st1[ids1.index(hub)]
        dep = eff(hub_stop.depart_at, sid)
        if dep < now:
            continue
        best: tuple[datetime, int, int, Any, Any] | None = None
        for t_stop in st1[ids1.index(hub) + 1:]:
            T = t_stop.node_id
            if T == dest:
                continue
            arr1 = eff(t_stop.arrive_at, sid)
            for sid2, sv2 in snap.services.items():
                if sid2 == sid or not _operating(snap, sid2):
                    continue
                pair2 = snap.serves_in_order(sid2, T, dest)
                if not pair2:
                    continue
                dep2 = eff(pair2[0].depart_at, sid2)
                if dep2 < arr1 + timedelta(minutes=TRANSFER_MIN):
                    continue
                arr2 = eff(pair2[1].arrive_at, sid2)
                cand = (arr2, sid2, T, t_stop, pair2)
                if best is None or (arr2, sid2) < (best[0], best[1]):
                    best = cand
        if best:
            arr2, sid2, T, t_stop, pair2 = best
            sv2 = snap.services[sid2]
            multi.append(OptionData(
                f"S{sid}+S{sid2}", sid,
                [(sid, hub, T), (sid2, T, dest)], dep, arr2, 1,
                f"{sv.label} + {sv2.label} (change at {snap.nodes[T].name})", sv.mode))
    multi.sort(key=lambda o: (o.eta_at, o.request_sid))
    out += multi[:MAX_MULTI_LEG]
    if cache is not None:
        cache[base_key] = [replace(o) for o in out]
    return _decorate(snap, p, out, counts)


def _decorate(snap: Snapshot, p: Passenger, out: list[OptionData], counts: dict) -> list[OptionData]:
    for o in out:
        sv = snap.services[o.request_sid]
        c = counts.get(o.request_sid)
        o.seats_left = c["free"] if c else sv.total_seats
        o.accessible_left = c["accessible_free"] if c else sv.accessible_seats
        o.is_full = o.seats_left < p.party_size or (p.wheelchair and o.accessible_left < 1)
        o.meets_deadline = p.connection_deadline_at is None or o.eta_at <= p.connection_deadline_at
        o.accessible = sv.accessible_seats > 0
    out.sort(key=lambda o: (o.eta_at, o.transfers, o.request_sid))
    return out


def leg_dict(snap: Snapshot, sid: int, a: int, b: int) -> dict[str, Any]:
    sv = snap.services[sid]
    sa, sb = snap.stop_at(sid, a), snap.stop_at(sid, b)
    return {"service": snap.summary(sid), "from": snap.node_ref(a), "to": snap.node_ref(b),
            "depart_at": iso(snap.effective(sa.depart_at, sid)), "arrive_at": iso(snap.effective(sb.arrive_at, sid)),
            "has_seats": bool(sv.has_seat_inventory)}


def option_dict(snap: Snapshot, o: OptionData) -> dict[str, Any]:
    return {"option_id": o.key, "request_service_id": o.request_sid, "label": o.label, "mode": o.mode,
            "legs": [leg_dict(snap, *leg) for leg in o.legs], "depart_at": iso(o.depart_at), "eta_at": iso(o.eta_at),
            "transfers": o.transfers, "is_multi_leg": o.is_multi_leg, "seats_left": o.seats_left,
            "accessible_seats_left": o.accessible_left, "is_full": o.is_full, "meets_deadline": o.meets_deadline,
            "accessible": o.accessible}


def requestable(options: list[OptionData]) -> dict[int, OptionData]:
    """request_service_id -> option, for options a passenger may legally choose (deadline respected)."""
    return {o.request_sid: o for o in options if o.meets_deadline}
