from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status

from coordination.approval.persistence import ApprovalStore, PostgresApprovalStore
from coordination.config import Settings, get_settings


def get_approval_store(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ApprovalStore:
    if settings.database_url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="approval store is not configured",
        )
    return PostgresApprovalStore(
        settings.database_url.get_secret_value(),
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
    )


ApprovalStoreDependency = Annotated[ApprovalStore, Depends(get_approval_store)]
