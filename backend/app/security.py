"""JWT, bcrypt, login-QR tokens, auth dependencies, in-memory rate limiter (PRD §2, F2)."""
from __future__ import annotations

import asyncio
import hashlib
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta

import bcrypt
import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.config import get_settings
from app.db import get_session
from app.errors import AppError
from app.models import Passenger

_bearer = HTTPBearer(auto_error=False)
ALGO = "HS256"


# ---- passwords ------------------------------------------------------------------------------
def hash_password_sync(pw: str, rounds: int = 10) -> str:
    return bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt(rounds)).decode()


def verify_password_sync(pw: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(pw.encode()[:72], hashed.encode())
    except ValueError:
        return False


async def hash_password(pw: str) -> str:
    return await asyncio.to_thread(hash_password_sync, pw)


async def verify_password(pw: str, hashed: str | None) -> bool:
    return await asyncio.to_thread(verify_password_sync, pw, hashed)


# ---- JWT ------------------------------------------------------------------------------------
def _encode(payload: dict) -> str:
    s = get_settings()
    now = clock.utcnow()
    payload = {**payload, "iat": int(now.timestamp()),
               "exp": int((now + timedelta(hours=s.JWT_TTL_HOURS)).timestamp())}
    return jwt.encode(payload, s.JWT_SECRET, algorithm=ALGO)


def create_passenger_token(p: Passenger) -> str:
    return _encode({"sub": str(p.id), "role": "passenger", "tv": p.token_version, "sid": p.scenario_id})


def create_ops_token() -> str:
    return _encode({"sub": "operator", "role": "operator"})


def decode_token(token: str) -> dict:
    try:
        # real-time expiry check uses wall clock; the frozen test clock must not expire tokens
        return jwt.decode(token, get_settings().JWT_SECRET, algorithms=[ALGO], options={"verify_exp": False,
                                                                                         "verify_iat": False})
    except jwt.PyJWTError:
        raise AppError("UNAUTHORIZED", "Invalid or expired token")


def _check_exp(claims: dict) -> None:
    if claims.get("exp") and claims["exp"] < clock.utcnow().timestamp():
        raise AppError("UNAUTHORIZED", "Session expired")


# ---- login QR tokens ---------------------------------------------------------------------------
def new_qr_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, hash_qr_token(raw)


def hash_qr_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# ---- dependencies ---------------------------------------------------------------------------
def _claims(creds: HTTPAuthorizationCredentials | None) -> dict:
    if creds is None or not creds.credentials:
        raise AppError("UNAUTHORIZED", "Missing bearer token")
    claims = decode_token(creds.credentials)
    _check_exp(claims)
    return claims


async def current_passenger(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> Passenger:
    claims = _claims(creds)
    if claims.get("role") != "passenger":
        raise AppError("FORBIDDEN", "Passenger token required")
    p = await session.get(Passenger, int(claims["sub"]))
    if p is None or p.token_version != claims.get("tv"):
        raise AppError("UNAUTHORIZED", "Session ended")
    return p


async def require_ops(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    claims = _claims(creds)
    if claims.get("role") != "operator":
        raise AppError("FORBIDDEN", "Operator token required")
    return claims


def token_from_query(token: str | None) -> dict:
    """WebSocket auth: ``?token=``."""
    if not token:
        raise AppError("UNAUTHORIZED", "Missing token")
    claims = decode_token(token)
    _check_exp(claims)
    return claims


# ---- rate limiting --------------------------------------------------------------------------
class RateLimiter:
    """Sliding-window limiter keyed by client IP. In-process (single instance, PRD D11)."""

    def __init__(self, name: str, limit_getter):
        self.name = name
        self.limit_getter = limit_getter
        self.hits: dict[str, deque] = defaultdict(deque)

    @staticmethod
    def parse(spec: str) -> tuple[int, int]:
        n, per = spec.split("/")
        return int(n), {"second": 1, "minute": 60, "hour": 3600}[per]

    def reset(self) -> None:
        self.hits.clear()

    async def __call__(self, request: Request) -> None:
        limit, window = self.parse(self.limit_getter())
        fwd = request.headers.get("x-forwarded-for")
        ip = fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")
        now = time.monotonic()
        q = self.hits[ip]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            raise AppError("RATE_LIMITED", "Too many attempts, wait a moment")
        q.append(now)


register_limiter = RateLimiter("register", lambda: get_settings().REGISTER_RATE_LIMIT)
auth_limiter = RateLimiter("auth", lambda: get_settings().AUTH_RATE_LIMIT)
