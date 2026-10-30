import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "FOX MLO - Plunet XLIFF ETL Server"
    APP_ENV: str = "production"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://fox_user:fox_password@postgres:5432/fox_mlo"
    )

    # Plunet BusinessManager API
    PLUNET_BASE_URL: str = os.getenv("PLUNET_BASE_URL", "https://portal.foxtranslations.com/")
    PLUNET_USERNAME: str = os.getenv("PLUNET_USERNAME", "")
    PLUNET_PASSWORD: str = os.getenv("PLUNET_PASSWORD", "")
    PLUNET_MODE: str = "soap"  # "soap" = live portal, "fake" = in-memory gateway (dev/tests)
    PLUNET_TIMEOUT_SECONDS: float = 30.0

    # Destination Server default (built-in simulator or remote)
    DEFAULT_DESTINATION_URL: str = os.getenv(
        "DEFAULT_DESTINATION_URL", "http://localhost:8000/api/v1/etl/simulate-destination"
    )

    # Temporal
    TEMPORAL_ADDRESS: str = "temporal:7233"
    TEMPORAL_NAMESPACE: str = "fox-mlo"
    TEMPORAL_TASK_QUEUE: str = "fox-orchestration"
    TEMPORAL_PLUNET_TASK_QUEUE: str = "fox-plunet"
    PLUNET_MAX_CONCURRENT_CALLS: int = 4  # fox-plunet activities run at most this many at once
    PLUNET_SYNC_SECONDS: int = 120  # PlunetSyncWorkflow schedule interval (decision 1)
    DEV_ENDPOINTS: bool = False  # /api/v1/dev/* (create orders, drive the fake Plunet); never in production

    # Polylang (WordPress) source
    POLYLANG_BASE_URL: str = "http://polylang-mock:8090"
    POLYLANG_USERNAME: str = ""
    POLYLANG_APP_PASSWORD: str = ""
    POLYLANG_TIMEOUT_SECONDS: float = 20.0

    # Realtime (Postgres LISTEN/NOTIFY)
    EVENTS_CHANNEL: str = "fox_events"
    SSE_HEARTBEAT_SECONDS: float = 15.0

    # CORS
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://frontend:3000",
        "*",
    ]

    model_config = SettingsConfigDict(
        env_file=("../../.env", "../.env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )


    @property
    def psycopg_conninfo(self) -> str:
        """DATABASE_URL without the SQLAlchemy driver suffix, for raw psycopg connections."""
        return self.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
