"""Event model + catalogue (contract §6). Domain code *returns* events; routers publish them
only after the transaction commits (PRD §9.5)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# every event type in the contract
EVENT_TYPES = [
    "service.status_changed", "disruption.created", "disruption.resolved", "batch.opened", "batch.closed",
    "allocation.run_started", "allocation.run_completed", "allocation.result", "offer.created",
    "swap.offer_created", "hold.expiring", "hold.expired", "allocation.confirmed", "allocation.declined",
    "seat.released", "waitlist.position_changed", "eta.updated", "service.rerouted", "vehicle.positions",
    "kpi.updated", "rules.updated", "pod.updated", "passenger.registered", "persona.claimed",
    "persona.released", "notification.created", "stress.progress", "stress.result",
]


@dataclass
class Event:
    type: str
    data: dict[str, Any]
    ops: bool = False                                  # deliver to every operator socket
    passengers: tuple[int, ...] = ()                   # deliver to these passenger ids
    all_passengers: bool = False                       # deliver to every connected passenger
    scenario: str | None = None                        # filled by the publisher when None
    dirty_kpi: bool = True                             # mark the KPI snapshot dirty


EventList = list[Event]


def ev(type_: str, data: dict[str, Any], *, ops: bool = False, to: list[int] | tuple[int, ...] = (),
       everyone: bool = False, kpi: bool = True) -> Event:
    return Event(type_, data, ops=ops, passengers=tuple(dict.fromkeys(to)), all_passengers=everyone, dirty_kpi=kpi)
