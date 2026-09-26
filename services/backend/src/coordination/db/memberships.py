from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, cast
from uuid import UUID

import psycopg

from coordination.auth.models import AdministrativeRole
from coordination.db.session import company_transaction


@dataclass(frozen=True, slots=True)
class ActiveMembership:
    membership_id: UUID
    company_id: UUID
    user_id: UUID
    administrative_role: AdministrativeRole
    employee_id: UUID | None


class MembershipResolver(Protocol):
    def resolve_active(self, *, user_id: UUID, company_id: UUID) -> ActiveMembership | None: ...


class MembershipStoreUnavailableError(RuntimeError):
    """Raised when current membership cannot be checked safely."""


class PostgresMembershipResolver:
    """Resolve membership inside a transaction-local tenant and actor context."""

    def __init__(self, dsn: str, *, connect_timeout_seconds: int = 5) -> None:
        self._dsn = dsn
        self._connect_timeout_seconds = connect_timeout_seconds

    def resolve_active(self, *, user_id: UUID, company_id: UUID) -> ActiveMembership | None:
        try:
            with company_transaction(
                self._dsn,
                role="coordination_api",
                actor_id=user_id,
                company_id=company_id,
                purpose="membership:resolve",
                connect_timeout_seconds=self._connect_timeout_seconds,
            ) as connection:
                row = connection.execute(
                    """
                        select
                            membership.id as membership_id,
                            membership.company_id,
                            membership.user_id,
                            membership.administrative_role,
                            employee.id as employee_id
                        from app.company_memberships as membership
                        left join app.employee_profiles as employee
                          on employee.company_id = membership.company_id
                         and employee.membership_id = membership.id
                         and employee.status = 'active'
                        where membership.company_id = %s
                          and membership.user_id = %s
                          and membership.membership_status = 'active'
                        """,
                    (company_id, user_id),
                ).fetchone()
        except psycopg.Error as error:
            raise MembershipStoreUnavailableError("membership store is unavailable") from error

        if row is None:
            return None
        return ActiveMembership(
            membership_id=cast(UUID, row["membership_id"]),
            company_id=cast(UUID, row["company_id"]),
            user_id=cast(UUID, row["user_id"]),
            administrative_role=cast(AdministrativeRole, row["administrative_role"]),
            employee_id=cast(UUID | None, row["employee_id"]),
        )
