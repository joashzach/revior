"""Single source of 'now' so tests can freeze time (determinism tests)."""
from datetime import datetime, timezone

_override: datetime | None = None


def utcnow() -> datetime:
    return _override or datetime.now(timezone.utc)


def freeze(dt: datetime | None) -> None:
    global _override
    _override = dt
