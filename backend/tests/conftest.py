import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db import dispose_engine
from app.main import app


@pytest_asyncio.fixture(scope="session")
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await dispose_engine()
