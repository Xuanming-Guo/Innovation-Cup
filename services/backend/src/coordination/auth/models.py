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


@dataclass(frozen=True, slots=True)
class CompanyContext:
    actor: AuthenticatedUser
    company_id: UUID
    membership_id: UUID
    administrative_role: AdministrativeRole
    employee_id: UUID | None
