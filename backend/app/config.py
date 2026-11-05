from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Environment configuration (PRD §16)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://stranded:stranded@localhost:5433/stranded"
    JWT_SECRET: str = "change-me"
    JWT_TTL_HOURS: int = 24
    OPS_PASSWORD: str = "change-me"
    CORS_ORIGINS: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    DEFAULT_SCENARIO: str = "potheri-demo"
    DEMO_MODE: bool = True
    BATCH_WINDOW_SECONDS: int = 150
    HOLD_SECONDS: int = 600
    DELAY_THRESHOLD_MINUTES: int = 20
    HUB_RADIUS_KM: float = 10
    SIM_SPEED: float = 10
    ENABLE_ORTOOLS: bool = False
    DEMO_OTP_ENABLED: bool = False
    TWILIO_ENABLED: bool = False
    TWILIO_SID: str = ""
    TWILIO_TOKEN: str = ""
    TWILIO_FROM: str = ""
    LOG_LEVEL: str = "INFO"

    APP_VERSION: str = "0.1.0"

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
