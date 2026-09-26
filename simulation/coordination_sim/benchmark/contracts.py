"""Finite, versioned benchmark facts and observable evidence, not product APIs."""
from __future__ import annotations

from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field, model_validator
from ..contracts import Contract, Identifier

Nonnegative = Annotated[int, Field(strict=True, ge=0)]
Positive = Annotated[int, Field(strict=True, gt=0)]
Provider = Literal["teams", "calendar", "planner", "sharepoint", "github"]
Classification = Literal["FEASIBLE", "INFEASIBLE_WITHIN_SCOPE", "INSUFFICIENT_SCOPE", "INVALID_INPUT", "UNKNOWN"]


class Span(Contract):
    start: Nonnegative
    end: Positive

    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("nonpositive slot span")
        return self


class Company(Contract):
    company_id: Identifier
    name: str = "SoraWorks Japan (synthetic)"
    business: str = "B2B enterprise software and implementation services"
    locale: str = "ja-JP / en"
    timezone: str = "Asia/Tokyo"
    anchor: AwareDatetime
    horizon_slots: Positive = 416
    slot_minutes: Literal[15] = 15
    policy_version: str = "company-policy-1"
    holiday_calendar: str = "fixture-week-no-holidays-1"
    optional_agent_enabled: Literal[False] = False

    @model_validator(mode="after")
    def timezone_valid(self):
        ZoneInfo(self.timezone)
        return self


class Team(Contract):
    team_id: Identifier
    company_id: Identifier
    name: str
    function: str
    manager_id: Identifier


class Familiarity(Contract):
    project_id: str
    maturity: Literal["exposure", "submission", "accepted"]
    source_ref: str
    version: str = "1"


class Employee(Contract):
    employee_id: Identifier
    company_id: Identifier
    name: str
    team_ids: tuple[str, ...]
    manager_id: str
    timezone: str = "Asia/Tokyo"
    locale: str = "ja-JP"
    confirmed_skills: tuple[str, ...]
    declared_skills: tuple[str, ...] = ()
    qualifications: tuple[str, ...] = ()
    working: tuple[Span, ...]
    daily_budget_slots: Positive = 28
    weekly_budget_slots: Positive = 140
    availability: Literal["known", "unknown"] = "known"
    familiarity: tuple[Familiarity, ...] = ()
    source_ref: str
    profile_version: str = "1"
    skill_version: str = "1"
    capacity_version: str = "1"
    estimate_version: str = "class-prior-1"
    correction_state: Literal["none", "disputed", "superseded"] = "none"
    resource_kind: Literal["human"] = "human"


class Actor(Contract):
    actor_id: str
    company_id: str
    role: str
    scope_refs: tuple[str, ...]
    permitted_actions: tuple[str, ...]
    policy_version: str = "responses-1"


class Project(Contract):
    project_id: str
    company_id: str
    team_id: str
    manager_id: str
    title: str
    purpose: str
    classification: Literal["team", "customer-confidential", "restricted", "internal"]
    requested_deadline_slot: Positive
    agreed_deadline_slot: Positive
    source_ref: str


class Source(Contract):
    source_id: str
    company_id: str
    provider: Provider
    connection_id: str
    external_id: str
    version: str
    retrieved_at: AwareDatetime
    expires_at: AwareDatetime
    classification: str
    owner_id: str
    authoritative_for: tuple[str, ...]
    fields: dict[str, str | int | bool | None]
    excerpt: str
    freshness: Literal["current", "stale", "unavailable"] = "current"
    revoked: bool = False
    origin: Literal["imported", "exported"] = "imported"
    internal_block_ref: str | None = None
    mode: Literal["simulated"] = "simulated"


class Grant(Contract):
    grant_id: str
    company_id: str
    principal_id: str
    connection_id: str
    resource_id: str
    actions: tuple[Literal["read", "write", "review", "share"], ...]
    expires_at: AwareDatetime
    revoked: bool = False
    authority_ref: str


class Brief(Contract):
    brief_id: str
    company_id: str
    version: str = "1"
    text: str
    audience: tuple[str, ...]
    approved_by: str
    source_ref: str
    revoked: bool = False


class Dependency(Contract):
    predecessor: str
    lag_slots: Nonnegative = 0
    acceptance_required: bool = False


class Task(Contract):
    task_id: str
    company_id: str
    project_id: str
    team_id: str
    title: str
    purpose: str
    deliverable: str
    acceptance_criteria: tuple[str, ...]
    task_class: str
    lifecycle: Literal["assigned", "in_progress", "ready", "accepted", "cancelled"] = "assigned"
    effort_slots: Nonnegative
    estimate_version: str = "class-prior-1"
    uncertainty: str = "synthetic fixed duration; not a calibrated forecast"
    window: Span
    requested_deadline_slot: Positive
    agreed_deadline_slot: Positive
    priority: Annotated[int, Field(strict=True, ge=0, le=3)] = 2
    priority_source: str
    required_skills: tuple[str, ...]
    preferred_skills: tuple[str, ...] = ()
    qualifications: tuple[str, ...] = ()
    eligible_owners: tuple[str, ...]
    required_sources: tuple[str, ...]
    dependencies: tuple[Dependency, ...] = ()
    reviewer_id: str | None = None
    review_task_id: str | None = None
    separation_of_duties: bool = False
    self_certifiable: bool = True
    min_segment_slots: Positive = 1
    max_segments: Positive = 1
    timing: Literal["active", "fixed", "passive"] = "active"
    passive_slots: Nonnegative = 0
    protected: bool = False
    movable: bool = True
    allow_owner_change: bool = True
    movement_authority: str
    required_approver: str | None = None
    brief_id: str
    source_ref: str

    @model_validator(mode="after")
    def semantics(self):
        if self.timing != "passive" and self.effort_slots == 0:
            raise ValueError("active effort must be positive")
        if self.timing == "passive" and (self.effort_slots != 0 or self.passive_slots == 0):
            raise ValueError("passive work uses elapsed time, not active capacity")
        if not self.eligible_owners or not self.acceptance_criteria:
            raise ValueError("explicit ownership and acceptance required")
        return self


class Segment(Contract):
    block_id: str
    company_id: str
    task_id: str
    employee_id: str
    span: Span


class Reservation(Contract):
    reservation_id: str
    company_id: str
    employee_id: str
    span: Span
    opaque: bool = True
    movable: Literal[False] = False
    source_ref: str
    internal_block_ref: str | None = None


class Snapshot(Contract):
    schema_version: Literal["benchmark-2"] = "benchmark-2"
    specification_version: Literal["0.5.0"] = "0.5.0"
    generator_version: str = "company-2"
    preset: Literal["tiny", "medium", "demo"]
    seed: Nonnegative
    revision: Nonnegative = 0
    company: Company
    teams: tuple[Team, ...]
    employees: tuple[Employee, ...]
    actors: tuple[Actor, ...]
    projects: tuple[Project, ...]
    tasks: tuple[Task, ...]
    schedule: tuple[Segment, ...]
    reservations: tuple[Reservation, ...]
    sources: tuple[Source, ...]
    grants: tuple[Grant, ...]
    briefs: tuple[Brief, ...]
    reporting_edges: tuple[tuple[str, str], ...]

    @model_validator(mode="after")
    def integrity(self):
        cid = self.company.company_id
        collections = ((self.teams, "team_id"), (self.employees, "employee_id"),
                       (self.actors, "actor_id"), (self.projects, "project_id"),
                       (self.tasks, "task_id"), (self.schedule, "block_id"),
                       (self.reservations, "reservation_id"), (self.sources, "source_id"),
                       (self.grants, "grant_id"), (self.briefs, "brief_id"))
        for rows, key in collections:
            ids = [getattr(x, key) for x in rows]
            if len(ids) != len(set(ids)) or any(x.company_id != cid for x in rows):
                raise ValueError("duplicate or cross-tenant reference")
        teams = {x.team_id for x in self.teams}
        people = {x.employee_id for x in self.employees}
        actors = {x.actor_id for x in self.actors}
        projects = {x.project_id for x in self.projects}
        tasks = {x.task_id for x in self.tasks}
        sources = {x.source_id for x in self.sources}
        briefs = {x.brief_id for x in self.briefs}
        for e in self.employees:
            if not set(e.team_ids) <= teams or e.manager_id not in people or e.source_ref not in sources:
                raise ValueError("invalid employee membership/lineage")
        for t in self.teams:
            if t.manager_id not in people:
                raise ValueError("unknown manager")
        for p in self.projects:
            if p.team_id not in teams or p.manager_id not in people or p.source_ref not in sources:
                raise ValueError("invalid project")
        for t in self.tasks:
            if (t.project_id not in projects or t.team_id not in teams or
                not set(t.eligible_owners) <= people or not set(t.required_sources) <= sources or
                {t.source_ref, t.priority_source, t.movement_authority} - sources or t.brief_id not in briefs or
                (t.reviewer_id and t.reviewer_id not in people) or
                (t.review_task_id and t.review_task_id not in tasks) or
                (t.required_approver and t.required_approver not in actors)):
                raise ValueError("invalid task reference/lineage")
        pending = {t.task_id: {d.predecessor for d in t.dependencies} for t in self.tasks}
        if any(not v <= tasks for v in pending.values()):
            raise ValueError("unknown dependency")
        while pending:
            ready = {k for k, v in pending.items() if not v}
            if not ready:
                raise ValueError("dependency cycle")
            pending = {k: v - ready for k, v in pending.items() if k not in ready}
        for b in self.schedule:
            if b.task_id not in tasks or b.employee_id not in people:
                raise ValueError("unknown schedule reference")
        for r in self.reservations:
            if r.employee_id not in people or r.source_ref not in sources:
                raise ValueError("unknown capacity reference")
        for g in self.grants:
            if g.principal_id not in people | actors or g.resource_id not in sources:
                raise ValueError("unknown grant reference")
        for b in self.briefs:
            if not set(b.audience) <= people | actors or b.source_ref not in sources:
                raise ValueError("unknown brief reference")
        return self


class Change(Contract):
    schema_version: Literal["benchmark-2"] = "benchmark-2"
    scenario_id: str
    version: str = "1"
    kind: Literal["deadline", "incident", "portfolio", "no_impact", "hr", "revocation", "unavailable", "concurrent"]
    at_slot: Nonnegative
    actor_id: str
    project_id: str
    source_refs: tuple[str, ...]
    summary: str
    task_ids: tuple[str, ...]
    requested_deadline_slot: Positive | None = None
    response_policy: str = "responses-1"


class Approval(Contract):
    actor_id: str
    task_ids: tuple[str, ...]
    proposal_digest: str
    base_revision: Nonnegative
    decision: Literal["approved", "rejected"]
    source_ref: str


class Acceptance(Contract):
    task_id: str
    reviewer_id: str
    submission_version: str
    accepted_slot: Nonnegative
    evidence_ref: str


class Disclosure(Contract):
    viewer_id: str
    source_refs: tuple[str, ...] = ()
    brief_ids: tuple[str, ...] = ()


class StageStates(Contract):
    interpretation: str = "NOT_AVAILABLE"
    solver: str = "NOT_AVAILABLE"
    product_validation: str = "NOT_AVAILABLE"
    approval: str = "NOT_AVAILABLE"
    commitment: str = "NOT_AVAILABLE"
    synchronisation: str = "NOT_AVAILABLE"
    notification_refetch: str = "NOT_AVAILABLE"
    acknowledgement: str = "NOT_AVAILABLE"
    work_acceptance: str = "NOT_AVAILABLE"


class Outcome(Contract):
    schema_version: Literal["benchmark-2"] = "benchmark-2"
    method: Literal["naive", "product_replay", "coordination_engine_product"]
    classification: Classification
    terminal: Literal["COMPLETED", "REFUSED", "UNKNOWN", "TIMED_OUT", "CANCELLED", "FAILED", "INVALID", "PARTIAL"]
    schedule: tuple[Segment, ...]
    considered_task_ids: tuple[str, ...]
    iterations: Nonnegative
    plan_versions: Nonnegative
    reason: str | None = None
    agreed_deadlines: dict[str, int] = Field(default_factory=dict)
    forecast_deadlines: dict[str, int] = Field(default_factory=dict)
    priorities: dict[str, int] = Field(default_factory=dict)
    protected_values: dict[str, bool] = Field(default_factory=dict)
    cancelled_task_ids: tuple[str, ...] = ()
    approvals: tuple[Approval, ...] = ()
    acceptances: tuple[Acceptance, ...] = ()
    actual_starts: dict[str, int] = Field(default_factory=dict)
    disclosures: tuple[Disclosure, ...] = ()
    read_source_ids: tuple[str, ...] = ()
    states: StageStates = StageStates()
    product_metadata: dict[str, str | int | None] = Field(default_factory=dict)


class GroundTruth(Contract):
    schema_version: Literal["benchmark-2"] = "benchmark-2"
    scenario_id: str
    input_digest: str
    expected_classification: Classification
    material_source_refs: tuple[str, ...]
    protected_task_ids: tuple[str, ...]
    allowed_scope: tuple[str, ...]
    review_note_ref: str


class Violation(Contract):
    category: Literal["tenant", "eligibility", "effort", "capacity", "dependency", "deadline", "protection", "authority", "disclosure"]
    code: str
    task_ids: tuple[str, ...]
    entity_refs: tuple[str, ...] = ()
    amount: int = 1


class Validation(Contract):
    schema_version: Literal["benchmark-2"] = "benchmark-2"
    validator_version: Literal["neutral-2"] = "neutral-2"
    violations: tuple[Violation, ...]
    checked_task_count: int
    requested_lateness_slots: dict[str, int]
    agreed_lateness_slots: dict[str, int]
    overloaded_slots: int
    overlap_pairs: int
    maximum_daily_load_ratio: float
    maximum_weekly_load_ratio: float
    coverage: tuple[str, ...]
    limitations: tuple[str, ...] = ("Synthetic input truth is not independent external evidence.",)
