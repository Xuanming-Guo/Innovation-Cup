from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Server-only settings loaded from the process environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="COORDINATION_",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Literal["development", "test", "staging", "production"] = "development"
    api_version: str = "1.0.0"
    build_commit: str = "development"
    log_level: str = "INFO"

    supabase_url: str | None = None
    supabase_jwt_issuer: str | None = None
    supabase_jwt_audience: str = "authenticated"
    database_url: SecretStr | None = None

    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.8-flash"
    google_cloud_project: str | None = None
    google_cloud_region: str | None = None

    worker_poll_seconds: float = Field(default=5.0, ge=0.5, le=60.0)

    @property
    def missing_production_settings(self) -> tuple[str, ...]:
        required = {
            "database_url": self.database_url,
            "google_cloud_project": self.google_cloud_project,
            "google_cloud_region": self.google_cloud_region,
            "supabase_jwt_issuer": self.supabase_jwt_issuer,
            "supabase_url": self.supabase_url,
        }
        return tuple(name for name, value in required.items() if value is None)

    def public_runtime_summary(self) -> dict[str, object]:
        """Return status metadata that cannot reveal secret values."""

        return {
            "environment": self.environment,
            "supabase_configured": bool(self.supabase_url and self.supabase_jwt_issuer),
            "database_configured": self.database_url is not None,
            "gemini_configured": self.gemini_api_key is not None,
            "gemini_model": self.gemini_model,
            "cloud_run_configured": bool(
                self.google_cloud_project and self.google_cloud_region
            ),
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
