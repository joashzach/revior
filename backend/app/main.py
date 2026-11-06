from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select

from app.api.v1 import auth, ops, public
from app.config import get_settings
from app.db import dispose_engine, get_sessionmaker
from app.errors import install_error_handlers
from app.logging import RequestIdMiddleware, configure_logging
from app.models import Node

log = structlog.get_logger()


async def bootstrap() -> None:
    """Create scenario rows and seed any scenario that has no data yet (first boot)."""
    from app.seed.loader import ensure_scenarios, reset_scenario

    async with get_sessionmaker()() as session:
        scenarios = await ensure_scenarios(session)
        await session.commit()
        for sc in scenarios:
            n = (await session.execute(select(func.count()).select_from(Node).where(Node.scenario_id == sc.id))).scalar()
            if not n:
                await reset_scenario(session, sc.slug)
                await session.commit()
                log.info("scenario_bootstrapped", slug=sc.slug)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    loops = None
    if s.AUTO_BOOTSTRAP:
        try:
            await bootstrap()
        except Exception:  # DB not migrated yet etc. — keep the app up so /health reports it
            log.error("bootstrap_failed", exc_info=True)
    log.info("revior_started", version=s.APP_VERSION, demo_mode=s.DEMO_MODE)
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    app = FastAPI(
        title="Revior API", version=settings.APP_VERSION, lifespan=lifespan,
        description="Revior - group disruption-recovery platform. Passengers choose. Revior decides fairly. "
                    "Every decision is explainable. (Hackathon PS2: The Stranded Network)")
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Request-ID"])
    app.add_middleware(RequestIdMiddleware)
    install_error_handlers(app)
    for r in (auth.router, ops.router, public.router,):
        app.include_router(r, prefix="/api/v1")
    return app


app = create_app()
