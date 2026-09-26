from __future__ import annotations

from typing import Annotated, Literal

import uvicorn
from fastapi import Depends, FastAPI, Response, status
from pydantic import BaseModel, ConfigDict

from coordination import __version__
from coordination.auth.dependencies import CompanyContextDependency
from coordination.config import Settings, get_settings


class StrictResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LivenessResponse(StrictResponse):
    service: Literal["coordination-api"] = "coordination-api"
    status: Literal["live"] = "live"


class ReadinessResponse(StrictResponse):
    service: Literal["coordination-api"] = "coordination-api"
    status: Literal["ready", "not_ready"]
    missing_configuration: list[str]
    runtime: dict[str, object]


class VersionResponse(StrictResponse):
    service: Literal["coordination-api"] = "coordination-api"
    api_version: str
    build_commit: str
    package_version: str


class SessionResponse(StrictResponse):
    user_id: str
    company_id: str
    membership_id: str
    administrative_role: str
    employee_id: str | None


SettingsDependency = Annotated[Settings, Depends(get_settings)]


def create_app() -> FastAPI:
    application = FastAPI(
        title="Coordination Engine API",
        version="1.0.0",
        docs_url="/docs",
        redoc_url=None,
    )

    @application.get("/health/live", response_model=LivenessResponse)
    def live() -> LivenessResponse:
        return LivenessResponse()

    @application.get("/health/ready", response_model=ReadinessResponse)
    def ready(response: Response, settings: SettingsDependency) -> ReadinessResponse:
        missing = list(settings.missing_production_settings)
        is_ready = settings.environment != "production" or not missing
        if not is_ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(
            status="ready" if is_ready else "not_ready",
            missing_configuration=missing,
            runtime=settings.public_runtime_summary(),
        )

    @application.get("/version", response_model=VersionResponse)
    def version(settings: SettingsDependency) -> VersionResponse:
        return VersionResponse(
            api_version=settings.api_version,
            build_commit=settings.build_commit,
            package_version=__version__,
        )

    @application.get("/v1/session", response_model=SessionResponse)
    def session(context: CompanyContextDependency) -> SessionResponse:
        return SessionResponse(
            user_id=str(context.actor.user_id),
            company_id=str(context.company_id),
            membership_id=str(context.membership_id),
            administrative_role=context.administrative_role,
            employee_id=str(context.employee_id) if context.employee_id else None,
        )

    return application


app = create_app()


def run(*, reload: bool = False) -> None:
    uvicorn.run(
        "coordination.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=reload,
    )
