from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from coordination import __version__
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
from coordination.interpretation.dependencies import (
    InterpretationGatewayDependency,
    InterpretationStoreDependency,
)
from coordination.interpretation.persistence import (
    CreatePlanningRequest,
    InterpretationStateConflictError,
    InterpretationStoreUnavailableError,
    PlanningRequestIdempotencyConflictError,
    PlanningRequestNotFoundError,
    PlanningRequestSourceNotFoundError,
)
from coordination.interpretation.service import (
    InterpretationBudgetExceededError,
    InterpretationExecutionError,
    InterpretationService,
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


class InterpretationResponse(StrictResponse):
    run_id: UUID
    status: Literal["admitted", "clarification_required", "rejected"]
    contract_digest: str
    projection_digest: str
    issue_codes: tuple[str, ...]


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


class PlanDecisionRequest(StrictResponse):
    requirement_id: UUID
    artifact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    binding: PlanBinding
    explanation: str = Field(default="", max_length=2000)
    correlation_id: UUID


class PlanCommitRequest(StrictResponse):
    binding: PlanBinding
    correlation_id: UUID


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
        )

    @application.post(
        "/v1/companies/{company_id}/planning-requests/{request_id}/interpret",
        response_model=InterpretationResponse,
    )
    def interpret_planning_request(
        company_id: UUID,
        request_id: UUID,
        context: CompanyContextDependency,
        store: InterpretationStoreDependency,
        gateway: InterpretationGatewayDependency,
        settings: SettingsDependency,
    ) -> InterpretationResponse:
        if company_id != context.company_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="company was not found"
            )
        if context.administrative_role not in ("manager", "company_admin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="manager authority is required"
            )
        retrieval_run_id = uuid4()
        try:
            bundle = store.load_projection(
                context=context,
                request_id=request_id,
                retrieval_run_id=retrieval_run_id,
            )
            service = InterpretationService(
                gateway=gateway,
                recorder=store.recorder(
                    context=context,
                    request_id=request_id,
                    retrieval_run_id=retrieval_run_id,
                ),
                max_projection_characters=settings.gemini_max_projection_characters,
            )
            outcome = service.interpret(bundle.projection)
        except (PlanningRequestNotFoundError, PlanningRequestSourceNotFoundError) as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="planning request was not found"
            ) from error
        except InterpretationBudgetExceededError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="interpretation input exceeds policy",
            ) from error
        except InterpretationStateConflictError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="planning request is already being interpreted or has a current result",
            ) from error
        except InterpretationExecutionError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"model interpretation failed: {error.code}",
            ) from error
        except InterpretationStoreUnavailableError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="interpretation state is unavailable",
            ) from error
        return InterpretationResponse(
            run_id=outcome.run_id,
            status=outcome.status,
            contract_digest=outcome.contract_digest,
            projection_digest=outcome.projection_digest,
            issue_codes=tuple(issue.code for issue in outcome.admission.issues),
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

    return application


def _require_manager_company(company_id: UUID, context: CompanyContextDependency) -> None:
    if company_id != context.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company was not found")
    if context.administrative_role not in ("manager", "company_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="manager authority is required"
        )


app = create_app()


def run(*, reload: bool = False) -> None:
    uvicorn.run(
        "coordination.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=reload,
    )
