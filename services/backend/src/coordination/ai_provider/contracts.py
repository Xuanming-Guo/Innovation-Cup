from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class AiProviderConfiguration(BaseModel):
    """Non-secret company AI configuration safe to return to an administrator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["gemini_developer_api"] = "gemini_developer_api"
    status: Literal["configured", "not_configured"]
    credential_hint: str | None
    validated_model: str | None
    configured_at: datetime | None
    validated_at: datetime | None
    rotated_at: datetime | None


class GeminiCredentialValidation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str
