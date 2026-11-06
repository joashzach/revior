import os

# Tests run against a dedicated database and never start background loops / auto-bootstrap.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://stranded:stranded@localhost:5433/stranded_test")
os.environ["RUN_BACKGROUND_LOOPS"] = "false"
os.environ["AUTO_BOOTSTRAP"] = "false"
os.environ["OPS_PASSWORD"] = "ops-test"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["DEMO_MODE"] = "true"

import asyncio  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.db import dispose_engine, get_sessionmaker  # noqa: E402


def pytest_sessionstart(session):
    # migrate the test DB to head (idempotent)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True,
                   cwd=os.path.dirname(os.path.dirname(__file__)), env=os.environ.copy())
    # drop throw-away scenarios left behind by earlier runs (factory scenarios are slugged "t-...")
    import asyncpg

    async def _clean():
        dsn = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
        conn = await asyncpg.connect(dsn)
        try:
            await conn.execute("DELETE FROM scenarios WHERE slug LIKE 't-%'")
        finally:
            await conn.close()
    asyncio.run(_clean())


from app.main import app  # noqa: E402


@pytest_asyncio.fixture(scope="session")
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await dispose_engine()


@pytest_asyncio.fixture(scope="session")
async def ops_headers(client):
    r = await client.post("/api/v1/auth/ops-login", json={"password": "ops-test"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest_asyncio.fixture
async def potheri(client, ops_headers):
    """Fresh potheri-demo scenario (reset through the real endpoint)."""
    from app.seed.loader import ensure_scenarios
    async with get_sessionmaker()() as s:
        await ensure_scenarios(s)
        await s.commit()
    r = await client.post("/api/v1/ops/scenarios/potheri-demo/activate", headers=ops_headers)
    assert r.status_code == 200, r.text
    r = await client.post("/api/v1/ops/scenarios/potheri-demo/reset", headers=ops_headers)
    assert r.status_code == 200, r.text
    return r.json()


@pytest_asyncio.fixture(autouse=True)
async def _purge_throwaway_scenarios():
    """Factory ('t-…') and stress scenarios are throw-away: drop them after every test so global counts stay clean."""
    yield
    from sqlalchemy import text
    for attempt in range(6):        # request sessions finish their cleanup just after the response: retry on lock races
        try:
            async with get_sessionmaker()() as s:
                await s.execute(text("DELETE FROM scenarios WHERE slug LIKE 't-%' OR slug LIKE 'stress-%'"))
                await s.commit()
            return
        except Exception:  # noqa: BLE001 - deadlock / lock timeout against a still-closing request session
            await asyncio.sleep(0.5 * (attempt + 1))


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _fresh_secondary(client, ops_headers):
    """Start the session with a pristine secondary scenario (earlier runs may have disrupted it)."""
    from app.seed.loader import ensure_scenarios
    async with get_sessionmaker()() as s:
        await ensure_scenarios(s)
        await s.commit()
    await client.post("/api/v1/ops/scenarios/secondary-demo/reset", headers=ops_headers)
    yield
