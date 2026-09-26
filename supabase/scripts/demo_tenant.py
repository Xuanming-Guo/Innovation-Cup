from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Sequence
from datetime import UTC, datetime, time, timedelta
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb


DEMO_COMPANY_ID = UUID("11111111-1111-4111-8111-111111111111")
MANAGER_MEMBERSHIP_ID = UUID("11111111-0000-4111-8111-111111111101")
EMPLOYEE_MEMBERSHIP_ID = UUID("11111111-0000-4111-8111-111111111102")
MANAGER_EMPLOYEE_ID = UUID("11111111-0000-4111-8111-111111111201")
EMPLOYEE_EMPLOYEE_ID = UUID("11111111-0000-4111-8111-111111111202")
SOFTWARE_TEAM_ID = UUID("11111111-0000-4111-8111-111111111301")
HR_TEAM_ID = UUID("11111111-0000-4111-8111-111111111302")
SOFTWARE_PROJECT_ID = UUID("11111111-0000-4111-8111-111111111401")
HR_PROJECT_ID = UUID("11111111-0000-4111-8111-111111111402")
SOFTWARE_SOURCE_ID = UUID("11111111-0000-4111-8111-111111111501")
HR_SOURCE_ID = UUID("11111111-0000-4111-8111-111111111502")
CAPACITY_SOURCE_ID = UUID("11111111-0000-4111-8111-111111111503")
SOFTWARE_VERSION_ID = UUID("11111111-0000-4111-8111-111111111601")
HR_VERSION_ID = UUID("11111111-0000-4111-8111-111111111602")
CAPACITY_VERSION_ID = UUID("11111111-0000-4111-8111-111111111603")
SOURCE_GRANT_IDS = (
    UUID("11111111-0000-4111-8111-111111111701"),
    UUID("11111111-0000-4111-8111-111111111702"),
    UUID("11111111-0000-4111-8111-111111111703"),
)

SOURCE_PACK = (
    (
        SOFTWARE_SOURCE_ID,
        SOFTWARE_VERSION_ID,
        SOFTWARE_TEAM_ID,
        "Software release commitments",
        "software-release",
        "Release readiness needs a checked dependency list, rollback owner and an approved "
        "technical handoff before the requested deadline.",
        "confidential",
    ),
    (
        HR_SOURCE_ID,
        HR_VERSION_ID,
        HR_TEAM_ID,
        "Internal onboarding operations",
        "hr-onboarding",
        "Internal onboarding needs an access brief and orientation handoff. Candidate ranking, "
        "hiring recommendations and payroll are outside this work.",
        "restricted",
    ),
    (
        CAPACITY_SOURCE_ID,
        CAPACITY_VERSION_ID,
        None,
        "Approved shared-specialist capacity",
        "shared-specialist",
        "The shared technical specialist may support both teams within the recorded capacity "
        "windows. Cross-team source details remain private.",
        "internal",
    ),
)


def required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def assert_safe_environment() -> None:
    environment = os.environ.get("COORDINATION_ENVIRONMENT", "development").lower()
    if environment not in {"development", "local", "demo", "test"}:
        raise SystemExit("demo tenant operations refuse this environment")


def next_business_day_start(now: datetime) -> datetime:
    candidate = (now + timedelta(days=1)).date()
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return datetime.combine(candidate, time(hour=9), tzinfo=UTC)


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
            values (%s, 'Maya Chen', 'en-GB'), (%s, 'Alex Rivera', 'en-GB')
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
            values
              (%s, %s, 'Software Delivery', 'Synthetic software delivery team'),
              (%s, %s, 'HR Operations', 'Synthetic internal onboarding operations team')
            on conflict (company_id, id) do update
            set name = excluded.name, description = excluded.description, status = 'active'
            """,
            (SOFTWARE_TEAM_ID, DEMO_COMPANY_ID, HR_TEAM_ID, DEMO_COMPANY_ID),
        )
        connection.execute(
            """
            insert into app.team_memberships (
              company_id, team_id, employee_id, team_role, assignment_eligible
            ) values
              (%s, %s, %s, 'manager', true),
              (%s, %s, %s, 'contributor', true),
              (%s, %s, %s, 'manager', true),
              (%s, %s, %s, 'contributor', true)
            on conflict (company_id, team_id, employee_id) where valid_to is null do update
            set team_role = excluded.team_role, assignment_eligible = excluded.assignment_eligible
            """,
            (
                DEMO_COMPANY_ID,
                SOFTWARE_TEAM_ID,
                MANAGER_EMPLOYEE_ID,
                DEMO_COMPANY_ID,
                SOFTWARE_TEAM_ID,
                EMPLOYEE_EMPLOYEE_ID,
                DEMO_COMPANY_ID,
                HR_TEAM_ID,
                MANAGER_EMPLOYEE_ID,
                DEMO_COMPANY_ID,
                HR_TEAM_ID,
                EMPLOYEE_EMPLOYEE_ID,
            ),
        )
        connection.execute(
            """
            update app.execution_resources
            set display_label = case id
              when %s then 'Maya Chen - coordination manager'
              when %s then 'Alex Rivera - shared technical specialist'
              else display_label end
            where company_id = %s and id in (%s, %s)
            """,
            (
                MANAGER_EMPLOYEE_ID,
                EMPLOYEE_EMPLOYEE_ID,
                DEMO_COMPANY_ID,
                MANAGER_EMPLOYEE_ID,
                EMPLOYEE_EMPLOYEE_ID,
            ),
        )
        connection.execute(
            """
            insert into app.projects (
              id, company_id, owning_team_id, manager_employee_id, title, purpose,
              default_priority_key, visibility_classification
            ) values
              (%s, %s, %s, %s, 'Release readiness',
               'Coordinate the synthetic software release readiness change.',
               'high', 'confidential'),
              (%s, %s, %s, %s, 'Internal onboarding',
               'Coordinate internal onboarding access and orientation only.',
               'high', 'restricted')
            on conflict (company_id, id) do update
            set title = excluded.title, purpose = excluded.purpose, status = 'active',
                default_priority_key = excluded.default_priority_key,
                visibility_classification = excluded.visibility_classification
            """,
            (
                SOFTWARE_PROJECT_ID,
                DEMO_COMPANY_ID,
                SOFTWARE_TEAM_ID,
                MANAGER_EMPLOYEE_ID,
                HR_PROJECT_ID,
                DEMO_COMPANY_ID,
                HR_TEAM_ID,
                MANAGER_EMPLOYEE_ID,
            ),
        )

        retrieved_at = datetime.now(UTC).replace(microsecond=0)
        expires_at = retrieved_at + timedelta(days=30)
        for source_id, version_id, team_id, title, locator, content, classification in SOURCE_PACK:
            connection.execute(
                """
                insert into app.source_records (
                  id, company_id, owning_team_id, uploaded_by_employee_id, source_kind,
                  title, classification, authority_status, access_policy, status
                ) values (%s, %s, %s, %s, 'fixture', %s, %s, 'authoritative', %s, 'active')
                on conflict (company_id, id) do update
                set owning_team_id = excluded.owning_team_id, title = excluded.title,
                    classification = excluded.classification,
                    authority_status = 'authoritative', status = 'active'
                """,
                (
                    source_id,
                    DEMO_COMPANY_ID,
                    team_id,
                    MANAGER_EMPLOYEE_ID,
                    title,
                    classification,
                    Jsonb({"fixture": "northstar-connected-v1"}),
                ),
            )
            digest = hashlib.sha256(content.encode("utf-8")).digest()
            connection.execute(
                """
                insert into app.source_versions (
                  id, company_id, source_id, provider_version, content_sha256,
                  retrieved_at, extraction_version, access_snapshot, expires_at
                ) values (%s, %s, %s, 'northstar-connected-v1', %s, %s,
                          'fixture-extract-v1', %s, %s)
                on conflict (company_id, id) do update
                set content_sha256 = excluded.content_sha256,
                    retrieved_at = excluded.retrieved_at,
                    access_snapshot = excluded.access_snapshot,
                    expires_at = excluded.expires_at
                """,
                (
                    version_id,
                    DEMO_COMPANY_ID,
                    source_id,
                    digest,
                    retrieved_at,
                    Jsonb({"manager_only": True, "synthetic": True}),
                    expires_at,
                ),
            )
            connection.execute(
                """
                update app.source_records set current_version_id = %s
                where company_id = %s and id = %s
                """,
                (version_id, DEMO_COMPANY_ID, source_id),
            )
            connection.execute(
                """
                insert into app.source_excerpts (
                  company_id, source_id, source_version_id, locator, permitted_text,
                  text_sha256, extraction_version
                ) values (%s, %s, %s, %s, %s, %s, 'fixture-extract-v1')
                on conflict (company_id, source_version_id, locator) do update
                set permitted_text = excluded.permitted_text,
                    text_sha256 = excluded.text_sha256,
                    extraction_version = excluded.extraction_version
                """,
                (DEMO_COMPANY_ID, source_id, version_id, locator, content, digest),
            )

        for grant_id, source in zip(SOURCE_GRANT_IDS, SOURCE_PACK, strict=True):
            connection.execute(
                """
                insert into app.source_access_grants (
                  id, company_id, source_id, principal_kind, employee_id, access_type,
                  authority_reference
                ) values (%s, %s, %s, 'employee', %s, 'manage',
                          'northstar-demo-manager-authority-v1')
                on conflict (id) do update
                set revoked_at = null, expires_at = null,
                    authority_reference = excluded.authority_reference
                """,
                (grant_id, DEMO_COMPANY_ID, source[0], MANAGER_EMPLOYEE_ID),
            )

        horizon_start = next_business_day_start(retrieved_at)
        windows = [
            {
                "start_at": (horizon_start + timedelta(days=offset)).isoformat(),
                "end_at": (horizon_start + timedelta(days=offset, hours=8)).isoformat(),
            }
            for offset in range(4)
            if (horizon_start + timedelta(days=offset)).weekday() < 5
        ]
        connection.execute(
            """
            insert into app.planning_resource_profiles (
              company_id, resource_id, timezone, availability_windows,
              capability_keys, permission_keys, daily_active_minutes,
              profile_revision, estimate_revision, active
            ) values
              (%s, %s, 'Europe/London', %s, %s, %s, 360, 1, 1, true),
              (%s, %s, 'Europe/London', %s, %s, %s, 360, 1, 1, true)
            on conflict (company_id, resource_id) do update
            set timezone = excluded.timezone,
                availability_windows = excluded.availability_windows,
                capability_keys = excluded.capability_keys,
                permission_keys = excluded.permission_keys,
                daily_active_minutes = excluded.daily_active_minutes,
                profile_revision = excluded.profile_revision,
                estimate_revision = excluded.estimate_revision,
                active = true
            """,
            (
                DEMO_COMPANY_ID,
                MANAGER_EMPLOYEE_ID,
                Jsonb(windows),
                Jsonb(["manager_review"]),
                Jsonb(["approve_plan", "review_work"]),
                DEMO_COMPANY_ID,
                EMPLOYEE_EMPLOYEE_ID,
                Jsonb(windows),
                Jsonb(["technical_coordination"]),
                Jsonb(["internal_delivery"]),
            ),
        )

        connection.execute(
            """
            update app.companies
            set name = 'Northstar Software & People Operations',
                default_timezone = 'Europe/London', default_locale = 'en-GB',
                status = 'active', is_demo = true
            where id = %s
            """,
            (DEMO_COMPANY_ID,),
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
    print(
        json.dumps(
            {
                "action": args.action,
                "company_id": str(DEMO_COMPANY_ID),
                "fixture": "northstar-connected-v1",
                "status": "completed",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
