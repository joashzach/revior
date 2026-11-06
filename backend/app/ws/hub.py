"""In-process pub/sub + connection manager (PRD §4, D11, contract §6)."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field

import structlog

from app import clock
from app.ws.events import Event

log = structlog.get_logger()


@dataclass(eq=False)
class Connection:
    role: str
    scenario_id: int
    passenger_id: int | None = None
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=2000))


class Hub:
    def __init__(self) -> None:
        self.ops: set[Connection] = set()
        self.passengers: dict[int, set[Connection]] = defaultdict(set)
        self.kpi_dirty: dict[str, bool] = {}   # scenario slug -> dirty
        self.published: list[dict] = []        # ring buffer, used by tests/demo script
        self.record = False

    # -- registry
    def add(self, c: Connection) -> None:
        if c.role == "operator":
            self.ops.add(c)
        else:
            self.passengers[c.passenger_id].add(c)

    def remove(self, c: Connection) -> None:
        if c.role == "operator":
            self.ops.discard(c)
        else:
            s = self.passengers.get(c.passenger_id)
            if s:
                s.discard(c)
                if not s:
                    self.passengers.pop(c.passenger_id, None)

    def connected_passenger_ids(self) -> list[int]:
        return list(self.passengers.keys())

    def disconnect_passenger(self, passenger_id: int) -> None:
        """Close sockets of a passenger whose token was invalidated."""
        for c in list(self.passengers.get(passenger_id, ())):
            c.queue.put_nowait(None)

    # -- delivery
    @staticmethod
    def envelope(e: Event, scenario: str) -> dict:
        return {"type": e.type, "ts": clock.utcnow().isoformat(), "scenario": scenario, "data": e.data}

    def _push(self, c: Connection, msg: dict) -> None:
        try:
            c.queue.put_nowait(msg)
        except asyncio.QueueFull:  # slow client: drop (events are not replayed anyway)
            log.warning("ws_queue_full", role=c.role, passenger_id=c.passenger_id)

    async def publish(self, events: list[Event], scenario: str) -> None:
        for e in events:
            msg = self.envelope(e, scenario)
            if self.record:
                self.published.append({**msg, "_ops": e.ops, "_to": list(e.passengers), "_all": e.all_passengers})
                del self.published[:-5000]
            if e.ops:
                for c in list(self.ops):
                    self._push(c, msg)
            if e.all_passengers:
                for conns in list(self.passengers.values()):
                    for c in list(conns):
                        self._push(c, msg)
            else:
                for pid in e.passengers:
                    for c in list(self.passengers.get(pid, ())):
                        self._push(c, msg)
            if e.dirty_kpi:
                self.kpi_dirty[scenario] = True

    def take_dirty(self) -> list[str]:
        out = [s for s, d in self.kpi_dirty.items() if d]
        for s in out:
            self.kpi_dirty[s] = False
        return out


hub = Hub()
