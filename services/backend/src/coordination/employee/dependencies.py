from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status

from coordination.config import Settings, get_settings
from coordination.employee.persistence import EmployeeStore, PostgresEmployeeStore


def get_employee_store(
    settings: Annotated[Settings, Depends(get_settings)],
) -> EmployeeStore:
    if settings.database_url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="employee workflow store is not configured",
        )
    return PostgresEmployeeStore(
        settings.database_url.get_secret_value(),
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
    )


EmployeeStoreDependency = Annotated[EmployeeStore, Depends(get_employee_store)]
