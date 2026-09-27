from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictProjection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceExcerpt(StrictProjection):
    locator: str = Field(min_length=1, max_length=240)
    text: str = Field(min_length=1, max_length=12_000)


class SourceVersionEvidence(StrictProjection):
    source_id: UUID
    source_version_id: UUID
    source_kind: Literal["upload", "calendar", "document", "fixture"]
    authority_status: Literal["authoritative", "unverified"]
    classification: Literal["internal", "confidential", "restricted"]
    retrieved_at: datetime
    expires_at: datetime | None
    freshness: Literal["current", "stale"]
    content_sha256_hex: str = Field(pattern=r"^[0-9a-f]{64}$")
    excerpts: tuple[EvidenceExcerpt, ...] = Field(max_length=20)

    @model_validator(mode="after")
    def validate_times(self) -> SourceVersionEvidence:
        if self.retrieved_at.utcoffset() is None:
            raise ValueError("retrieved_at must be timezone-aware")
        if self.expires_at is not None and self.expires_at.utcoffset() is None:
            raise ValueError("expires_at must be timezone-aware")
        return self


class PermittedEmployee(StrictProjection):
    employee_id: UUID
    timezone: str = Field(min_length=1, max_length=64)
    capability_keys: tuple[str, ...] = Field(max_length=200)
    permission_keys: tuple[str, ...] = Field(max_length=200)
    status: Literal["active"]

    @model_validator(mode="after")
    def canonical_keys(self) -> PermittedEmployee:
        if tuple(sorted(set(self.capability_keys))) != self.capability_keys:
            raise ValueError("capability keys must be unique and ordered")
        if tuple(sorted(set(self.permission_keys))) != self.permission_keys:
            raise ValueError("permission keys must be unique and ordered")
        return self


class ExistingCommitment(StrictProjection):
    commitment_id: UUID
    employee_id: UUID
    start_at: datetime
    end_at: datetime
    active_minutes: int = Field(ge=0)
    movement: Literal["fixed", "protected", "movable_with_authority"]

    @model_validator(mode="after")
    def validate_window(self) -> ExistingCommitment:
        if self.start_at.utcoffset() is None or self.end_at.utcoffset() is None:
            raise ValueError("commitment times must be timezone-aware")
        if self.end_at <= self.start_at:
            raise ValueError("commitment end must follow start")
        return self


class CapacityFact(StrictProjection):
    employee_id: UUID
    horizon_start: datetime
    horizon_end: datetime
    available_active_minutes: int = Field(ge=0)
    source: Literal["working_rule", "availability_snapshot", "reduced_cross_team"]


class ExistingDependency(StrictProjection):
    predecessor_id: UUID
    successor_id: UUID
    dependency_type: Literal["finish_to_start", "acceptance_to_start", "information"]


class MissingDataMarker(StrictProjection):
    kind: Literal[
        "commitments",
        "capacity",
        "deadline_policy",
        "priority_policy",
        "employee_scope",
        "source_content",
    ]
    reason: str = Field(min_length=1, max_length=500)
    blocking: bool


class ClarificationAnswer(StrictProjection):
    response_id: UUID
    question_key: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    category: Literal["missing_data", "authority", "timezone", "ambiguity", "disclosure"]
    question: str = Field(min_length=1, max_length=1000)
    answer: str = Field(min_length=1, max_length=4000)
    answered_at: datetime
    authority_role: Literal["manager", "company_admin"]

    @model_validator(mode="after")
    def validate_answered_at(self) -> ClarificationAnswer:
        if self.answered_at.utcoffset() is None:
            raise ValueError("answered_at must be timezone-aware")
        return self


class InterpretationProjection(StrictProjection):
    projection_version: Literal["interpretation-projection.v1"]
    company_id: UUID
    request_id: UUID
    request_version: int = Field(ge=1)
    original_request: str = Field(min_length=1, max_length=8000)
    retrieved_at: datetime
    requested_priority_key: str | None = Field(max_length=80)
    requested_deadline: datetime | None
    requested_deadline_timezone: str | None = Field(max_length=64)
    sources: tuple[SourceVersionEvidence, ...] = Field(max_length=50)
    employees: tuple[PermittedEmployee, ...] = Field(max_length=500)
    commitments: tuple[ExistingCommitment, ...] = Field(max_length=5000)
    capacity: tuple[CapacityFact, ...] = Field(max_length=5000)
    dependencies: tuple[ExistingDependency, ...] = Field(max_length=5000)
    clarification_answers: tuple[ClarificationAnswer, ...] = Field(
        default=(), max_length=100
    )
    supported_constraint_types: tuple[str, ...] = Field(min_length=1, max_length=30)
    missing_data: tuple[MissingDataMarker, ...] = Field(max_length=20)

    @model_validator(mode="after")
    def validate_request_times(self) -> InterpretationProjection:
        if self.retrieved_at.utcoffset() is None:
            raise ValueError("retrieved_at must be timezone-aware")
        if self.requested_deadline is not None and self.requested_deadline.utcoffset() is None:
            raise ValueError("requested_deadline must be timezone-aware")
        if (self.requested_deadline is None) != (self.requested_deadline_timezone is None):
            raise ValueError("requested deadline and timezone must be supplied together")
        return self

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()
