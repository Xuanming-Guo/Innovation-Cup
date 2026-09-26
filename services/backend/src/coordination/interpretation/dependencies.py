from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status

from coordination.config import Settings, get_settings
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
InterpretationStoreDependency = Annotated[InterpretationStore, Depends(get_interpretation_store)]
