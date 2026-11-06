"""ORM -> contract-shaped dicts (validated again by the response models)."""
from __future__ import annotations

from typing import Any

from app.domain.snapshot import Snapshot, iso
from app.models import Batch, Notification, Passenger


def needs_dict(p: Passenger) -> dict[str, Any]:
    return {"wheelchair": p.wheelchair, "elderly": p.elderly, "with_children": p.with_children,
            "medical": p.medical, "connection_deadline_at": iso(p.connection_deadline_at)}


def passenger_out(p: Passenger, snap: Snapshot) -> dict[str, Any]:
    return {
        "id": p.id, "name": p.name, "email": p.email, "phone": p.phone, "is_seeded": p.is_seeded,
        "is_demo_persona": p.is_demo_persona, "hub": snap.node_ref(p.hub_node_id),
        "destination": snap.node_ref(p.destination_node_id), "party_size": p.party_size,
        "needs": needs_dict(p), "allow_auto": p.allow_auto, "state": p.state, "ticket_id": p.ticket_id,
        "affected_at": iso(p.affected_at),
    }


def ticket_out(p: Passenger, snap: Snapshot) -> dict[str, Any] | None:
    if p.ticket_service_id is None or p.ticket_service_id not in snap.services:
        return None
    return {"ticket_id": p.ticket_id, "service": snap.summary(p.ticket_service_id)}


def batch_out(b: Batch) -> dict[str, Any]:
    return {"id": b.id, "status": b.status, "opens_at": iso(b.opens_at), "closes_at": iso(b.closes_at)}


def persona_out(p: Passenger, snap: Snapshot) -> dict[str, Any]:
    return {"id": p.id, "title": p.persona_title or p.name, "emoji": p.persona_emoji or "🙂",
            "summary": p.persona_summary or "", "destination": snap.node_ref(p.destination_node_id),
            "party_size": p.party_size, "needs": needs_dict(p), "is_taken": p.persona_claimed_at is not None}


def notification_out(n: Notification) -> dict[str, Any]:
    return {"id": n.id, "template": n.template, "title": n.title, "body": n.body,
            "created_at": iso(n.created_at), "read": n.read}


def allocation_dict(snap: Snapshot, alloc_id: int, service_id: int, seat_count: int, seats: list[str], rank: str,
                    status: str, is_primary: bool, hold_expires_at, score: float, explanation: str) -> dict[str, Any]:
    return {"id": alloc_id, "service": snap.summary(service_id), "seat_count": seat_count, "seats": seats,
            "choice_rank": rank, "status": status, "is_primary": is_primary, "hold_expires_at": iso(hold_expires_at),
            "score": float(score), "explanation": explanation}
