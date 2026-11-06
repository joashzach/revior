"""WebSocket endpoints: /ws/passenger?token= and /ws/ops?token= (contract §6)."""
from __future__ import annotations

import asyncio
import contextlib

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app import clock
from app.db import get_sessionmaker
from app.errors import AppError
from app.models import Passenger, Scenario
from app.security import token_from_query
from app.ws.hub import Connection, hub

router = APIRouter()
log = structlog.get_logger()
PING_INTERVAL = 20


async def _serve(ws: WebSocket, conn: Connection) -> None:
    hub.add(conn)

    async def reader():
        while True:
            msg = await ws.receive_json()
            if isinstance(msg, dict) and msg.get("type") == "ping":
                conn.queue.put_nowait({"type": "pong", "ts": clock.utcnow().isoformat(), "scenario": None, "data": {}})

    async def writer():
        while True:
            try:
                msg = await asyncio.wait_for(conn.queue.get(), PING_INTERVAL)
            except asyncio.TimeoutError:
                msg = {"type": "ping", "ts": clock.utcnow().isoformat(), "scenario": None, "data": {}}
            if msg is None:  # token invalidated
                await ws.close(code=4401)
                return
            await ws.send_json(msg)

    tasks = [asyncio.create_task(reader()), asyncio.create_task(writer())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for t in tasks:
            t.cancel()
        for t in tasks:
            with contextlib.suppress(BaseException):
                await t
        hub.remove(conn)


@router.websocket("/ws/passenger")
async def ws_passenger(ws: WebSocket, token: str | None = None):
    await ws.accept()
    try:
        claims = token_from_query(token)
        if claims.get("role") != "passenger":
            raise AppError("FORBIDDEN", "Passenger token required")
        async with get_sessionmaker()() as s:
            p = await s.get(Passenger, int(claims["sub"]))
            if p is None or p.token_version != claims.get("tv"):
                raise AppError("UNAUTHORIZED", "Session ended")
            pid, sid = p.id, p.scenario_id
    except AppError:
        await ws.close(code=4401)
        return
    try:
        await _serve(ws, Connection("passenger", sid, pid))
    except (WebSocketDisconnect, RuntimeError):
        pass


@router.websocket("/ws/ops")
async def ws_ops(ws: WebSocket, token: str | None = None):
    await ws.accept()
    try:
        claims = token_from_query(token)
        if claims.get("role") != "operator":
            raise AppError("FORBIDDEN", "Operator token required")
    except AppError:
        await ws.close(code=4401)
        return
    try:
        await _serve(ws, Connection("operator", 0))
    except (WebSocketDisconnect, RuntimeError):
        pass
