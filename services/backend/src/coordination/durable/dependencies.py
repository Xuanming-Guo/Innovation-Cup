from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status

from coordination.config import Settings, get_settings
from coordination.durable.persistence import PostgresDurableStore


def get_durable_store(
    settings: Annotated[Settings, Depends(get_settings)],
) -> PostgresDurableStore:
    if settings.database_url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="durable coordination store is not configured",
        )
    return PostgresDurableStore(
        settings.database_url.get_secret_value(),
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
    )


DurableStoreDependency = Annotated[PostgresDurableStore, Depends(get_durable_store)]
