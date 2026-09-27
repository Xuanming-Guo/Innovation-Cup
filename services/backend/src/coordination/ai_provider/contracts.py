from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, SecretStr, model_validator

AiProviderName = Literal["gemini_developer_api", "vertex_ai"]
AiCredentialKind = Literal["api_key", "vertex_service_account"]


def _validate_provider_mode(
    *,
    provider: AiProviderName,
    credential_kind: AiCredentialKind,
    vertex_project_id: str | None,
    vertex_client_email: str | None,
    vertex_location: str | None,
) -> None:
    vertex_metadata = (vertex_project_id, vertex_client_email, vertex_location)
    if provider == "gemini_developer_api":
        if credential_kind != "api_key" or any(value is not None for value in vertex_metadata):
            raise ValueError("Gemini Developer API configuration requires only an API key")
        return
    if credential_kind != "vertex_service_account" or any(
        value is None for value in vertex_metadata
    ):
        raise ValueError("Vertex AI configuration requires service-account metadata")


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

    @model_validator(mode="after")
    def provider_mode_matches(self) -> AiProviderConfiguration:
        _validate_provider_mode(
            provider=self.provider,
            credential_kind=self.credential_kind,
            vertex_project_id=self.vertex_project_id,
            vertex_client_email=self.vertex_client_email,
            vertex_location=self.vertex_location,
        )
        return self


class AiCredentialValidation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: AiProviderName
    credential_kind: AiCredentialKind
    canonical_credential: SecretStr
    model: str
    vertex_project_id: str | None = None
    vertex_client_email: str | None = None
    vertex_location: str | None = None

    @model_validator(mode="after")
    def provider_mode_matches(self) -> AiCredentialValidation:
        _validate_provider_mode(
            provider=self.provider,
            credential_kind=self.credential_kind,
            vertex_project_id=self.vertex_project_id,
            vertex_client_email=self.vertex_client_email,
            vertex_location=self.vertex_location,
        )
        return self


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

    @model_validator(mode="after")
    def provider_mode_matches(self) -> ResolvedAiCredential:
        _validate_provider_mode(
            provider=self.provider,
            credential_kind=self.credential_kind,
            vertex_project_id=self.vertex_project_id,
            vertex_client_email=self.vertex_client_email,
            vertex_location=self.vertex_location,
        )
        return self
