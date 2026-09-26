from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

ApprovalDomain = Literal["planning", "disclosure"]
RequirementKind = Literal[
    "plan_commit",
    "deadline_change",
    "cross_team_displacement",
    "employee_brief_disclosure",
]
AuthorityKind = Literal["company_manager", "team_manager", "company_admin"]


@dataclass(frozen=True, slots=True)
class ApprovalRisk:
    deadline_changed: bool = False
    employee_brief_present: bool = False
    affected_team_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class RequirementBlueprint:
    domain: ApprovalDomain
    kind: RequirementKind
    authority: AuthorityKind
    team_id: UUID | None
    reason: str


def derive_requirements(risk: ApprovalRisk) -> tuple[RequirementBlueprint, ...]:
    """Return the minimum explicit authorities; AI output never grants authority."""

    requirements = [
        RequirementBlueprint(
            domain="planning",
            kind="plan_commit",
            authority="company_manager",
            team_id=None,
            reason="Approve the exact independently validated plan proposal.",
        )
    ]
    if risk.deadline_changed:
        requirements.append(
            RequirementBlueprint(
                domain="planning",
                kind="deadline_change",
                authority="company_manager",
                team_id=None,
                reason="Confirm movement of an agreed deadline.",
            )
        )
    for team_id in sorted(set(risk.affected_team_ids), key=str):
        requirements.append(
            RequirementBlueprint(
                domain="planning",
                kind="cross_team_displacement",
                authority="team_manager",
                team_id=team_id,
                reason="Authorize displacement of work owned by the affected team.",
            )
        )
    if risk.employee_brief_present:
        requirements.append(
            RequirementBlueprint(
                domain="disclosure",
                kind="employee_brief_disclosure",
                authority="company_manager",
                team_id=None,
                reason="Approve the separately hashed employee-facing brief and audience.",
            )
        )
    return tuple(requirements)
