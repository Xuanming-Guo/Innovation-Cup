from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from uuid import UUID

import psycopg


DEMO_COMPANY_ID = UUID("11111111-1111-4111-8111-111111111111")
MANAGER_MEMBERSHIP_ID = UUID("11111111-0000-4111-8111-111111111101")
EMPLOYEE_MEMBERSHIP_ID = UUID("11111111-0000-4111-8111-111111111102")
MANAGER_EMPLOYEE_ID = UUID("11111111-0000-4111-8111-111111111201")
EMPLOYEE_EMPLOYEE_ID = UUID("11111111-0000-4111-8111-111111111202")
DEMO_TEAM_ID = UUID("11111111-0000-4111-8111-111111111301")


def required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def assert_safe_environment() -> None:
    environment = os.environ.get("COORDINATION_ENVIRONMENT", "development").lower()
    if environment not in {"development", "local", "demo", "test"}:
        raise SystemExit("demo tenant operations refuse this environment")


def seed(connection: psycopg.Connection[tuple[object, ...]]) -> None:
    manager_user_id = UUID(required_environment("DEMO_MANAGER_USER_ID"))
    employee_user_id = UUID(required_environment("DEMO_EMPLOYEE_USER_ID"))
    with connection.transaction():
        company = connection.execute(
            "select is_demo from app.companies where id = %s for update",
            (DEMO_COMPANY_ID,),
        ).fetchone()
        if company is None or company[0] is not True:
            raise SystemExit("the fixed demo company is missing or not marked as demo")

        connection.execute(
            """
            insert into app.user_profiles (user_id, display_name, ui_locale)
            values (%s, 'Morgan Manager', 'en-GB'), (%s, 'Elliot Employee', 'en-GB')
            on conflict (user_id) do update
            set display_name = excluded.display_name, ui_locale = excluded.ui_locale
            """,
            (manager_user_id, employee_user_id),
        )
        connection.execute(
            """
            insert into app.company_memberships (
              id, company_id, user_id, membership_status, administrative_role, joined_at
            ) values
              (%s, %s, %s, 'active', 'company_admin', clock_timestamp()),
              (%s, %s, %s, 'active', 'member', clock_timestamp())
            on conflict (company_id, user_id) do update
            set membership_status = 'active',
                administrative_role = excluded.administrative_role,
                joined_at = coalesce(app.company_memberships.joined_at, excluded.joined_at),
                suspended_at = null
            """,
            (
                MANAGER_MEMBERSHIP_ID,
                DEMO_COMPANY_ID,
                manager_user_id,
                EMPLOYEE_MEMBERSHIP_ID,
                DEMO_COMPANY_ID,
                employee_user_id,
            ),
        )
        connection.execute(
            """
            insert into app.employee_profiles (id, company_id, membership_id, timezone)
            values (%s, %s, %s, 'Europe/London'), (%s, %s, %s, 'Europe/London')
            on conflict (company_id, membership_id) do update
            set status = 'active', timezone = excluded.timezone
            """,
            (
                MANAGER_EMPLOYEE_ID,
                DEMO_COMPANY_ID,
                MANAGER_MEMBERSHIP_ID,
                EMPLOYEE_EMPLOYEE_ID,
                DEMO_COMPANY_ID,
                EMPLOYEE_MEMBERSHIP_ID,
            ),
        )
        connection.execute(
            """
            insert into app.teams (id, company_id, name, description)
            values (%s, %s, 'Product Operations', 'Synthetic Innovation Cup demo team')
            on conflict (company_id, id) do update
            set name = excluded.name, description = excluded.description, status = 'active'
            """,
            (DEMO_TEAM_ID, DEMO_COMPANY_ID),
        )
        connection.execute(
            """
            insert into app.team_memberships (
              company_id, team_id, employee_id, team_role, assignment_eligible
            ) values
              (%s, %s, %s, 'manager', true),
              (%s, %s, %s, 'contributor', true)
            on conflict (company_id, team_id, employee_id) where valid_to is null do update
            set team_role = excluded.team_role, assignment_eligible = excluded.assignment_eligible
            """,
            (
                DEMO_COMPANY_ID,
                DEMO_TEAM_ID,
                MANAGER_EMPLOYEE_ID,
                DEMO_COMPANY_ID,
                DEMO_TEAM_ID,
                EMPLOYEE_EMPLOYEE_ID,
            ),
        )


def reset(connection: psycopg.Connection[tuple[object, ...]], confirmation: str) -> None:
    expected = f"RESET {DEMO_COMPANY_ID}"
    if confirmation != expected:
        raise SystemExit(f"reset requires --confirm \"{expected}\"")
    with connection.transaction():
        connection.execute("select app_private.reset_demo_company(%s)", (DEMO_COMPANY_ID,))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed or reset the synthetic demo tenant")
    parser.add_argument("action", choices=("seed", "reset"))
    parser.add_argument("--confirm", default="")
    args = parser.parse_args(argv)

    assert_safe_environment()
    dsn = required_environment("SUPABASE_DB_URL")
    with psycopg.connect(dsn) as connection:
        if args.action == "seed":
            seed(connection)
        else:
            reset(connection, args.confirm)
    print(f"demo tenant {args.action} completed for {DEMO_COMPANY_ID}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
