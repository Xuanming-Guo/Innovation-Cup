"""Small versioned benchmark contracts, not product API or workflow contracts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from . import SCHEMA_VERSION, SPEC_VERSION

Identifier = Annotated[str, Field(min_length=1)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class Window(Contract):
    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode="after")
    def ordered(self) -> Window:
        if self.end <= self.start:
            raise ValueError("window must have positive duration")
        return self


class Team(Contract):
    team_id: Identifier
    company_id: Identifier
    display_name: Identifier


class Employee(Contract):
    employee_id: Identifier
    company_id: Identifier
    team_id: Identifier
    display_name: Identifier
    timezone: Literal["Asia/Tokyo"] = "Asia/Tokyo"
    confirmed_skills: tuple[Identifier, ...]
    working_windows: tuple[Window, ...]
    source_version_ref: Identifier


class Task(Contract):
    task_id: Identifier
    company_id: Identifier
    project_id: Identifier
    team_id: Identifier
    title: Identifier
    effort_minutes: Annotated[int, Field(strict=True, gt=0)]
    required_skill: Identifier
    window: Window
    requested_deadline: AwareDatetime
    agreed_deadline: AwareDatetime
    predecessors: tuple[Identifier, ...] = ()
    protected: bool = False
    source_version_ref: Identifier


class Block(Contract):
    block_id: Identifier
    company_id: Identifier
    task_id: Identifier
    employee_id: Identifier
    interval: Window


class SourceVersion(Contract):
    source_version_id: Identifier
    company_id: Identifier
    mode: Literal["synthetic"] = "synthetic"
    authority: Literal["fixture-author"] = "fixture-author"
    content: Identifier


class Fixture(Contract):
    schema_version: Literal["bootstrap-1"] = SCHEMA_VERSION
    specification_version: Literal["0.5.0"] = SPEC_VERSION
    generator_version: Literal["tiny-bootstrap-1"] = "tiny-bootstrap-1"
    preset: Literal["tiny"] = "tiny"
    seed: Annotated[int, Field(strict=True, ge=0)]
    company_id: Literal["soraworks-synthetic"] = "soraworks-synthetic"
    company_name: Literal["SoraWorks Japan (synthetic)"] = "SoraWorks Japan (synthetic)"
    horizon: Window
    teams: tuple[Team, ...]
    employees: tuple[Employee, ...]
    tasks: tuple[Task, ...]
    initial_schedule: tuple[Block, ...]
    sources: tuple[SourceVersion, ...]

    @model_validator(mode="after")
    def integrity(self) -> Fixture:
        def unique(rows: tuple, field: str) -> set[str]:
            ids = [getattr(row, field) for row in rows]
            if len(ids) != len(set(ids)):
                raise ValueError(f"duplicate {field}")
            if any(row.company_id != self.company_id for row in rows):
                raise ValueError("cross-tenant fixture reference")
            return set(ids)

        teams = unique(self.teams, "team_id")
        employees = unique(self.employees, "employee_id")
        tasks = unique(self.tasks, "task_id")
        sources = unique(self.sources, "source_version_id")
        unique(self.initial_schedule, "block_id")
        for row in (*self.employees, *self.tasks):
            if row.team_id not in teams or row.source_version_ref not in sources:
                raise ValueError("unknown team or source version")
        for block in self.initial_schedule:
            if block.task_id not in tasks or block.employee_id not in employees:
                raise ValueError("unknown initial schedule reference")
        pending = {task.task_id: set(task.predecessors) for task in self.tasks}
        if any(not predecessors <= tasks for predecessors in pending.values()):
            raise ValueError("unknown dependency")
        while pending:
            ready = {key for key, predecessors in pending.items() if not predecessors}
            if not ready:
                raise ValueError("dependency cycle")
            pending = {key: value - ready for key, value in pending.items() if key not in ready}
        return self


class Scenario(Contract):
    schema_version: Literal["bootstrap-1"] = SCHEMA_VERSION
    specification_version: Literal["0.5.0"] = SPEC_VERSION
    scenario_id: Literal["tiny-no-impact-smoke"] = "tiny-no-impact-smoke"
    scenario_version: Literal["1"] = "1"
    simulated_at: AwareDatetime
    event_type: Literal["unrelated_note_corrected"] = "unrelated_note_corrected"
    summary: str = "Synthetic unrelated note corrected; scheduling facts are unchanged."


class GroundTruth(Contract):
    schema_version: Literal["bootstrap-1"] = SCHEMA_VERSION
    expected_class: Literal["FEASIBLE"] = "FEASIBLE"
    expected_task_ids: tuple[str, ...]
    protected_task_ids: tuple[str, ...]
    acceptance_checks: tuple[str, ...]


class ReplayExample(Contract):
    schema_version: Literal["bootstrap-1"] = SCHEMA_VERSION
    replay_version: Literal["authored-no-impact-1"] = "authored-no-impact-1"
    provenance: Literal["authored_synthetic_example_not_product_capture"]
    label: Literal["REPLAY — NOT A PRODUCT RESULT"]
    input_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    schedule: tuple[Block, ...]


class Violation(Contract):
    code: str
    entity_refs: tuple[str, ...]


class ValidationReport(Contract):
    schema_version: Literal["bootstrap-1"] = SCHEMA_VERSION
    validator_version: Literal["neutral-bootstrap-1"] = "neutral-bootstrap-1"
    coverage: tuple[str, ...]
    unchecked: tuple[str, ...]
    violations: tuple[Violation, ...]


class MetricObservation(Contract):
    metric_schema_version: Literal["1"] = "1"
    metric_definition_version: Literal["1"] = "1"
    metric_id: Literal["bootstrap_schedule_violation_count"] = "bootstrap_schedule_violation_count"
    run_id: str
    scenario_id: str
    approach_or_condition: Literal["product_replay"] = "product_replay"
    evidence_class: Literal["recorded_replay"] = "recorded_replay"
    unit: Literal["violations"] = "violations"
    direction_if_any: Literal["lower"] = "lower"
    eligibility_rule: str = "Available terminal replay output under bootstrap-1, including invalid schedules"
    numerator_and_denominator_refs: tuple[str, ...] = (
        "validation.json#/violations", "fixture.json#/tasks",
    )
    source_event_or_artifact_refs: tuple[str, ...] = (
        "trace.jsonl#event-003", "validation.json", "outcome.json", "ground_truth.json",
    )
    value: Annotated[int, Field(strict=True, ge=0)] | None
    status: Literal["MEASURED", "NOT_MEASURED", "INVALID"]
    missing_or_invalid_reason: str | None

    @model_validator(mode="after")
    def honest_missing(self) -> MetricObservation:
        if self.status == "MEASURED":
            if self.value is None or self.missing_or_invalid_reason is not None:
                raise ValueError("measured observation needs a value and no missing reason")
        elif self.value is not None or not self.missing_or_invalid_reason:
            raise ValueError("unmeasured observation needs null and a reason")
        return self
