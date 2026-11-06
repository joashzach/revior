"""Async engine/session + advisory lock helpers (PRD §9)."""
import hashlib
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        # Direct (session-mode) connection; pool 10–20 per PRD §9.8.
        _engine = create_async_engine(
            get_settings().DATABASE_URL,
            pool_size=get_settings().DB_POOL_SIZE,
            max_overflow=get_settings().DB_MAX_OVERFLOW,
            pool_timeout=get_settings().DB_POOL_TIMEOUT,
            pool_pre_ping=True,
            connect_args={"server_settings": {"jit": "off"}},  # JIT adds 100-200 ms to first big statements
        )
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
        slow = get_settings().SQL_SLOW_MS
        if slow > 0:
            import time

            import structlog
            from sqlalchemy import event

            log = structlog.get_logger("sql")

            @event.listens_for(_engine.sync_engine, "before_cursor_execute")
            def _before(conn, cur, stmt, params, ctx, many):
                conn.info["t0"] = time.perf_counter()

            @event.listens_for(_engine.sync_engine, "after_cursor_execute")
            def _after(conn, cur, stmt, params, ctx, many):
                ms = (time.perf_counter() - conn.info.get("t0", time.perf_counter())) * 1000
                if ms >= slow:
                    log.warning("slow_sql", ms=round(ms), stmt=" ".join(stmt.split())[:140])
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request."""
    async with get_sessionmaker()() as session:
        yield session


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def check_db() -> bool:
    try:
        async with get_sessionmaker()() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def advisory_key(namespace: str, scenario_id: int) -> int:
    """Stable signed 64-bit key for pg advisory locks, e.g. ('alloc', 1)."""
    digest = hashlib.sha256(f"{namespace}:{scenario_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


async def acquire_xact_lock(session: AsyncSession, namespace: str, scenario_id: int) -> None:
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:k)"), {"k": advisory_key(namespace, scenario_id)}
    )


async def try_xact_lock(session: AsyncSession, namespace: str, scenario_id: int) -> bool:
    res = await session.execute(
        text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": advisory_key(namespace, scenario_id)}
    )
    return bool(res.scalar())


async def acquire_xact_lock_shared(session: AsyncSession, namespace: str, scenario_id: int) -> None:
    """Shared advisory lock: many claims/cascades coexist; an allocation run (exclusive) waits for them."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock_shared(:k)"), {"k": advisory_key(namespace, scenario_id)}
    )


async def try_xact_lock_shared(session: AsyncSession, namespace: str, scenario_id: int) -> bool:
    res = await session.execute(
        text("SELECT pg_try_advisory_xact_lock_shared(:k)"), {"k": advisory_key(namespace, scenario_id)}
    )
    return bool(res.scalar())
