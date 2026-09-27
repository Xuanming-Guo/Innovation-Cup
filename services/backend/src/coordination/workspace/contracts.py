from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from coordination.employee.contracts import EmployeeTask


class WorkspaceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CompanyView(WorkspaceModel):
    id: UUID
    name: str
    is_demo: bool


class Viewer(WorkspaceModel):
    user_id: UUID
    employee_id: UUID | None
    display_name: str
    role: Literal["manager", "employee"]
    job_title: str


class ActiveDemoRun(WorkspaceModel):
    id: UUID
    mode: str
    clock_at: datetime
    actor_name: str | None
    actor_session_id: UUID | None = None
    row_version: int
    clock_version: int


class WorkspaceBootstrap(WorkspaceModel):
    company: CompanyView
    viewer: Viewer
    demo_run: ActiveDemoRun | None
    capabilities: list[str]


class WorkspacePreferences(WorkspaceModel):
    row_version: int = 0
    sidebar_collapsed: bool = False
    graph_breathing: bool = True
    reduce_motion: bool = False
    desktop_shortcut_enabled: bool = False
    shortcut: str = "Control+Space"


class PreferencesUpdate(WorkspaceModel):
    expected_row_version: int = Field(ge=0)
    sidebar_collapsed: bool
    graph_breathing: bool
    reduce_motion: bool
    desktop_shortcut_enabled: bool
    shortcut: str = Field(min_length=1, max_length=80)


class Project(WorkspaceModel):
    id: UUID
    title: str
    goal_label: str = ""
    status: str
    deadline: datetime | None
    updated_at: datetime
    task_count: int
    completed_task_count: int
    plan_id: UUID | None
    accepted_at: datetime | None = None
    accepted_by: str | None = None
    description: str = ""

    @field_validator("goal_label", mode="before")
    @classmethod
    def legacy_goal_label(cls, value: object) -> object:
        # The additive column is nullable for projects created before ALTO.
        # Keep the desktop's string response contract without changing stored rows.
        return "" if value is None else value


class ActionItem(WorkspaceModel):
    id: UUID
    title: str
    kind: str
    status: str
    target_path: str
    detail: str = ""


class HomeData(WorkspaceModel):
    recent_projects: list[Project]
    completed_projects: list[Project]
    actions: list[ActionItem]
    tasks: list[EmployeeTask]


class GraphNode(WorkspaceModel):
    id: UUID
    task_key: str
    title: str
    team: str
    owner_name: str | None
    owner_employee_id: UUID | None
    status: str
    start_at: datetime | None
    finish_at: datetime | None
    reviewer_name: str | None
    summary: str
    is_mine: bool
    can_work: bool
    row_version: int


class GraphEdge(WorkspaceModel):
    id: UUID
    from_: UUID = Field(alias="from")
    to: UUID
    kind: Literal["dependency", "handoff", "review", "acceptance"]
    label: str


class RuleResult(WorkspaceModel):
    id: str
    rule_id: str
    title: str
    status: str
    description: str
    category_key: Literal[
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
    category_title: str
    category_keys: list[
        Literal[
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
    ]
    category_titles: list[str]
    encoding_version: str
    formula: str | None
    source_label: str | None
    source_version: str | None
    candidate_values: dict[str, Any] | None
    technical_expression_available: bool = False


class RuleTechnicalDetail(WorkspaceModel):
    rule_id: str
    technical_expression: str | None
    encoding_version: str


class VerificationSummary(WorkspaceModel):
    proposal_id: UUID
    author_kind: str
    product_status: str
    native_status: str
    z3_version: str
    compiler_version: str
    verifier_version: str
    duration_ms: int = Field(ge=0)
    required_rule_count: int = Field(ge=0)
    covered_rule_count: int = Field(ge=0)
    unverified_rule_count: int = Field(ge=0)
    candidate_digest: str
    snapshot_digest: str
    digests_match: bool
    independent_validation_passed: bool
    validator_version: str | None
    approval_status: str


class CandidateCheckVersion(WorkspaceModel):
    proposal_id: UUID
    version: int
    author_kind: str
    product_status: str
    independent_validation_passed: bool
    candidate_digest: str
    created_at: datetime


class ProjectGraphData(WorkspaceModel):
    project: Project
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    rules: list[RuleResult]
    plan_id: UUID | None
    can_approve: bool
    check_status: str
    approval_disabled_reason: str | None
    timezone: str
    candidate_history: list[CandidateCheckVersion] = Field(default_factory=list)
    selected_proposal_id: UUID | None = None
    is_candidate_preview: bool = False
    verification_summary: VerificationSummary | None = None


class CalendarItem(WorkspaceModel):
    id: str
    title: str
    start_at: datetime
    end_at: datetime
    kind: Literal["meeting", "busy", "work", "deadline", "protected"]
    source: str
    status: str
    task_id: UUID | None
    project_id: UUID | None
    description: str
    owner_name: str | None


class CalendarSource(WorkspaceModel):
    name: str
    status: str


class CalendarData(WorkspaceModel):
    items: list[CalendarItem]
    timezone: str
    sources: list[CalendarSource]


class OnboardingRequest(WorkspaceModel):
    display_name: str = Field(min_length=1, max_length=120)
    requested_role: Literal["manager", "employee"]

    @field_validator("display_name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("display name must not be blank")
        return value.strip()


class CreateRun(WorkspaceModel):
    mode: Literal["live", "authored_replay", "authored_d0_check"] = "authored_replay"
    parent_run_id: UUID | None = None


class SelectActor(WorkspaceModel):
    employee_id: UUID


class DemoQuickstartRequest(WorkspaceModel):
    preferred_actor_key: str | None = Field(
        default=None, min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_-]{0,63}$"
    )


class DemoQuickstartResponse(WorkspaceModel):
    run_id: UUID
    actor_session_id: UUID
    actor_key: str
    provider_status: Literal["configured"] = "configured"


class AdvanceClock(WorkspaceModel):
    expected_clock_version: int = Field(gt=0)
    clock_at: datetime

    @field_validator("clock_at")
    @classmethod
    def offset_required(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("scenario clock must include an offset")
        return value


class VersionCommand(WorkspaceModel):
    expected_row_version: int = Field(ge=0)


class DraftUpdate(VersionCommand):
    text: str = Field(max_length=12000)


class PreferenceUpdate(VersionCommand):
    text: str = Field(min_length=1, max_length=1000)


class PreferenceDecision(VersionCommand):
    manager_id: UUID | None = None


class AssistantContext(WorkspaceModel):
    kind: Literal["global", "project", "task", "person"]
    id: UUID | None = None
    label: str | None = Field(default=None, max_length=160)
    proposal_id: UUID | None = None

    @model_validator(mode="after")
    def exact_proposal_requires_project(self) -> AssistantContext:
        if self.proposal_id is not None and self.kind != "project":
            raise ValueError("an exact proposal can only bind a project conversation")
        return self


class CreateThread(WorkspaceModel):
    context: AssistantContext


class AssistantTurn(CreateThread):
    content: str = Field(min_length=1, max_length=8000)


class AssistantActionDecision(WorkspaceModel):
    decision: Literal["confirm", "dismiss"]
    expected_version: int = Field(gt=0)


class CancelThread(WorkspaceModel):
    expected_status: Literal["queued", "running"]


class VoiceRequest(WorkspaceModel):
    file_id: UUID
    thread_id: UUID


class FinalizeUpload(WorkspaceModel):
    size_bytes: int = Field(gt=0, le=26_214_400)


class FeedbackRequest(WorkspaceModel):
    text: str = Field(min_length=1, max_length=10000)
    task_id: UUID | None = None
    suggest_preference: bool = False


class NewPreference(WorkspaceModel):
    text: str = Field(min_length=1, max_length=1000)


class GateApproval(VersionCommand):
    required_submission_id: UUID | None = None
    required_submission_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class ProfileSkills(VersionCommand):
    skills: list[str] = Field(max_length=20)

    @field_validator("skills")
    @classmethod
    def valid_labels(cls, values: list[str]) -> list[str]:
        result = [value.strip() for value in values]
        if any(
            not 1 <= len(value) <= 120 or any(ord(char) < 32 for char in value) for value in result
        ):
            raise ValueError("skill labels must be nonempty plain text up to 120 characters")
        if len({value.casefold() for value in result}) != len(result):
            raise ValueError("skill labels must be distinct")
        return result
