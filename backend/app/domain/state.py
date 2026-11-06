"""Passenger journey state machine (PRD §5.6). The ONLY place that mutates ``Passenger.state``."""
from __future__ import annotations

from app.dbutil import in_ids
from app.errors import AppError
from app.models import Passenger

ALLOWED: dict[str, set[str]] = {
    "REGISTERED": {"BOOKED", "AFFECTED"},
    "BOOKED": {"AFFECTED", "BOOKED"},
    "AFFECTED": {"REQUESTED", "AFFECTED", "HELD", "BOOKED", "RESOLVED_ALT"},
    "REQUESTED": {"REQUESTED", "HELD", "WAITLISTED", "UNRESOLVED", "AFFECTED", "RESOLVED_ALT"},
    "HELD": {"CONFIRMED", "WAITLISTED", "UNRESOLVED", "AFFECTED", "REOFFER", "REQUESTED", "HELD"},
    "CONFIRMED": {"REOFFER", "AFFECTED", "CONFIRMED"},
    "WAITLISTED": {"HELD", "UNRESOLVED", "RESOLVED_ALT", "REQUESTED", "WAITLISTED", "AFFECTED"},
    "UNRESOLVED": {"RESOLVED_ALT", "REQUESTED", "HELD", "WAITLISTED", "UNRESOLVED", "AFFECTED"},
    "RESOLVED_ALT": {"AFFECTED", "REQUESTED"},
    "REOFFER": {"REQUESTED", "HELD", "CONFIRMED", "REOFFER", "AFFECTED", "WAITLISTED", "UNRESOLVED"},
}
STATES = set(ALLOWED)
EDITABLE_STATES = {"REGISTERED", "BOOKED", "AFFECTED"}
# states in which the passenger may (re)submit a request into a batch
REQUESTABLE = {"AFFECTED", "REQUESTED", "REOFFER", "WAITLISTED", "UNRESOLVED"}


def can(from_state: str, to_state: str) -> bool:
    return to_state in ALLOWED.get(from_state, set())


def transition(p: Passenger, to_state: str, *, force: bool = False) -> bool:
    """Move ``p`` to ``to_state``; raises ``409 INVALID_STATE`` on an illegal edge.
    ``force`` is reserved for administrative resets (persona release, scenario reset).
    Returns True when the state actually changed."""
    if to_state not in STATES:
        raise ValueError(f"unknown passenger state {to_state}")
    if p.state == to_state:
        return False
    if not force and not can(p.state, to_state):
        raise AppError("INVALID_STATE", f"Cannot go from {p.state} to {to_state}",
                       {"from": p.state, "to": to_state})
    p.state = to_state
    return True


async def bulk_transition(session, ids: list[int], to_state: str, from_states: set[str] | None = None,
                          **extra) -> list[int]:
    """Set-based state change for many passengers (still validated against the table): only passengers whose
    current state may legally move to ``to_state`` (and are in ``from_states`` when given) are updated.
    Returns the ids actually changed."""
    from sqlalchemy import update
    legal = {s for s, tos in ALLOWED.items() if to_state in tos}
    if from_states is not None:
        legal &= from_states
    if not ids or not legal:
        return []
    res = await session.execute(
        update(Passenger).where(in_ids(Passenger.id, ids), Passenger.state.in_(legal)).values(state=to_state, **extra)
        .returning(Passenger.id))
    return [r[0] for r in res.all()]


async def force_state(session, ids: list[int], to_state: str) -> None:
    """Engine/administrative set-based state change (the allocation engine has already decided the outcome)."""
    from sqlalchemy import update
    if to_state not in STATES:
        raise ValueError(to_state)
    if ids:
        await session.execute(update(Passenger).where(in_ids(Passenger.id, ids)).values(state=to_state))


async def force_states(session, by_state: dict[str, list[int]]) -> None:
    """Many state changes in ONE statement: {state: [passenger ids]} (engine decisions)."""
    import json

    from sqlalchemy import text
    rows = [{"id": i, "s": st} for st, ids in by_state.items() for i in ids]
    for st in by_state:
        if st not in STATES:
            raise ValueError(st)
    if rows:
        await session.execute(text(
            "UPDATE passengers p SET state = CAST(v.s AS passenger_state) "
            "FROM jsonb_to_recordset(CAST(:d AS jsonb)) AS v(id bigint, s text) WHERE p.id = v.id"),
            {"d": json.dumps(rows)})
