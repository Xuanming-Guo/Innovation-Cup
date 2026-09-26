from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status

from coordination.config import Settings, get_settings
from coordination.interpretation.gateway import (
    GatewayConfiguration,
    GoogleGeminiGateway,
    InterpretationGateway,
)
from coordination.interpretation.persistence import (
    InterpretationStore,
    PostgresInterpretationStore,
)


def get_interpretation_store(
    settings: Annotated[Settings, Depends(get_settings)],
) -> InterpretationStore:
    if settings.database_url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="interpretation store is not configured",
        )
    return PostgresInterpretationStore(
        settings.database_url.get_secret_value(),
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
    )


def get_interpretation_gateway(
    settings: Annotated[Settings, Depends(get_settings)],
) -> InterpretationGateway:
    if settings.gemini_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="model interpretation is not configured",
        )
    return GoogleGeminiGateway(
        api_key=settings.gemini_api_key.get_secret_value(),
        configuration=GatewayConfiguration(
            model=settings.gemini_model,
            timeout_seconds=settings.gemini_timeout_seconds,
            retry_attempts=settings.gemini_retry_attempts,
            max_output_tokens=settings.gemini_max_output_tokens,
        ),
    )


InterpretationStoreDependency = Annotated[InterpretationStore, Depends(get_interpretation_store)]
InterpretationGatewayDependency = Annotated[
    InterpretationGateway, Depends(get_interpretation_gateway)
]
