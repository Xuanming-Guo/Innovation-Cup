from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status

from coordination.ai_provider.persistence import AiProviderStore, PostgresAiProviderStore
from coordination.ai_provider.validation import (
    GeminiCredentialValidator,
    GoogleGeminiCredentialValidator,
)
from coordination.config import Settings, get_settings


def get_ai_provider_store(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AiProviderStore:
    if settings.database_url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI provider configuration is unavailable",
        )
    return PostgresAiProviderStore(
        settings.database_url.get_secret_value(),
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
    )


def get_gemini_credential_validator(
    settings: Annotated[Settings, Depends(get_settings)],
) -> GeminiCredentialValidator:
    return GoogleGeminiCredentialValidator(
        model=settings.gemini_model,
        timeout_seconds=settings.gemini_timeout_seconds,
    )


AiProviderStoreDependency = Annotated[AiProviderStore, Depends(get_ai_provider_store)]
GeminiCredentialValidatorDependency = Annotated[
    GeminiCredentialValidator, Depends(get_gemini_credential_validator)
]
