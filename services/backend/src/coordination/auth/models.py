from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

AdministrativeRole = Literal["member", "manager", "company_admin"]


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    user_id: UUID
    role: Literal["authenticated"]
    session_id: UUID
    assurance_level: Literal["aal1", "aal2"]
    is_anonymous: bool = False


@dataclass(frozen=True, slots=True)
class CompanyContext:
    actor: AuthenticatedUser
    company_id: UUID
    membership_id: UUID
    administrative_role: AdministrativeRole
    employee_id: UUID | None
    demo_run_id: UUID | None = None
    demo_actor_session_id: UUID | None = None
    simulated_employee_id: UUID | None = None
    demo_planning_authority: bool = False

    @property
    def effective_employee_id(self) -> UUID | None:
        return self.simulated_employee_id or self.employee_id

    @property
    def can_manage_planning(self) -> bool:
        # This demo flag is resolved from Postgres, never from headers or a role
        # claim. It changes no real membership; commands still recheck DB authority.
        if self.demo_run_id is not None:
            return self.demo_planning_authority
        return self.administrative_role in {"manager", "company_admin"}
