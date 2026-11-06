"""Notifications (PRD F21): DB row + WS push (`notification.created`); channel `email_sim` by default,
optional real SMS through Twilio's REST API for *registered judges only* (never seeded)."""
from __future__ import annotations

from typing import Any

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Notification, Passenger
from app.serializers import notification_out
from app.ws.events import Event

log = structlog.get_logger()

# template -> (title, body)  (str.format with ctx; missing keys render as '…')
TEMPLATES: dict[str, tuple[str, str]] = {
    "disruption_alert": ("Your train is cancelled", "{message} Choose an alternative now."),
    "batch_open": ("Requests are open", "Choose your 1st/2nd option. Requests close at {closes}."),
    "placed": ("You have a seat", "Placed on {service} ({seats}). Accept within {minutes} min."),
    "moved": ("You were moved", "Moved to {service} ({seats}). {why}"),
    "waitlisted": ("You're on the waitlist", "Waitlisted #{position} for {service}. We'll offer a seat the moment one frees up."),
    "offer_cascade": ("A seat opened up for you!", "Seat on {service} ({seats}). Accept within {minutes} min."),
    "hold_expiring": ("Your hold is about to expire", "Your seat on {service} expires in {seconds} s - accept it now."),
    "expired": ("Your hold expired", "Your hold on {service} expired and the seat was released."),
    "eta_updated": ("Arrival time updated", "{service} now arrives at {eta}."),
    "reoffer": ("Please choose again", "{service} was re-routed and may miss your deadline. You keep your seat until you choose."),
    "swap_offer": ("Your preferred option has a seat", "{service} has a seat for you. Switch within {minutes} min."),
    "pod_update": ("Shared cab update", "{message}"),
    "unresolved": ("No seat yet", "We could not place you yet. See alternatives such as shared cabs and later services."),
    "confirmed": ("You're confirmed", "Seat confirmed on {service} ({seats})."),
}


class _Safe(dict):
    def __missing__(self, k):
        return "…"


def render(template: str, ctx: dict[str, Any]) -> tuple[str, str]:
    title, body = TEMPLATES[template]
    return title.format_map(_Safe(ctx)), body.format_map(_Safe(ctx))


def make(p: Passenger, template: str, ctx: dict[str, Any] | None = None, *, channel: str = "email_sim",
         body: str | None = None, title: str | None = None) -> Notification:
    """Build (not yet persisted) notification row for ``p``."""
    from app import clock
    ctx = ctx or {}
    t, b = render(template, ctx) if template in TEMPLATES else (template, "")
    return Notification(scenario_id=p.scenario_id, passenger_id=p.id, channel=channel, template=template,
                        title=title or t, body=body or b, payload={k: str(v) for k, v in ctx.items()},
                        status="sent", read=False, created_at=clock.utcnow())


async def emit(session: AsyncSession, notes: list[Notification]) -> list[Event]:
    """Persist notifications (one bulk statement) and return their `notification.created` events."""
    if not notes:
        return []
    from app.dbutil import bulk
    rows = [dict(scenario_id=n.scenario_id, passenger_id=n.passenger_id, channel=n.channel, template=n.template,
                 title=n.title, body=n.body, payload=n.payload, status=n.status, read=n.read,
                 created_at=n.created_at) for n in notes]
    ids = [r[0] for r in await bulk(session, Notification, rows, (Notification.id,))]
    for n, i in zip(notes, ids):
        n.id = i
    return [Event("notification.created", notification_out(n), passengers=(n.passenger_id,), dirty_kpi=False)
            for n in notes]


async def maybe_send_sms(p: Passenger, text: str) -> None:
    s = get_settings()
    if not (s.TWILIO_ENABLED and s.TWILIO_SID and p.phone) or p.is_seeded or p.is_demo_persona:
        return
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            await c.post(f"https://api.twilio.com/2010-04-01/Accounts/{s.TWILIO_SID}/Messages.json",
                         auth=(s.TWILIO_SID, s.TWILIO_TOKEN), data={"From": s.TWILIO_FROM, "To": p.phone, "Body": text})
    except Exception:  # noqa: BLE001 - never break a request because SMS failed
        log.warning("twilio_failed", passenger_id=p.id)
