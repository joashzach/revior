"""Scenario lookup + config helpers (PRD F1)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.errors import AppError
from app.models import Scenario

# keys exposed through the API (frontend ScenarioConfig) + internal extras kept in the same JSONB
PUBLIC_CONFIG_KEYS = (
    "batch_window_seconds", "hold_seconds", "auto_run_on_batch_close", "delay_threshold_minutes",
    "hub_radius_km", "open_booking_enabled", "sim_speed", "demo_mode", "join_qr_mode",
)
INTERNAL_CONFIG_KEYS = ("auto_run_on_capacity_add", "cluster_window_minutes", "auto_open_booking_after_rounds")


def default_config() -> dict[str, Any]:
    s = get_settings()
    return {
        "batch_window_seconds": s.BATCH_WINDOW_SECONDS, "hold_seconds": s.HOLD_SECONDS,
        "auto_run_on_batch_close": True, "delay_threshold_minutes": s.DELAY_THRESHOLD_MINUTES,
        "hub_radius_km": s.HUB_RADIUS_KM, "open_booking_enabled": False, "sim_speed": s.SIM_SPEED,
        "demo_mode": s.DEMO_MODE, "join_qr_mode": "corner",
        "auto_run_on_capacity_add": True, "cluster_window_minutes": 30,
    }


def cfg(sc: Scenario) -> dict[str, Any]:
    return {**default_config(), **(sc.config or {})}


def public_config(sc: Scenario) -> dict[str, Any]:
    c = cfg(sc)
    return {k: c[k] for k in PUBLIC_CONFIG_KEYS}


def join_url(sc: Scenario) -> str:
    return f"{get_settings().FRONTEND_BASE_URL.rstrip('/')}/demo-join?scenario={sc.slug}"


async def active_scenario(session: AsyncSession) -> Scenario:
    sc = (await session.execute(select(Scenario).where(Scenario.is_active))).scalars().first()
    if sc is None:
        raise AppError("NOT_FOUND", "No active scenario")
    return sc


async def scenario_by_slug(session: AsyncSession, slug: str | None) -> Scenario:
    if not slug:
        return await active_scenario(session)
    sc = (await session.execute(select(Scenario).where(Scenario.slug == slug))).scalars().first()
    if sc is None:
        raise AppError("NOT_FOUND", f"Unknown scenario '{slug}'")
    return sc
