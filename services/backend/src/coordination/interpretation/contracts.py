from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceBasis(StrictContract):
    kind: Literal["evidence"]
    source_version_id: UUID
    locator: str = Field(min_length=1, max_length=240)
    claim: str = Field(min_length=1, max_length=1000)


class AssumptionBasis(StrictContract):
    kind: Literal["assumption"]
    assumption_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")


CandidateBasis = Annotated[EvidenceBasis | AssumptionBasis, Field(discriminator="kind")]


class CandidateEstimate(StrictContract):
    active_minutes: int = Field(ge=1, le=100_800)
    lower_minutes: int | None = Field(ge=1, le=100_800)
    upper_minutes: int | None = Field(ge=1, le=100_800)
    bases: tuple[CandidateBasis, ...] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def validate_range(self) -> CandidateEstimate:
        if self.lower_minutes is not None and self.lower_minutes > self.active_minutes:
            raise ValueError("lower_minutes cannot exceed active_minutes")
        if self.upper_minutes is not None and self.upper_minutes < self.active_minutes:
            raise ValueError("upper_minutes cannot be below active_minutes")
        return self


class CandidateDeadline(StrictContract):
    requested_at: datetime
    timezone: str = Field(min_length=1, max_length=64)
    flexibility: Literal["fixed", "negotiable", "unknown"]
    bases: tuple[CandidateBasis, ...] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def validate_timezone(self) -> CandidateDeadline:
        if self.requested_at.utcoffset() is None:
            raise ValueError("requested_at must include a UTC offset")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError("timezone must be a valid IANA timezone") from error
        return self


class CandidateRequirement(StrictContract):
    requirement_key: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    kind: Literal["skill", "qualification", "permission", "tool", "input", "review"]
    description: str = Field(min_length=1, max_length=1000)
    strength: Literal["hard", "preferred"]
    minimum_level: str | None = Field(max_length=120)
    bases: tuple[CandidateBasis, ...] = Field(min_length=1, max_length=12)


class CandidateTask(StrictContract):
    task_key: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    title: str = Field(min_length=1, max_length=160)
    purpose: str = Field(min_length=1, max_length=2000)
    deliverable: str = Field(min_length=1, max_length=2000)
    acceptance_criteria: tuple[str, ...] = Field(min_length=1, max_length=20)
    timing_type: Literal["flexible_active", "fixed_attendance", "passive_wait"]
    estimate: CandidateEstimate
    deadline: CandidateDeadline | None
    requirements: tuple[CandidateRequirement, ...] = Field(max_length=30)
    bases: tuple[CandidateBasis, ...] = Field(min_length=1, max_length=20)

    @field_validator("acceptance_criteria")
    @classmethod
    def validate_acceptance_criteria(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        stripped = tuple(value.strip() for value in values)
        if any(not value or len(value) > 1000 for value in stripped):
            raise ValueError("acceptance criteria must contain 1-1000 characters")
        return stripped


class CandidateDependency(StrictContract):
    predecessor_task_key: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    successor_task_key: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    dependency_type: Literal["finish_to_start", "acceptance_to_start", "information"]
    minimum_lag_minutes: int = Field(ge=0, le=43_200)
    bases: tuple[CandidateBasis, ...] = Field(min_length=1, max_length=12)


class CandidateAssumption(StrictContract):
    assumption_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    statement: str = Field(min_length=1, max_length=1000)
    material: bool
    authority_required: Literal[
        "requester",
        "project_manager",
        "company_admin",
        "source_owner",
        "policy_owner",
        "unknown",
    ]


class CandidateClarification(StrictContract):
    question_key: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    category: Literal["missing_data", "authority", "timezone", "ambiguity", "disclosure"]
    question: str = Field(min_length=1, max_length=1000)
    blocks_planning: bool
    related_task_keys: tuple[str, ...] = Field(max_length=20)


class UnsupportedRequest(StrictContract):
    code: Literal[
        "unsupported_constraint",
        "unsupported_action",
        "insufficient_context",
        "authority_unknown",
        "sensitive_request",
    ]
    description: str = Field(min_length=1, max_length=1000)
    related_task_keys: tuple[str, ...] = Field(max_length=20)


class CandidateTaskContract(StrictContract):
    schema_version: Literal["candidate-task-contract.v1"]
    company_id: UUID
    request_id: UUID
    request_version: int = Field(ge=1)
    tasks: tuple[CandidateTask, ...] = Field(max_length=100)
    dependencies: tuple[CandidateDependency, ...] = Field(max_length=300)
    assumptions: tuple[CandidateAssumption, ...] = Field(max_length=100)
    clarifications: tuple[CandidateClarification, ...] = Field(max_length=100)
    unsupported: tuple[UnsupportedRequest, ...] = Field(max_length=100)
