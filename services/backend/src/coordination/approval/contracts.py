from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ApprovalDomain = Literal["planning", "disclosure"]
ApprovalDecision = Literal["approved", "rejected"]
ApprovalRequirementStatus = Literal["pending", "approved", "rejected", "expired"]
PlanReviewStatus = Literal["proposed", "approved", "rejected", "committed", "stale"]


def command_digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class StrictApprovalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PlanBinding(StrictApprovalModel):
    proposal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    base_company_revision: int = Field(ge=0)
    policy_revision: int = Field(ge=0)
    policy_version: str = Field(min_length=1, max_length=120)


class PlanTaskView(StrictApprovalModel):
    task_id: UUID
    task_key: str
    title: str
    scheduling_kind: str
    start_at: datetime
    finish_at: datetime
    owner_resource_id: UUID | None

    @model_validator(mode="after")
    def valid_window(self) -> PlanTaskView:
        if self.start_at.utcoffset() is None or self.finish_at.utcoffset() is None:
            raise ValueError("task timestamps must include a UTC offset")
        if self.finish_at <= self.start_at:
            raise ValueError("task finish must follow task start")
        return self


class PlanChangeView(StrictApprovalModel):
    change_id: UUID
    kind: str
    summary: str
    affected_team_id: UUID | None
    before_value: dict[str, object] | None
    after_value: dict[str, object] | None
    supporting_constraint_keys: tuple[str, ...]


class ApprovalRequirementView(StrictApprovalModel):
    requirement_id: UUID
    domain: ApprovalDomain
    kind: str
    authority_kind: str
    authority_team_id: UUID | None
    artifact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str
    status: ApprovalRequirementStatus
    decided_by_membership_id: UUID | None
    decided_at: datetime | None
    expires_at: datetime | None


class PlanReview(StrictApprovalModel):
    plan_id: UUID
    request_id: UUID
    request_summary: str
    classification: str
    status: PlanReviewStatus
    binding: PlanBinding
    tasks: tuple[PlanTaskView, ...]
    changes: tuple[PlanChangeView, ...]
    requirements: tuple[ApprovalRequirementView, ...]
    can_commit: bool


class ConstraintEvidence(StrictApprovalModel):
    constraint_key: str
    family: str
    strength: str
    confidentiality: str
    source_version_ids: tuple[UUID, ...]
    authority_refs: tuple[str, ...]


class SolverDiagnostic(StrictApprovalModel):
    classification: str
    raw_status: str
    termination: str
    solver_version: str
    compiler_version: str | None
    validator_version: str | None
    runtime_ms: int = Field(ge=0)
    objective_vector: tuple[dict[str, object], ...]
    diagnostic_constraint_keys: tuple[str, ...]


class PlanEvidence(StrictApprovalModel):
    plan_id: UUID
    constraints: tuple[ConstraintEvidence, ...]
    assumptions: tuple[str, ...]
    solver: SolverDiagnostic


class ApprovalCommand(StrictApprovalModel):
    requirement_id: UUID
    decision: ApprovalDecision
    explanation: str = Field(default="", max_length=2000)
    artifact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    binding: PlanBinding
    idempotency_key: str = Field(min_length=16, max_length=128)
    correlation_id: UUID

    @field_validator("explanation")
    @classmethod
    def rejection_explained(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def valid_rejection(self) -> ApprovalCommand:
        if self.decision == "rejected" and not self.explanation:
            raise ValueError("a rejection requires an explanation")
        return self

    @property
    def digest(self) -> str:
        return command_digest(self.model_dump(mode="json", exclude={"idempotency_key"}))


class ApprovalDecisionResult(StrictApprovalModel):
    decision_id: UUID
    decision: ApprovalDecision
    replayed: bool


class CommitCommand(StrictApprovalModel):
    binding: PlanBinding
    idempotency_key: str = Field(min_length=16, max_length=128)
    correlation_id: UUID

    @property
    def digest(self) -> str:
        return command_digest(self.model_dump(mode="json", exclude={"idempotency_key"}))


class CommitResult(StrictApprovalModel):
    commitment_id: UUID
    status: Literal["committed"]
    company_revision: int = Field(gt=0)
    replayed: bool
