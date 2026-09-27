from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """Server-only settings loaded from the process environment."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_ENV_FILE,
        env_prefix="COORDINATION_",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Literal["development", "test", "staging", "production"] = "development"
    api_version: str = "1.0.0"
    build_commit: str = "development"
    log_level: str = "INFO"
    cors_allowed_origins: str = (
        "tauri://localhost,http://tauri.localhost,"
        "http://127.0.0.1:1420,http://localhost:1420"
    )

    supabase_url: str | None = None
    supabase_jwt_issuer: str | None = None
    supabase_jwt_audience: str = "authenticated"
    supabase_jwt_algorithms: str = "ES256,RS256"
    supabase_jwt_leeway_seconds: int = Field(default=30, ge=0, le=120)
    database_url: SecretStr | None = None
    database_connect_timeout_seconds: int = Field(default=5, ge=1, le=30)

    # Local/test fallback only. Production Gemini credentials are supplied per company and
    # resolved from Supabase Vault by the worker; they are never process-wide configuration.
    gemini_api_key: SecretStr | None = None
    interpretation_mode: Literal["gemini", "fixture"] = "gemini"
    gemini_model: str = "gemini-3.8-flash"
    gemini_timeout_seconds: int = Field(default=20, ge=1, le=120)
    gemini_max_output_tokens: int = Field(default=8192, ge=512, le=32768)
    gemini_max_projection_characters: int = Field(default=150000, ge=10000, le=500000)
    vertex_location: str = Field(
        default="global",
        min_length=2,
        max_length=64,
        pattern=r"^(global|[a-z]+-[a-z]+[0-9])$",
    )
    vertex_allowed_project_ids: str = ""
    worker_poll_seconds: float = Field(default=5.0, ge=0.5, le=60.0)
    worker_batch_size: int = Field(default=4, ge=1, le=32)
    worker_lease_seconds: int = Field(default=120, ge=15, le=900)
    worker_renewal_seconds: float = Field(default=30.0, ge=5.0, le=300.0)
    worker_instance_name: str | None = Field(default=None, max_length=200)

    # Single-laptop hosted-demo registrar. These values are supplied only to the
    # host registrar container and are never exposed to desktop clients.
    host_company_id: UUID | None = None
    host_actor_id: UUID | None = None
    host_instance_id: UUID | None = None
    host_tunnel_log_path: Path = Path("/state/cloudflared.log")
    host_ready_path: Path = Path("/tmp/coordination-host-registrar.ready")
    host_poll_seconds: float = Field(default=2.0, ge=0.5, le=30.0)
    host_heartbeat_seconds: float = Field(default=30.0, ge=10.0, le=60.0)
    host_ttl_seconds: int = Field(default=120, ge=60, le=300)
    host_health_timeout_seconds: float = Field(default=10.0, ge=1.0, le=30.0)

    @property
    def worker_configuration_valid(self) -> bool:
        return (
            self.database_url is not None
            and self.worker_renewal_seconds < self.worker_lease_seconds
            and not (self.interpretation_mode == "fixture" and self.environment == "production")
        )

    @property
    def host_registrar_configuration_valid(self) -> bool:
        return (
            self.database_url is not None
            and self.host_company_id is not None
            and self.host_actor_id is not None
            and self.host_instance_id is not None
            and self.host_heartbeat_seconds < self.host_ttl_seconds
            and len(self.build_commit) == 40
            and all(character in "0123456789abcdef" for character in self.build_commit)
        )

    @property
    def supabase_jwks_url(self) -> str:
        if self.supabase_jwt_issuer is None:
            raise ValueError("Supabase JWT issuer is not configured")
        return f"{self.supabase_jwt_issuer.rstrip('/')}/.well-known/jwks.json"

    @property
    def cors_origin_allowlist(self) -> tuple[str, ...]:
        origins = tuple(
            origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()
        )
        if "*" in origins:
            raise ValueError("CORS origins must be explicit")
        return origins

    @property
    def supabase_jwt_algorithm_allowlist(self) -> tuple[str, ...]:
        return tuple(
            algorithm.strip()
            for algorithm in self.supabase_jwt_algorithms.split(",")
            if algorithm.strip()
        )

    @property
    def vertex_project_allowlist(self) -> tuple[str, ...]:
        return tuple(
            project_id.strip()
            for project_id in self.vertex_allowed_project_ids.split(",")
            if project_id.strip()
        )

    @property
    def missing_production_settings(self) -> tuple[str, ...]:
        required = {
            "database_url": self.database_url,
            "supabase_jwt_issuer": self.supabase_jwt_issuer,
            "supabase_url": self.supabase_url,
        }
        if self.interpretation_mode == "fixture" and self.environment == "production":
            required["interpretation_mode"] = None
        return tuple(name for name, value in required.items() if value is None)

    def public_runtime_summary(self) -> dict[str, object]:
        """Return status metadata that cannot reveal secret values."""

        return {
            "environment": self.environment,
            "supabase_configured": bool(self.supabase_url and self.supabase_jwt_issuer),
            "database_configured": self.database_url is not None,
            "gemini_credential_mode": "tenant_byok_api_key_or_vertex_service_account",
            "gemini_local_fallback_configured": (
                self.environment != "production" and self.gemini_api_key is not None
            ),
            "gemini_model": self.gemini_model,
            "interpretation_mode": self.interpretation_mode,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
