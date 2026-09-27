from __future__ import annotations

from dataclasses import replace
from uuid import UUID

import psycopg

from coordination.auth.models import CompanyContext
from coordination.db.session import company_transaction


class DemoSelectionUnavailableError(LookupError):
    """The selected run/session is absent, expired or outside the actor's scope."""


class DemoStoreUnavailableError(RuntimeError):
    """The run authority store cannot currently be checked."""


def resolve_demo_context(
    dsn: str,
    *,
    context: CompanyContext,
    run_id: UUID,
    actor_session_id: UUID | None,
    connect_timeout_seconds: int = 5,
) -> CompanyContext:
    """Resolve selectors against current DB authority; never replace the JWT subject."""
    try:
        with company_transaction(
            dsn,
            role="coordination_api",
            actor_id=context.actor.user_id,
            company_id=context.company_id,
            purpose="demo:resolve-context",
            demo_run_id=run_id,
            demo_actor_session_id=actor_session_id,
            connect_timeout_seconds=connect_timeout_seconds,
        ) as connection:
            row = connection.execute(
                "select app.resolve_demo_context(%s, %s, %s) as value, "
                "app.can_manage_planning(%s,%s) as planning_authority",
                (
                    context.company_id,
                    run_id,
                    actor_session_id,
                    context.company_id,
                    context.actor.user_id,
                ),
            ).fetchone()
    except (psycopg.errors.InsufficientPrivilege, psycopg.errors.NoDataFound) as error:
        raise DemoSelectionUnavailableError("demo context not found") from error
    except psycopg.Error as error:
        raise DemoStoreUnavailableError("demo context unavailable") from error
    if not row or not isinstance(row["value"], dict):
        raise DemoSelectionUnavailableError("demo context not found")
    value = row["value"]
    employee_id = value.get("simulated_employee_id") or value.get("employee_id")
    return replace(
        context,
        demo_run_id=run_id,
        demo_actor_session_id=actor_session_id,
        simulated_employee_id=UUID(str(employee_id)) if employee_id else None,
        demo_planning_authority=bool(row["planning_authority"]),
    )
