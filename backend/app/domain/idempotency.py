"""`Idempotency-Key` handling for mutating passenger actions (PRD §9.4, contract §3)."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError


def key_of(request: Request) -> str:
    k = request.headers.get("idempotency-key")
    if not k or len(k) > 128:
        raise AppError("VALIDATION_ERROR", "Idempotency-Key header is required",
                       {"fields": {"Idempotency-Key": "required (uuid v4)"}})
    return k


async def claim_key(session: AsyncSession, key: str, passenger_id: int, endpoint: str) -> dict[str, Any] | None:
    """Reserve the key inside the caller's transaction. Returns the stored response when this is a replay.
    A concurrent request with the same key blocks on the unique index until the first one commits; it then
    replays the stored response. A key re-used for a different endpoint -> IDEMPOTENCY_CONFLICT."""
    res = await session.execute(text(
        "INSERT INTO idempotency_keys (key, passenger_id, endpoint, response, created_at) "
        "VALUES (:k, :p, :e, NULL, now()) ON CONFLICT (key, passenger_id) DO NOTHING RETURNING key"),
        {"k": key, "p": passenger_id, "e": endpoint})
    if res.first() is not None:
        return None
    row = (await session.execute(text("SELECT endpoint, response FROM idempotency_keys WHERE key=:k AND passenger_id=:p"),
                                 {"k": key, "p": passenger_id})).first()
    if row is None or row[0] != endpoint:
        raise AppError("IDEMPOTENCY_CONFLICT", "That Idempotency-Key was used for a different action")
    if row[1] is None:
        raise AppError("IDEMPOTENCY_CONFLICT", "A request with this Idempotency-Key is still in progress")
    return row[1]


async def store_response(session: AsyncSession, key: str, passenger_id: int, response: dict[str, Any]) -> None:
    import json
    await session.execute(text("UPDATE idempotency_keys SET response = CAST(:r AS jsonb) WHERE key=:k AND passenger_id=:p"),
                          {"r": json.dumps(response, default=str), "k": key, "p": passenger_id})
