from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, SecretStr

AiProviderName = Literal["gemini_developer_api", "vertex_ai"]
AiCredentialKind = Literal["api_key", "vertex_service_account"]


class AiProviderConfiguration(BaseModel):
    """Non-secret company AI configuration safe to return to an administrator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: AiProviderName = "gemini_developer_api"
    credential_kind: AiCredentialKind = "api_key"
    status: Literal["configured", "not_configured"]
    credential_hint: str | None
    validated_model: str | None
    vertex_project_id: str | None = None
    vertex_client_email: str | None = None
    vertex_location: str | None = None
    configured_at: datetime | None
    validated_at: datetime | None
    rotated_at: datetime | None


class AiCredentialValidation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: AiProviderName
    credential_kind: AiCredentialKind
    canonical_credential: SecretStr
    model: str
    vertex_project_id: str | None = None
    vertex_client_email: str | None = None
    vertex_location: str | None = None


class ResolvedAiCredential(BaseModel):
    """Worker-only credential value returned by the guarded database resolver."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: AiProviderName
    credential_kind: AiCredentialKind
    credential: SecretStr
    validated_model: str
    vertex_project_id: str | None = None
    vertex_client_email: str | None = None
    vertex_location: str | None = None
