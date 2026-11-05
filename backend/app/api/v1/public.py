from fastapi import APIRouter
from pydantic import BaseModel

from app.config import get_settings
from app.db import check_db

router = APIRouter()


class HealthOut(BaseModel):
    status: str
    db: str
    version: str


@router.get("/health", response_model=HealthOut)
async def health() -> HealthOut:
    ok = await check_db()
    return HealthOut(
        status="ok" if ok else "degraded",
        db="ok" if ok else "down",
        version=get_settings().APP_VERSION,
    )
