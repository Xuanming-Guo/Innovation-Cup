from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID, uuid5

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from coordination import __version__
from coordination.ai_provider.contracts import AiProviderConfiguration
from coordination.ai_provider.dependencies import (
    AiProviderStoreDependency,
    GeminiCredentialValidatorDependency,
)
from coordination.ai_provider.persistence import (
    AiProviderAuthorityError,
    AiProviderStoreUnavailableError,
)
from coordination.ai_provider.validation import (
    GeminiCredentialValidationUnavailableError,
    InvalidGeminiCredentialError,
)
from coordination.approval.contracts import (
    ApprovalCommand,
    ApprovalDecisionResult,
    CommitCommand,
    CommitResult,
    PlanBinding,
    PlanEvidence,
    PlanReview,
)
from coordination.approval.dependencies import ApprovalStoreDependency
from coordination.approval.persistence import (
    ApprovalAuthorityError,
    ApprovalIdempotencyConflictError,
    ApprovalIncompleteError,
    ApprovalStaleError,
    ApprovalStoreError,
    PlanNotFoundError,
    ScheduleConflictError,
)
from coordination.auth.dependencies import CompanyContextDependency
from coordination.config import Settings, get_settings
from coordination.db.health import DatabaseReadinessDependency
from coordination.durable.contracts import JobView, NotificationPage, NotificationView, QueueMetrics
from coordination.durable.dependencies import DurableStoreDependency
from coordination.durable.persistence import (
    DurableStoreError,
    JobIdempotencyConflictError,
    JobNotFoundError,
    JobStateConflictError,
    NotificationNotFoundError,
)
from coordination.employee.contracts import (
    EmployeeTask,
    ReviewCommand,
    ReviewPolicyCommand,
    ReviewPolicyResult,
    ReviewResult,
    SubmissionCommand,
    SubmissionResult,
    SubmissionReviewView,
    TaskCommand,
    TaskTransitionCommand,
    TaskTransitionResult,
    TaskView,
)
from coordination.employee.dependencies import EmployeeStoreDependency
from coordination.employee.persistence import (
    EmployeeAuthorityError,
    EmployeeIdempotencyConflictError,
    EmployeeStateConflictError,
    EmployeeStoreError,
    EmployeeTaskNotFoundError,
)
from coordination.interpretation.dependencies import InterpretationStoreDependency
from coordination.interpretation.persistence import (
    CreatePlanningRequest,
    InterpretationStoreUnavailableError,
    PlanningRequestIdempotencyConflictError,
    PlanningRequestNotFoundError,
    PlanningRequestSourceNotFoundError,
)


class StrictResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LivenessResponse(StrictResponse):
    service: Literal["coordination-api"] = "coordination-api"
    status: Literal["live"] = "live"


class ReadinessResponse(StrictResponse):
    service: Literal["coordination-api"] = "coordination-api"
    status: Literal["ready", "not_ready"]
    missing_configuration: list[str]
    checks: dict[str, bool]
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


class GeminiCredentialRequest(StrictResponse):
    api_key: SecretStr = Field(min_length=20, max_length=512)
    correlation_id: UUID


class PlanningRequestCreate(StrictResponse):
    project_id: UUID | None
    original_request: str = Field(min_length=1, max_length=8000)
    selected_source_ids: tuple[UUID, ...] = Field(max_length=50)
    requested_priority_key: str | None = Field(max_length=80)
    requested_deadline: datetime | None
    requested_deadline_timezone: str | None = Field(max_length=64)

    @model_validator(mode="after")
    def validate_deadline(self) -> PlanningRequestCreate:
        if (self.requested_deadline is None) != (self.requested_deadline_timezone is None):
            raise ValueError("requested deadline and timezone must be supplied together")
        if self.requested_deadline is not None and self.requested_deadline.utcoffset() is None:
            raise ValueError("requested_deadline must include a UTC offset")
        if len(self.selected_source_ids) != len(set(self.selected_source_ids)):
            raise ValueError("selected_source_ids must be unique")
        return self


class PlanningRequestResponse(StrictResponse):
    request_id: UUID
    status: str
    request_version: int
    created: bool


class ClarificationResponse(StrictResponse):
    question_key: str
    category: str
    question: str
    blocks_planning: bool
    status: str


class PlanningRequestDetailResponse(StrictResponse):
    request_id: UUID
    status: str
    request_version: int
    latest_outcome: str | None
    candidate_digest: str | None
    clarifications: tuple[ClarificationResponse, ...]
    candidate_contract_id: UUID | None
    snapshot_id: UUID | None
    plan_id: UUID | None
    interpretation_job_state: str | None
    materialization_job_state: str | None
    planning_job_state: str | None


class PlanningSourceResponse(StrictResponse):
    source_id: UUID
    title: str
    classification: str
    source_kind: str


class PlanningRequestSummaryResponse(StrictResponse):
    request_id: UUID
    original_request: str
    status: str
    created_at: datetime


class PlanningContextResponse(StrictResponse):
    sources: tuple[PlanningSourceResponse, ...]
    requests: tuple[PlanningRequestSummaryResponse, ...]


class PlanDecisionRequest(StrictResponse):
    requirement_id: UUID
    artifact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    binding: PlanBinding
    explanation: str = Field(default="", max_length=2000)
    correlation_id: UUID


class PlanCommitRequest(StrictResponse):
    binding: PlanBinding
    correlation_id: UUID


class EmployeeTasksResponse(StrictResponse):
    view: TaskView
    tasks: tuple[EmployeeTask, ...]


class TaskTransitionRequest(StrictResponse):
    command: TaskCommand
    expected_task_version: int = Field(gt=0)
    payload: dict[str, object] = Field(default_factory=dict)
    correlation_id: UUID


class TaskReviewPolicyRequest(StrictResponse):
    reviewer_employee_id: UUID | None = None
    self_certifiable: bool = False
    self_certification_rule: str = Field(default="", max_length=1000)
    expected_task_version: int = Field(gt=0)
    correlation_id: UUID

    @model_validator(mode="after")
    def valid_policy(self) -> TaskReviewPolicyRequest:
        rule = self.self_certification_rule.strip()
        if self.self_certifiable != bool(rule):
            raise ValueError("self-certification requires one explicit deterministic rule")
        if self.reviewer_employee_id is None and not self.self_certifiable:
            raise ValueError("a reviewer or self-certification rule is required")
        return self


class TaskSubmissionRequest(StrictResponse):
    narrative: str = Field(min_length=1, max_length=12000)
    external_evidence_refs: tuple[str, ...] = Field(default=(), max_length=50)
    file_ids: tuple[UUID, ...] = Field(default=(), max_length=20)
    reported_active_minutes: int | None = Field(default=None, ge=0, le=100_000)
    expected_task_version: int = Field(gt=0)
    correlation_id: UUID

    @field_validator("narrative")
    @classmethod
    def nonblank_narrative(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("narrative must not be blank")
        return cleaned

    @field_validator("external_evidence_refs")
    @classmethod
    def valid_external_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        cleaned = tuple(value.strip() for value in values)
        if any(not value or len(value) > 500 for value in cleaned):
            raise ValueError("external evidence references must be 1 to 500 characters")
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("external evidence references must be unique")
        return cleaned

    @model_validator(mode="after")
    def unique_files(self) -> TaskSubmissionRequest:
        if len(self.file_ids) != len(set(self.file_ids)):
            raise ValueError("file_ids must be unique")
        return self


class SubmissionReviewRequest(StrictResponse):
    expected_submission_version: int = Field(gt=0)
    submission_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["accepted", "revision_requested"]
    criterion_findings: tuple[dict[str, object], ...] = Field(default=(), max_length=100)
    correction_request: str = Field(default="", max_length=4000)
    correlation_id: UUID

    @model_validator(mode="after")
    def valid_decision(self) -> SubmissionReviewRequest:
        correction = self.correction_request.strip()
        if (self.decision == "revision_requested") != bool(correction):
            raise ValueError("only revision requests require correction instructions")
        return self


class PendingReviewsResponse(StrictResponse):
    reviews: tuple[SubmissionReviewView, ...]


class JobCancellationRequest(StrictResponse):
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def nonblank_reason(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("cancellation reason must not be blank")
        return cleaned


def _job_command_digest(company_id: UUID, job_kind: str, aggregate_id: UUID) -> bytes:
    return hashlib.sha256(f"{company_id}:{job_kind}:{aggregate_id}".encode()).digest()


def _parse_notification_cursor(cursor: str | None) -> tuple[datetime | None, UUID | None]:
    if cursor is None:
        return None, None
    try:
        created_at, notification_id = cursor.rsplit("|", 1)
        parsed_at = datetime.fromisoformat(created_at)
        if parsed_at.utcoffset() is None:
            raise ValueError("cursor timestamp is not timezone-aware")
        return parsed_at, UUID(notification_id)
    except (ValueError, TypeError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="notification cursor is invalid",
        ) from error


SettingsDependency = Annotated[Settings, Depends(get_settings)]


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="Coordination Engine API",
        version="1.0.0",
        docs_url="/docs",
        redoc_url=None,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origin_allowlist),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Company-ID"],
    )

    @application.get("/health/live", response_model=LivenessResponse)
    def live() -> LivenessResponse:
        return LivenessResponse()

    @application.get("/health/ready", response_model=ReadinessResponse)
    def ready(
        response: Response,
        settings: SettingsDependency,
        database_ready: DatabaseReadinessDependency,
    ) -> ReadinessResponse:
        missing = list(settings.missing_production_settings)
        configuration_ready = settings.environment != "production" or not missing
        is_ready = configuration_ready and database_ready
        if not is_ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(
            status="ready" if is_ready else "not_ready",
            missing_configuration=missing,
            checks={
                "configuration": configuration_ready,
                "durable_schema": database_ready,
            },
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

    @application.get(
        "/v1/companies/{company_id}/ai-provider/gemini",
        response_model=AiProviderConfiguration,
    )
    def get_company_gemini_configuration(
        company_id: UUID,
        context: CompanyContextDependency,
        store: AiProviderStoreDependency,
    ) -> AiProviderConfiguration:
        _require_company_admin(company_id, context)
        try:
            return store.get_configuration(context=context)
        except AiProviderAuthorityError as error:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="company administrator authority is required",
            ) from error
        except AiProviderStoreUnavailableError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI provider configuration is unavailable",
            ) from error

    @application.put(
        "/v1/companies/{company_id}/ai-provider/gemini",
        response_model=AiProviderConfiguration,
    )
    def configure_company_gemini(
        company_id: UUID,
        body: GeminiCredentialRequest,
        context: CompanyContextDependency,
        store: AiProviderStoreDependency,
        validator: GeminiCredentialValidatorDependency,
    ) -> AiProviderConfiguration:
        _require_company_admin(company_id, context)
        api_key = body.api_key.get_secret_value()
        try:
            validation = validator.validate(api_key=api_key)
            return store.configure(
                context=context,
                api_key=api_key,
                validated_model=validation.model,
                correlation_id=body.correlation_id,
            )
        except InvalidGeminiCredentialError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Gemini rejected the key or the configured model is unavailable",
            ) from error
        except GeminiCredentialValidationUnavailableError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Gemini credential validation is temporarily unavailable",
            ) from error
        except AiProviderAuthorityError as error:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="company administrator authority is required",
            ) from error
        except AiProviderStoreUnavailableError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI provider configuration could not be stored",
            ) from error

    @application.delete(
        "/v1/companies/{company_id}/ai-provider/gemini",
        response_model=AiProviderConfiguration,
    )
    def remove_company_gemini(
        company_id: UUID,
        correlation_id: UUID,
        context: CompanyContextDependency,
        store: AiProviderStoreDependency,
    ) -> AiProviderConfiguration:
        _require_company_admin(company_id, context)
        try:
            return store.remove(context=context, correlation_id=correlation_id)
        except AiProviderAuthorityError as error:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="company administrator authority is required",
            ) from error
        except AiProviderStoreUnavailableError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI provider configuration could not be removed",
            ) from error

    @application.post(
        "/v1/companies/{company_id}/planning-requests",
        response_model=PlanningRequestResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_planning_request(
        company_id: UUID,
        body: PlanningRequestCreate,
        response: Response,
        context: CompanyContextDependency,
        store: InterpretationStoreDependency,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> PlanningRequestResponse:
        if company_id != context.company_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="company was not found"
            )
        if context.administrative_role not in ("manager", "company_admin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="manager authority is required"
            )
        try:
            record = store.create_request(
                context=context,
                command=CreatePlanningRequest(
                    project_id=body.project_id,
                    original_request=body.original_request,
                    selected_source_ids=body.selected_source_ids,
                    requested_priority_key=body.requested_priority_key,
                    requested_deadline=body.requested_deadline,
                    requested_deadline_timezone=body.requested_deadline_timezone,
                    idempotency_key=idempotency_key,
                ),
            )
        except (PlanningRequestNotFoundError, PlanningRequestSourceNotFoundError) as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="resource was not found"
            ) from error
        except PlanningRequestIdempotencyConflictError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="idempotency key was reused"
            ) from error
        except InterpretationStoreUnavailableError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="planning request could not be stored",
            ) from error
        if not record.created:
            response.status_code = status.HTTP_200_OK
        return PlanningRequestResponse(
            request_id=record.request_id,
            status=record.status,
            request_version=record.request_version,
            created=record.created,
        )

    @application.get(
        "/v1/companies/{company_id}/planning-context",
        response_model=PlanningContextResponse,
    )
    def get_planning_context(
        company_id: UUID,
        context: CompanyContextDependency,
        store: InterpretationStoreDependency,
    ) -> PlanningContextResponse:
        if company_id != context.company_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="company was not found"
            )
        if context.administrative_role not in ("manager", "company_admin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="manager authority is required"
            )
        try:
            sources, requests = store.list_planning_context(context=context)
        except InterpretationStoreUnavailableError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="planning context is unavailable",
            ) from error
        return PlanningContextResponse(
            sources=tuple(
                PlanningSourceResponse(
                    source_id=value.source_id,
                    title=value.title,
                    classification=value.classification,
                    source_kind=value.source_kind,
                )
                for value in sources
            ),
            requests=tuple(
                PlanningRequestSummaryResponse(
                    request_id=value.request_id,
                    original_request=value.original_request,
                    status=value.status,
                    created_at=value.created_at,
                )
                for value in requests
            ),
        )

    @application.get(
        "/v1/companies/{company_id}/planning-requests/{request_id}",
        response_model=PlanningRequestDetailResponse,
    )
    def get_planning_request(
        company_id: UUID,
        request_id: UUID,
        context: CompanyContextDependency,
        store: InterpretationStoreDependency,
    ) -> PlanningRequestDetailResponse:
        if company_id != context.company_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="company was not found",
            )
        if context.administrative_role not in ("manager", "company_admin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="manager authority is required",
            )
        try:
            view = store.get_request(context=context, request_id=request_id)
        except PlanningRequestNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="planning request was not found",
            ) from error
        except InterpretationStoreUnavailableError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="planning request state is unavailable",
            ) from error
        return PlanningRequestDetailResponse(
            request_id=view.request_id,
            status=view.status,
            request_version=view.request_version,
            latest_outcome=view.latest_outcome,
            candidate_digest=view.candidate_digest,
            clarifications=tuple(
                ClarificationResponse(
                    question_key=question.question_key,
                    category=question.category,
                    question=question.question,
                    blocks_planning=question.blocks_planning,
                    status=question.status,
                )
                for question in view.clarifications
            ),
            candidate_contract_id=view.candidate_contract_id,
            snapshot_id=view.snapshot_id,
            plan_id=view.plan_id,
            interpretation_job_state=view.interpretation_job_state,
            materialization_job_state=view.materialization_job_state,
            planning_job_state=view.planning_job_state,
        )

    @application.post(
        "/v1/companies/{company_id}/planning-requests/{request_id}/interpret",
        response_model=JobView,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def interpret_planning_request(
        company_id: UUID,
        request_id: UUID,
        context: CompanyContextDependency,
        store: DurableStoreDependency,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> JobView:
        if company_id != context.company_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="company was not found"
            )
        if context.administrative_role not in ("manager", "company_admin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="manager authority is required"
            )
        try:
            return store.ensure_job(
                context=context,
                job_kind="interpretation.run",
                aggregate_id=request_id,
                idempotency_key=idempotency_key,
                command_digest=_job_command_digest(
                    company_id, "interpretation.run", request_id
                ),
                correlation_id=uuid5(request_id, "interpretation.run"),
            )
        except JobNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="planning request was not found"
            ) from error
        except JobIdempotencyConflictError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="job idempotency key conflicts with an earlier command",
            ) from error
        except PermissionError as error:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="manager authority is required",
            ) from error
        except DurableStoreError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="durable planning is unavailable",
            ) from error

    @application.get(
        "/v1/companies/{company_id}/jobs/{job_id}",
        response_model=JobView,
    )
    def get_durable_job(
        company_id: UUID,
        job_id: UUID,
        context: CompanyContextDependency,
        store: DurableStoreDependency,
    ) -> JobView:
        _require_manager_company(company_id, context)
        try:
            return store.get_job(context=context, job_id=job_id)
        except JobNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="job was not found"
            ) from error
        except DurableStoreError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="job state is unavailable",
            ) from error

    @application.post(
        "/v1/companies/{company_id}/jobs/{job_id}/cancel",
        response_model=JobView,
    )
    def cancel_durable_job(
        company_id: UUID,
        job_id: UUID,
        body: JobCancellationRequest,
        context: CompanyContextDependency,
        store: DurableStoreDependency,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> JobView:
        _require_manager_company(company_id, context)
        digest = hashlib.sha256(
            f"{company_id}:{job_id}:{body.reason}".encode()
        ).digest()
        try:
            return store.cancel_job(
                context=context,
                job_id=job_id,
                reason=body.reason,
                idempotency_key=idempotency_key,
                command_digest=digest,
            )
        except JobNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="job was not found"
            ) from error
        except PermissionError as error:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="manager authority is required",
            ) from error
        except JobStateConflictError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="job state changed or the cancellation key conflicts",
            ) from error
        except DurableStoreError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="job cancellation could not be stored",
            ) from error

    @application.get(
        "/v1/companies/{company_id}/operations/metrics",
        response_model=QueueMetrics,
    )
    def durable_metrics(
        company_id: UUID,
        context: CompanyContextDependency,
        store: DurableStoreDependency,
    ) -> QueueMetrics:
        _require_manager_company(company_id, context)
        try:
            return store.metrics(context=context)
        except PermissionError as error:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="manager authority is required",
            ) from error
        except DurableStoreError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="coordination metrics are unavailable",
            ) from error

    @application.get(
        "/v1/companies/{company_id}/me/notifications",
        response_model=NotificationPage,
    )
    def list_notifications(
        company_id: UUID,
        context: CompanyContextDependency,
        store: DurableStoreDependency,
        cursor: str | None = None,
        limit: int = 50,
    ) -> NotificationPage:
        _require_same_company(company_id, context)
        if limit < 1 or limit > 100:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="notification limit must be between 1 and 100",
            )
        after_created_at, after_id = _parse_notification_cursor(cursor)
        try:
            return store.list_notifications(
                context=context,
                after_created_at=after_created_at,
                after_id=after_id,
                limit=limit,
            )
        except DurableStoreError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="notifications are unavailable",
            ) from error

    def advance_notification(
        *,
        company_id: UUID,
        notification_id: UUID,
        action: str,
        context: CompanyContextDependency,
        store: DurableStoreDependency,
    ) -> NotificationView:
        _require_same_company(company_id, context)
        try:
            return store.advance_notification(
                context=context,
                notification_id=notification_id,
                action=action,
            )
        except NotificationNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="notification was not found",
            ) from error
        except DurableStoreError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="notification state could not be stored",
            ) from error

    @application.post(
        "/v1/companies/{company_id}/me/notifications/{notification_id}/seen",
        response_model=NotificationView,
    )
    def mark_notification_seen(
        company_id: UUID,
        notification_id: UUID,
        context: CompanyContextDependency,
        store: DurableStoreDependency,
    ) -> NotificationView:
        return advance_notification(
            company_id=company_id,
            notification_id=notification_id,
            action="seen",
            context=context,
            store=store,
        )

    @application.post(
        "/v1/companies/{company_id}/me/notifications/{notification_id}/acknowledge",
        response_model=NotificationView,
    )
    def acknowledge_notification(
        company_id: UUID,
        notification_id: UUID,
        context: CompanyContextDependency,
        store: DurableStoreDependency,
    ) -> NotificationView:
        return advance_notification(
            company_id=company_id,
            notification_id=notification_id,
            action="acknowledged",
            context=context,
            store=store,
        )

    @application.get(
        "/v1/companies/{company_id}/plans/{plan_id}",
        response_model=PlanReview,
    )
    def get_plan_review(
        company_id: UUID,
        plan_id: UUID,
        context: CompanyContextDependency,
        store: ApprovalStoreDependency,
    ) -> PlanReview:
        _require_manager_company(company_id, context)
        try:
            return store.get_review(context=context, plan_id=plan_id)
        except PlanNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="plan was not found"
            ) from error
        except ApprovalStoreError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="plan review is unavailable",
            ) from error

    @application.get(
        "/v1/companies/{company_id}/plans/{plan_id}/evidence",
        response_model=PlanEvidence,
    )
    def get_plan_evidence(
        company_id: UUID,
        plan_id: UUID,
        context: CompanyContextDependency,
        store: ApprovalStoreDependency,
    ) -> PlanEvidence:
        _require_manager_company(company_id, context)
        try:
            return store.get_evidence(context=context, plan_id=plan_id)
        except PlanNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="plan was not found"
            ) from error
        except ApprovalStoreError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="plan evidence is unavailable",
            ) from error

    def record_plan_decision(
        *,
        decision: Literal["approved", "rejected"],
        company_id: UUID,
        plan_id: UUID,
        body: PlanDecisionRequest,
        context: CompanyContextDependency,
        store: ApprovalStoreDependency,
        idempotency_key: str,
    ) -> ApprovalDecisionResult:
        _require_manager_company(company_id, context)
        try:
            return store.decide(
                context=context,
                plan_id=plan_id,
                command=ApprovalCommand(
                    requirement_id=body.requirement_id,
                    decision=decision,
                    explanation=body.explanation,
                    artifact_digest=body.artifact_digest,
                    binding=body.binding,
                    idempotency_key=idempotency_key,
                    correlation_id=body.correlation_id,
                ),
            )
        except PlanNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="plan was not found"
            ) from error
        except ApprovalAuthorityError as error:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="required approval authority is absent",
            ) from error
        except (ApprovalStaleError, ApprovalIdempotencyConflictError) as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="approval binding is stale or conflicts with an earlier command",
            ) from error
        except ApprovalStoreError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="approval decision could not be stored",
            ) from error

    @application.post(
        "/v1/companies/{company_id}/plans/{plan_id}/approve",
        response_model=ApprovalDecisionResult,
    )
    def approve_plan_requirement(
        company_id: UUID,
        plan_id: UUID,
        body: PlanDecisionRequest,
        context: CompanyContextDependency,
        store: ApprovalStoreDependency,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> ApprovalDecisionResult:
        return record_plan_decision(
            decision="approved",
            company_id=company_id,
            plan_id=plan_id,
            body=body,
            context=context,
            store=store,
            idempotency_key=idempotency_key,
        )

    @application.post(
        "/v1/companies/{company_id}/plans/{plan_id}/reject",
        response_model=ApprovalDecisionResult,
    )
    def reject_plan_requirement(
        company_id: UUID,
        plan_id: UUID,
        body: PlanDecisionRequest,
        context: CompanyContextDependency,
        store: ApprovalStoreDependency,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> ApprovalDecisionResult:
        return record_plan_decision(
            decision="rejected",
            company_id=company_id,
            plan_id=plan_id,
            body=body,
            context=context,
            store=store,
            idempotency_key=idempotency_key,
        )

    @application.post(
        "/v1/companies/{company_id}/plans/{plan_id}/commit",
        response_model=CommitResult,
    )
    def commit_plan(
        company_id: UUID,
        plan_id: UUID,
        body: PlanCommitRequest,
        context: CompanyContextDependency,
        store: ApprovalStoreDependency,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> CommitResult:
        _require_manager_company(company_id, context)
        try:
            return store.commit(
                context=context,
                plan_id=plan_id,
                command=CommitCommand(
                    binding=body.binding,
                    idempotency_key=idempotency_key,
                    correlation_id=body.correlation_id,
                ),
            )
        except PlanNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="plan was not found"
            ) from error
        except (ApprovalAuthorityError, ApprovalIncompleteError) as error:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="all current planning approvals are required",
            ) from error
        except (
            ApprovalStaleError,
            ApprovalIdempotencyConflictError,
            ScheduleConflictError,
        ) as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="shared state changed; replan and approve the new proposal",
            ) from error
        except ApprovalStoreError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="plan could not be committed",
            ) from error

    @application.get(
        "/v1/companies/{company_id}/me/tasks",
        response_model=EmployeeTasksResponse,
    )
    def list_employee_tasks(
        company_id: UUID,
        view: TaskView,
        context: CompanyContextDependency,
        store: EmployeeStoreDependency,
    ) -> EmployeeTasksResponse:
        _require_same_company(company_id, context)
        try:
            tasks = store.list_tasks(context=context, view=view)
        except EmployeeAuthorityError as error:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="an active employee profile is required",
            ) from error
        except EmployeeStoreError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="employee tasks are unavailable",
            ) from error
        return EmployeeTasksResponse(view=view, tasks=tasks)

    @application.post(
        "/v1/companies/{company_id}/tasks/{task_id}/events",
        response_model=TaskTransitionResult,
    )
    def transition_employee_task(
        company_id: UUID,
        task_id: UUID,
        body: TaskTransitionRequest,
        context: CompanyContextDependency,
        store: EmployeeStoreDependency,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> TaskTransitionResult:
        _require_same_company(company_id, context)
        try:
            return store.transition(
                context=context,
                task_id=task_id,
                command=TaskTransitionCommand(
                    command=body.command,
                    expected_task_version=body.expected_task_version,
                    payload=body.payload,
                    idempotency_key=idempotency_key,
                    correlation_id=body.correlation_id,
                ),
            )
        except EmployeeTaskNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="task was not found"
            ) from error
        except EmployeeAuthorityError as error:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="task owner authority is required",
            ) from error
        except (EmployeeStateConflictError, EmployeeIdempotencyConflictError) as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="task state changed or the idempotency key conflicts",
            ) from error
        except EmployeeStoreError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="task transition could not be stored",
            ) from error

    @application.put(
        "/v1/companies/{company_id}/tasks/{task_id}/review-policy",
        response_model=ReviewPolicyResult,
    )
    def set_task_review_policy(
        company_id: UUID,
        task_id: UUID,
        body: TaskReviewPolicyRequest,
        context: CompanyContextDependency,
        store: EmployeeStoreDependency,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> ReviewPolicyResult:
        _require_manager_company(company_id, context)
        try:
            command = ReviewPolicyCommand(
                reviewer_employee_id=body.reviewer_employee_id,
                self_certifiable=body.self_certifiable,
                self_certification_rule=body.self_certification_rule,
                expected_task_version=body.expected_task_version,
                idempotency_key=idempotency_key,
                correlation_id=body.correlation_id,
            )
            return store.set_review_policy(context=context, task_id=task_id, command=command)
        except EmployeeTaskNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="task or reviewer was not found",
            ) from error
        except EmployeeAuthorityError as error:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="manager authority is required",
            ) from error
        except (EmployeeStateConflictError, EmployeeIdempotencyConflictError) as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="task state changed or the idempotency key conflicts",
            ) from error
        except EmployeeStoreError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="review policy could not be stored",
            ) from error

    @application.post(
        "/v1/companies/{company_id}/tasks/{task_id}/submissions",
        response_model=SubmissionResult,
        status_code=status.HTTP_201_CREATED,
    )
    def submit_employee_task(
        company_id: UUID,
        task_id: UUID,
        body: TaskSubmissionRequest,
        response: Response,
        context: CompanyContextDependency,
        store: EmployeeStoreDependency,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> SubmissionResult:
        _require_same_company(company_id, context)
        try:
            result = store.submit(
                context=context,
                task_id=task_id,
                command=SubmissionCommand(
                    narrative=body.narrative,
                    external_evidence_refs=body.external_evidence_refs,
                    file_ids=body.file_ids,
                    reported_active_minutes=body.reported_active_minutes,
                    expected_task_version=body.expected_task_version,
                    idempotency_key=idempotency_key,
                    correlation_id=body.correlation_id,
                ),
            )
        except EmployeeTaskNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="task was not found"
            ) from error
        except EmployeeAuthorityError as error:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="task owner and review policy are required",
            ) from error
        except (EmployeeStateConflictError, EmployeeIdempotencyConflictError) as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="task state changed or the idempotency key conflicts",
            ) from error
        except EmployeeStoreError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="submission could not be stored",
            ) from error
        if result.replayed:
            response.status_code = status.HTTP_200_OK
        return result

    @application.get(
        "/v1/companies/{company_id}/submissions/{submission_id}",
        response_model=SubmissionReviewView,
    )
    def get_task_submission(
        company_id: UUID,
        submission_id: UUID,
        context: CompanyContextDependency,
        store: EmployeeStoreDependency,
    ) -> SubmissionReviewView:
        _require_same_company(company_id, context)
        try:
            return store.get_submission(context=context, submission_id=submission_id)
        except EmployeeTaskNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="submission was not found",
            ) from error
        except EmployeeStoreError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="submission is unavailable",
            ) from error

    @application.get(
        "/v1/companies/{company_id}/reviews/pending",
        response_model=PendingReviewsResponse,
    )
    def list_pending_reviews(
        company_id: UUID,
        context: CompanyContextDependency,
        store: EmployeeStoreDependency,
    ) -> PendingReviewsResponse:
        _require_same_company(company_id, context)
        try:
            return PendingReviewsResponse(reviews=store.list_pending_reviews(context=context))
        except EmployeeAuthorityError as error:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="reviewer authority is required",
            ) from error
        except EmployeeStoreError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="pending reviews are unavailable",
            ) from error

    @application.post(
        "/v1/companies/{company_id}/submissions/{submission_id}/review",
        response_model=ReviewResult,
    )
    def review_task_submission(
        company_id: UUID,
        submission_id: UUID,
        body: SubmissionReviewRequest,
        context: CompanyContextDependency,
        store: EmployeeStoreDependency,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> ReviewResult:
        _require_same_company(company_id, context)
        try:
            return store.review(
                context=context,
                submission_id=submission_id,
                command=ReviewCommand(
                    expected_submission_version=body.expected_submission_version,
                    submission_digest=body.submission_digest,
                    decision=body.decision,
                    criterion_findings=body.criterion_findings,
                    correction_request=body.correction_request,
                    idempotency_key=idempotency_key,
                    correlation_id=body.correlation_id,
                ),
            )
        except EmployeeTaskNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="submission was not found",
            ) from error
        except EmployeeAuthorityError as error:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="assigned reviewer authority is required",
            ) from error
        except (EmployeeStateConflictError, EmployeeIdempotencyConflictError) as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="submission changed or the idempotency key conflicts",
            ) from error
        except EmployeeStoreError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="submission review could not be stored",
            ) from error

    return application


def _require_manager_company(company_id: UUID, context: CompanyContextDependency) -> None:
    _require_same_company(company_id, context)
    if context.administrative_role not in ("manager", "company_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="manager authority is required"
        )


def _require_company_admin(company_id: UUID, context: CompanyContextDependency) -> None:
    _require_same_company(company_id, context)
    if context.administrative_role != "company_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="company administrator authority is required",
        )


def _require_same_company(company_id: UUID, context: CompanyContextDependency) -> None:
    if company_id != context.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company was not found")


app = create_app()


def run(*, reload: bool = False) -> None:
    uvicorn.run(
        "coordination.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=reload,
    )
