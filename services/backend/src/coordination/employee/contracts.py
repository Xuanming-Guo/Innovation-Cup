from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TaskView = Literal["today", "upcoming", "blocked", "submitted"]
TaskCommand = Literal[
    "acknowledge",
    "start",
    "block",
    "unblock",
    "progress",
    "flag_estimate",
    "flag_skill",
    "flag_input",
    "flag_availability",
]


def canonical_digest(payload: object) -> str:
    value = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(value).hexdigest()


class StrictEmployeeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ApprovedBrief(StrictEmployeeModel):
    brief_version_id: UUID
    version: int = Field(gt=0)
    content: dict[str, object]


class EmployeeTask(StrictEmployeeModel):
    task_id: UUID
    task_key: str
    title: str
    scheduling_kind: str
    status: str
    row_version: int = Field(gt=0)
    start_at: datetime
    finish_at: datetime
    reviewer_name: str | None
    latest_submission_id: UUID | None
    latest_submission_version: int | None
    approved_brief: ApprovedBrief | None


class TaskTransitionCommand(StrictEmployeeModel):
    command: TaskCommand
    payload: dict[str, object] = Field(default_factory=dict)
    expected_task_version: int = Field(gt=0)
    idempotency_key: str = Field(min_length=16, max_length=128)
    correlation_id: UUID

    @property
    def digest(self) -> str:
        return canonical_digest(self.model_dump(mode="json", exclude={"idempotency_key"}))


class TaskTransitionResult(StrictEmployeeModel):
    event_id: UUID
    task_status: str
    task_version: int = Field(gt=0)
    replayed: bool


class ReviewPolicyCommand(StrictEmployeeModel):
    reviewer_employee_id: UUID | None = None
    self_certifiable: bool = False
    self_certification_rule: str = Field(default="", max_length=1000)
    expected_task_version: int = Field(gt=0)
    idempotency_key: str = Field(min_length=16, max_length=128)
    correlation_id: UUID

    @model_validator(mode="after")
    def valid_policy(self) -> ReviewPolicyCommand:
        rule = self.self_certification_rule.strip()
        if self.self_certifiable != bool(rule):
            raise ValueError("self-certification requires one explicit deterministic rule")
        if self.reviewer_employee_id is None and not self.self_certifiable:
            raise ValueError("a reviewer or self-certification rule is required")
        return self

    @property
    def digest(self) -> str:
        return canonical_digest(self.model_dump(mode="json", exclude={"idempotency_key"}))


class ReviewPolicyResult(StrictEmployeeModel):
    policy_id: UUID
    version: int = Field(gt=0)
    task_version: int = Field(gt=0)
    replayed: bool


class SubmissionCommand(StrictEmployeeModel):
    narrative: str = Field(min_length=1, max_length=12000)
    external_evidence_refs: tuple[str, ...] = Field(default=(), max_length=50)
    file_ids: tuple[UUID, ...] = Field(default=(), max_length=20)
    reported_active_minutes: int | None = Field(default=None, ge=0, le=100_000)
    expected_task_version: int = Field(gt=0)
    idempotency_key: str = Field(min_length=16, max_length=128)
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
    def unique_files(self) -> SubmissionCommand:
        if len(self.file_ids) != len(set(self.file_ids)):
            raise ValueError("file_ids must be unique")
        return self

    @property
    def submission_digest(self) -> str:
        return canonical_digest(
            {
                "narrative": self.narrative.strip(),
                "external_evidence_refs": self.external_evidence_refs,
                "file_ids": tuple(sorted(str(value) for value in self.file_ids)),
                "reported_active_minutes": self.reported_active_minutes,
                "expected_task_version": self.expected_task_version,
            }
        )

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                **self.model_dump(mode="json", exclude={"idempotency_key"}),
                "submission_digest": self.submission_digest,
            }
        )


class SubmissionResult(StrictEmployeeModel):
    submission_id: UUID
    version: int = Field(gt=0)
    state: str
    task_version: int = Field(gt=0)
    replayed: bool


class SubmissionFile(StrictEmployeeModel):
    file_id: UUID
    display_filename: str
    detected_mime_type: str
    size_bytes: int = Field(gt=0)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SubmissionReviewView(StrictEmployeeModel):
    submission_id: UUID
    task_id: UUID
    task_title: str
    version: int = Field(gt=0)
    state: str
    narrative: str
    external_evidence_refs: tuple[str, ...]
    submission_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    submitting_employee_id: UUID
    submitting_employee_name: str
    review_policy_version: int = Field(gt=0)
    submitted_at: datetime
    files: tuple[SubmissionFile, ...]


class ReviewCommand(StrictEmployeeModel):
    expected_submission_version: int = Field(gt=0)
    submission_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["accepted", "revision_requested"]
    criterion_findings: tuple[dict[str, object], ...] = Field(default=(), max_length=100)
    correction_request: str = Field(default="", max_length=4000)
    idempotency_key: str = Field(min_length=16, max_length=128)
    correlation_id: UUID

    @model_validator(mode="after")
    def valid_decision(self) -> ReviewCommand:
        correction = self.correction_request.strip()
        if (self.decision == "revision_requested") != bool(correction):
            raise ValueError("only revision requests require correction instructions")
        return self

    @property
    def digest(self) -> str:
        return canonical_digest(self.model_dump(mode="json", exclude={"idempotency_key"}))


class ReviewResult(StrictEmployeeModel):
    review_id: UUID
    decision: Literal["accepted", "revision_requested"]
    task_status: str
    task_version: int = Field(gt=0)
    replayed: bool
