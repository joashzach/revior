from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Environment configuration for Revior (PRD §16)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://stranded:stranded@localhost:5433/stranded"
    JWT_SECRET: str = "change-me"
    JWT_TTL_HOURS: int = 24
    OPS_PASSWORD: str = "change-me"
    CORS_ORIGINS: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    FRONTEND_BASE_URL: str = "http://localhost:5173"
    DEMO_PERSONA_PASSWORD: str = "revior-demo"
    DEFAULT_SCENARIO: str = "potheri-demo"
    DEMO_MODE: bool = True
    BATCH_WINDOW_SECONDS: int = 150
    HOLD_SECONDS: int = 600
    DELAY_THRESHOLD_MINUTES: int = 20
    HUB_RADIUS_KM: float = 10
    SIM_SPEED: float = 10
    ENABLE_ORTOOLS: bool = False
    TWILIO_ENABLED: bool = False
    TWILIO_SID: str = ""
    TWILIO_TOKEN: str = ""
    TWILIO_FROM: str = ""
    LOG_LEVEL: str = "INFO"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 120  # seconds a request may wait for a pooled connection under a surge
    SQL_SLOW_MS: int = 0  # >0: log statements slower than this (perf debugging)
    RUN_BACKGROUND_LOOPS: bool = True
    AUTO_BOOTSTRAP: bool = True  # seed the default scenario on startup if the DB is empty
    REGISTER_RATE_LIMIT: str = "20/minute"
    AUTH_RATE_LIMIT: str = "60/minute"

    APP_NAME: str = "Revior"
    APP_VERSION: str = "1.0.0"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, v):
        # PRD §16 gives CORS_ORIGINS as a comma-separated string.
        if isinstance(v, str) and not v.strip().startswith("["):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
