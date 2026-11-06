"""Read-only scenario snapshot (nodes, services, stops) shared by routing, options and serializers."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import defer
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Node, Scenario, Seat, Service, ServiceStop


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


class Snapshot:
    def __init__(self, scenario: Scenario, nodes: dict[int, Node], services: dict[int, Service],
                 stops: dict[int, list[ServiceStop]]):
        self.scenario = scenario
        self.nodes = nodes
        self.services = services
        self.stops = stops
        self._by_code = {s.code: s for s in services.values()}
        self._served: dict[int, list[ServiceStop]] = {}
        self._index: dict[int, dict[int, int]] = {}
        self._sum: dict[int, dict[str, Any]] = {}

    @classmethod
    async def load(cls, session: AsyncSession, scenario: Scenario, *, polylines: bool = False) -> "Snapshot":
        """``polylines=False`` (default) defers the big GeoJSON columns: decoding ~1300-point JSON for every service
        on every request used to dominate request CPU. Pass True where geometry is needed (map, vehicles)."""
        nodes = {n.id: n for n in (await session.execute(select(Node).where(Node.scenario_id == scenario.id))).scalars()}
        q = select(Service).where(Service.scenario_id == scenario.id).order_by(Service.id)
        if not polylines:
            q = q.options(defer(Service.polyline))
        services = {s.id: s for s in (await session.execute(q)).scalars()}
        stops: dict[int, list[ServiceStop]] = {sid: [] for sid in services}
        rows = (await session.execute(
            select(ServiceStop).join(Service, Service.id == ServiceStop.service_id)
            .where(Service.scenario_id == scenario.id).order_by(ServiceStop.service_id, ServiceStop.seq))).scalars()
        for st in rows:
            stops[st.service_id].append(st)
        return cls(scenario, nodes, services, stops)

    # -- nodes
    def node_ref(self, node_id: int) -> dict[str, Any]:
        n = self.nodes[node_id]
        return {"id": n.id, "code": n.code, "name": n.name, "lat": n.lat, "lng": n.lng, "kind": n.kind,
                "is_hub": n.is_hub, "is_default_hub": n.is_default_hub}

    def code_to_node(self, code: str) -> Node | None:
        return next((n for n in self.nodes.values() if n.code == code), None)

    # -- services
    def by_code(self, code: str) -> Service | None:
        return self._by_code.get(code)

    def served(self, sid: int) -> list[ServiceStop]:  # cached
        """Boarding stops in order (via and skipped stops excluded)."""
        if sid not in self._served:
            self._served[sid] = [s for s in self.stops.get(sid, []) if not s.is_via and not s.is_skipped]
        return self._served[sid]

    def endpoints(self, sid: int) -> tuple[int, int]:
        st = self.served(sid) or self.stops[sid]
        return st[0].node_id, st[-1].node_id

    def stop_at(self, sid: int, node_id: int) -> ServiceStop | None:
        return next((s for s in self.served(sid) if s.node_id == node_id), None)

    def index(self, sid: int) -> dict[int, int]:
        if sid not in self._index:
            self._index[sid] = {s.node_id: i for i, s in enumerate(self.served(sid))}
        return self._index[sid]

    def serves_in_order(self, sid: int, from_node: int, to_node: int) -> tuple[ServiceStop, ServiceStop] | None:
        idx = self.index(sid)
        a, b = idx.get(from_node), idx.get(to_node)
        if a is not None and b is not None and a < b:
            st = self.served(sid)
            return st[a], st[b]
        return None

    def summary(self, sid: int) -> dict[str, Any]:
        """ServiceSummary dict (memoised per snapshot; callers must treat it as read-only)."""
        if sid not in self._sum:
            self._sum[sid] = self._summary(sid)
        return self._sum[sid]

    def _summary(self, sid: int) -> dict[str, Any]:
        s = self.services[sid]
        o, d = self.endpoints(sid)
        return {"id": s.id, "code": s.code, "label": s.label, "mode": s.mode, "status": s.status,
                "delay_minutes": s.delay_minutes, "depart_at": iso(s.depart_at), "arrive_at": iso(s.arrive_at),
                "origin": self.node_ref(o), "destination": self.node_ref(d),
                "accessible": bool(s.has_seat_inventory and s.accessible_seats > 0)}

    def effective(self, dt: datetime, sid: int) -> datetime:
        return dt + timedelta(minutes=self.services[sid].delay_minutes or 0)


def linestring(coords: list | None) -> dict[str, Any] | None:
    return {"type": "LineString", "coordinates": coords or []}


async def seat_counts(session: AsyncSession, service_ids: list[int]) -> dict[int, dict[str, int]]:
    """{service_id: {total, free, accessible_free, held, confirmed}}"""
    out = {sid: {"total": 0, "free": 0, "accessible_free": 0, "held": 0, "confirmed": 0} for sid in service_ids}
    if not service_ids:
        return out
    rows = await session.execute(
        select(Seat.service_id, Seat.status, Seat.is_accessible, func.count())
        .where(Seat.service_id.in_(service_ids)).group_by(Seat.service_id, Seat.status, Seat.is_accessible))
    for sid, status, acc, n in rows.all():
        o = out[sid]
        o["total"] += n
        o[status] += n
        if status == "free" and acc:
            o["accessible_free"] += n
    return out
