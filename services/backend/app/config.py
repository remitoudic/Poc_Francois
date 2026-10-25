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

    # Destination Server default (built-in simulator or remote)
    DEFAULT_DESTINATION_URL: str = os.getenv(
        "DEFAULT_DESTINATION_URL", "http://localhost:8000/api/v1/etl/simulate-destination"
    )

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
