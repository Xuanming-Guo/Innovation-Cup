"""Immutable ALTO proposals. No field in this contract is a solver decision."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, Self
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator

from coordination.planning.contracts import (
    ScheduleBlock,
    SchedulingKind,
    StrictPlanningModel,
    TaskPlacement,
    ValidationIssue,
    canonical_digest,
)

FixedResult = Literal["CHECKED", "VIOLATIONS_FOUND", "UNABLE_TO_VERIFY", "INVALID_CANDIDATE"]
RuleCategoryKey = Literal[
    "owner",
    "working_hours",
    "busy_time",
    "effort",
    "eligibility",
    "dependencies",
    "participants",
    "handoffs",
    "protected_time",
    "reviews",
    "deadlines",
    "authorised_scope",
]
MAX_FIXED_PLAN_PROPOSALS = 5

RULE_CATEGORY_TITLES: dict[RuleCategoryKey, str] = {
    "owner": "Owner",
    "working_hours": "Working hours",
    "busy_time": "Busy time",
    "effort": "Effort",
    "eligibility": "Eligibility",
    "dependencies": "Dependencies",
    "participants": "Participants",
    "handoffs": "Handoffs",
    "protected_time": "Protected time",
    "reviews": "Reviews",
    "deadlines": "Deadlines",
    "authorised_scope": "Authorised scope",
}
RULE_CATEGORY_BY_FAMILY: dict[str, RuleCategoryKey] = {
    "task_definition": "authorised_scope",
    "working_window": "working_hours",
    "resource_capacity": "busy_time",
    "effort": "effort",
    "eligibility": "eligibility",
    "dependency": "dependencies",
    "active_participants": "participants",
    "fixed_attendance": "participants",
    "shared_resource": "participants",
    "execution_gate": "handoffs",
    "reservation": "protected_time",
    "acceptance_review": "reviews",
    "task_review_policy": "reviews",
    "deadline": "deadlines",
    "movement": "authorised_scope",
    "segmentation": "authorised_scope",
    "priority": "authorised_scope",
}


def rule_categories_for_family(
    family: str,
) -> tuple[tuple[RuleCategoryKey, ...], tuple[str, ...]]:
    """Map an allowlisted family to each canonical check it actually supports."""
    categories: tuple[RuleCategoryKey, ...]
    if family == "execution_gate":
        categories = ("dependencies", "handoffs")
    elif family == "eligibility":
        categories = ("eligibility", "owner")
    elif family == "resource_capacity":
        categories = ("busy_time", "working_hours")
    else:
        categories = (RULE_CATEGORY_BY_FAMILY.get(family, "authorised_scope"),)
    return categories, tuple(RULE_CATEGORY_TITLES[item] for item in categories)


def rule_category_for_family(family: str) -> tuple[RuleCategoryKey, str]:
    """Return the primary category for older consumers of the rule projection."""
    categories, titles = rule_categories_for_family(family)
    return categories[0], titles[0]


class FixedInterval(StrictPlanningModel):
    start: datetime
    end: datetime

    @field_validator("start", "end")
    @classmethod
    def offset_required(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("candidate timestamps require an explicit UTC offset")
        return value

    @model_validator(mode="after")
    def positive_interval(self) -> Self:
        if self.end.astimezone(UTC) <= self.start.astimezone(UTC):
            raise ValueError("candidate interval must be positive")
        return self


class ProposedBlock(FixedInterval):
    resource_id: UUID
    role: Literal["owner", "participant", "shared"]
    capacity_units: int = Field(ge=1, le=16)


class ProposedTask(FixedInterval):
    task_id: UUID
    expected_work_version: int | None = Field(default=None, ge=1)
    priority_tier: int = Field(default=5, ge=0, le=9)
    task_key: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=160)
    purpose: str = Field(min_length=1, max_length=2000)
    deliverable: str = Field(min_length=1, max_length=2000)
    acceptance_criteria: tuple[str, ...] = Field(min_length=1, max_length=20)
    scheduling_kind: SchedulingKind
    owner_resource_id: UUID | None
    effort_minutes: int = Field(ge=0, le=1_000_000)
    blocks: tuple[ProposedBlock, ...] = Field(max_length=2000)
    review_policy: Literal["exact_review", "self_certifiable_internal_draft", "not_required"]
    reviewer_resource_ids: tuple[UUID, ...] = Field(max_length=100)
    confidentiality: Literal["company", "restricted"]
    evidence_rule_ids: tuple[str, ...] = Field(min_length=1, max_length=100)
    # Safe references only; employee-facing prose is rendered after verification.
    audience_resource_ids: tuple[UUID, ...] = Field(max_length=100)


class ProposedGate(StrictPlanningModel):
    rule_id: str = Field(min_length=1, max_length=128)
    predecessor_task_id: UUID
    successor_task_id: UUID
    required_state: Literal["submitted", "accepted", "approved", "self_certified"]
    artifact_version_policy: Literal["exact_submitted_version"]
    review_task_ids: tuple[UUID, ...] = Field(max_length=100)
    minimum_lag_minutes: int = Field(ge=0, le=1_000_000)


class CompletePlanDraft(StrictPlanningModel):
    """Model output excludes tenant, actor, approval state, and trusted digests."""

    timezone: str = Field(min_length=1, max_length=64)
    tasks: tuple[ProposedTask, ...] = Field(min_length=1, max_length=2000)
    gates: tuple[ProposedGate, ...] = Field(max_length=10_000)
    assumptions: tuple[str, ...] = Field(max_length=30)
    unresolved_items: tuple[str, ...] = Field(max_length=30)

    @field_validator("timezone")
    @classmethod
    def iana_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("timezone must be an IANA timezone") from error
        return value

    def semantic_payload(self) -> dict[str, object]:
        # Different JSON array order / equivalent offsets are not new candidates.
        value = self.model_dump(mode="json")
        tasks = []
        for task in sorted(self.tasks, key=lambda item: str(item.task_id)):
            item = task.model_dump(mode="json")
            item["start"] = task.start.astimezone(UTC).isoformat()
            item["end"] = task.end.astimezone(UTC).isoformat()
            blocks = []
            for block in task.blocks:
                block_value = block.model_dump(mode="json")
                block_value["start"] = block.start.astimezone(UTC).isoformat()
                block_value["end"] = block.end.astimezone(UTC).isoformat()
                blocks.append(block_value)
            item["blocks"] = sorted(
                blocks,
                key=lambda block: (
                    str(block["resource_id"]),
                    str(block["start"]),
                    str(block["end"]),
                    str(block["role"]),
                ),
            )
            for key in ("evidence_rule_ids", "reviewer_resource_ids", "audience_resource_ids"):
                item[key] = sorted(item[key])
            tasks.append(item)
        value["tasks"] = tasks
        value["gates"] = sorted(value["gates"], key=lambda gate: str(gate["rule_id"]))
        return value

    @property
    def semantic_digest(self) -> str:
        return canonical_digest(self.semantic_payload())


class ProposalChange(StrictPlanningModel):
    task_id: UUID
    changed_fields: tuple[str, ...]


class PlanProposalV2(StrictPlanningModel):
    schema_version: Literal["plan-proposal.v2"] = "plan-proposal.v2"
    proposal_id: UUID
    company_id: UUID
    demo_run_id: UUID | None
    request_id: UUID
    snapshot_id: UUID
    snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    version: int = Field(ge=1, le=MAX_FIXED_PLAN_PROPOSALS)
    parent_proposal_id: UUID | None
    author_kind: Literal["ai_authored", "authored_replay", "authored_check"]
    draft: CompletePlanDraft
    candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    changes: tuple[ProposalChange, ...]

    @model_validator(mode="after")
    def immutable_binding(self) -> Self:
        if self.candidate_digest != self.draft.semantic_digest:
            raise ValueError("candidate semantic digest does not match the complete draft")
        if (self.version == 1) != (self.parent_proposal_id is None):
            raise ValueError("replacement proposals must bind their exact parent")
        return self


def proposal_changes(
    parent: PlanProposalV2 | None, draft: CompletePlanDraft
) -> tuple[ProposalChange, ...]:
    if parent is None:
        return ()
    previous = {task.task_id: task.model_dump(mode="json") for task in parent.draft.tasks}
    changes = []
    for task in draft.tasks:
        before = previous.get(task.task_id, {})
        fields = tuple(
            sorted(
                key
                for key, value in task.model_dump(mode="json").items()
                if before.get(key) != value
            )
        )
        if fields:
            changes.append(ProposalChange(task_id=task.task_id, changed_fields=fields))
    return tuple(sorted(changes, key=lambda item: str(item.task_id)))


class FixedRuleResult(StrictPlanningModel):
    rule_id: str
    result: Literal["pass", "violation", "unable"]
    category_key: RuleCategoryKey
    category_title: str
    category_keys: tuple[RuleCategoryKey, ...]
    category_titles: tuple[str, ...]
    encoding_version: str
    candidate_values: dict[str, Any] = Field(default_factory=dict)
    # Persisted deliberately into each rule result's fixed_values, not the broad run report.
    technical_expression: str | None = Field(default=None, exclude=True)


class FixedCheckReport(StrictPlanningModel):
    run_kind: Literal["fixed_candidate_verification"] = "fixed_candidate_verification"
    compiler_version: str
    verifier_version: str
    solver_version: str
    candidate_digest_before: str
    candidate_digest_after: str
    snapshot_digest: str
    native_status: Literal["sat", "unsat", "unknown", "invalid"]
    product_status: FixedResult
    required_rule_ids: tuple[str, ...]
    covered_rule_ids: tuple[str, ...]
    unverified_required_rule_ids: tuple[str, ...]
    diagnostic_rule_ids: tuple[str, ...]
    rule_results: tuple[FixedRuleResult, ...] = ()
    diagnostics: tuple[ValidationIssue, ...]
    duration_ms: int = Field(ge=0)
    timeout_ms: int = Field(ge=1)
    resource_limit: int = Field(ge=1)


class FixedValidationReport(StrictPlanningModel):
    validator_version: str
    candidate_digest: str
    snapshot_digest: str
    passed: bool
    issues: tuple[ValidationIssue, ...]


class FixedCandidateResult(StrictPlanningModel):
    proposal: PlanProposalV2
    check: FixedCheckReport
    validation: FixedValidationReport | None
    placements: tuple[TaskPlacement, ...]
    blocks: tuple[ScheduleBlock, ...]

    @property
    def approvable(self) -> bool:
        return (
            self.check.product_status == "CHECKED"
            and self.validation is not None
            and self.validation.passed
            and self.validation.candidate_digest == self.proposal.candidate_digest
            and not self.check.unverified_required_rule_ids
        )
