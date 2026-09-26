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
    supabase_jwt_algorithms: str = "ES256,RS256"
    supabase_jwt_leeway_seconds: int = Field(default=30, ge=0, le=120)
    database_url: SecretStr | None = None
    database_connect_timeout_seconds: int = Field(default=5, ge=1, le=30)

    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.8-flash"
    gemini_timeout_seconds: int = Field(default=20, ge=1, le=120)
    gemini_retry_attempts: int = Field(default=2, ge=1, le=3)
    gemini_max_output_tokens: int = Field(default=8192, ge=512, le=32768)
    gemini_max_projection_characters: int = Field(default=150000, ge=10000, le=500000)
    google_cloud_project: str | None = None
    google_cloud_region: str | None = None

    worker_poll_seconds: float = Field(default=5.0, ge=0.5, le=60.0)
    worker_batch_size: int = Field(default=4, ge=1, le=32)
    worker_lease_seconds: int = Field(default=120, ge=15, le=900)
    worker_renewal_seconds: float = Field(default=30.0, ge=5.0, le=300.0)
    worker_instance_name: str | None = Field(default=None, max_length=200)

    @property
    def worker_configuration_valid(self) -> bool:
        return (
            self.database_url is not None
            and self.gemini_api_key is not None
            and self.worker_renewal_seconds < self.worker_lease_seconds
        )

    @property
    def supabase_jwks_url(self) -> str:
        if self.supabase_jwt_issuer is None:
            raise ValueError("Supabase JWT issuer is not configured")
        return f"{self.supabase_jwt_issuer.rstrip('/')}/.well-known/jwks.json"

    @property
    def supabase_jwt_algorithm_allowlist(self) -> tuple[str, ...]:
        return tuple(
            algorithm.strip()
            for algorithm in self.supabase_jwt_algorithms.split(",")
            if algorithm.strip()
        )

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
            "cloud_run_configured": bool(self.google_cloud_project and self.google_cloud_region),
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
