"""Provision the versioned synthetic ALTO directory/template; never reset a database.

Run only with operator/migration credentials after applying the ALTO migrations.
No Auth users, credentials, completed work, accepted submissions or AI output are seeded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
OPERATOR_ENV_FILE = REPOSITORY_ROOT / "supabase" / ".env"
LINKED_POOLER_FILE = REPOSITORY_ROOT / "supabase" / ".temp" / "pooler-url"

COMPANY = UUID("11111111-1111-4111-8111-111111111111")
SCENARIO = "northstar-launch"
VERSION = 1
ZONE = "America/Los_Angeles"


class OperatorConfigurationError(ValueError):
    """An actionable configuration message containing no credential values."""


class OperatorSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SUPABASE_",
        env_file_encoding="utf-8-sig",
        extra="ignore",
        hide_input_in_errors=True,
    )

    db_url: SecretStr | None = None
    db_password: SecretStr | None = None

    def __init__(self, env_file: Path) -> None:
        super().__init__(_env_file=env_file)


def operator_connection_string(
    *, env_file: Path = OPERATOR_ENV_FILE, pooler_file: Path = LINKED_POOLER_FILE
) -> str:
    """Load private operator settings without prompting or changing process environment."""
    try:
        settings = OperatorSettings(env_file)
    except (OSError, ValueError):
        raise OperatorConfigurationError(
            "Cannot load operator settings from supabase/.env; check its format and permissions."
        ) from None
    dsn = settings.db_url.get_secret_value().strip() if settings.db_url else ""
    password = settings.db_password.get_secret_value() if settings.db_password else ""
    if not dsn:
        if not password:
            raise OperatorConfigurationError(
                "Set SUPABASE_DB_PASSWORD in ignored supabase/.env for the linked project, "
                "or set an explicit operator SUPABASE_DB_URL. Never use a runtime login."
            )
        try:
            dsn = pooler_file.read_text(encoding="utf-8-sig").strip()
        except (OSError, UnicodeError):
            raise OperatorConfigurationError(
                "Cannot read linked project metadata; run supabase link for the intended "
                "project or set an explicit operator SUPABASE_DB_URL."
            ) from None
        overrides = {"password": password}
    else:
        overrides = {}
    try:
        values = {
            key: str(value)
            for key, value in conninfo_to_dict(dsn, **overrides).items()
            if value is not None
        }
    except (psycopg.Error, ValueError):
        raise OperatorConfigurationError(
            "Invalid PostgreSQL connection string. Use the linked-project password option "
            "or a complete operator URI, not an HTTPS API URL or a password alone."
        ) from None
    if any(not values.get(key, "").strip() for key in ("host", "dbname", "user")):
        raise OperatorConfigurationError(
            "The operator connection must explicitly specify host, dbname and user."
        )
    if values.get("sslmode") not in {"verify-ca", "verify-full"}:
        values["sslmode"] = "require"
    try:
        timeout = int(values.get("connect_timeout", "10"))
    except ValueError:
        timeout = 0
    if not 1 <= timeout <= 30:
        raise OperatorConfigurationError(
            "Operator connect_timeout must be between 1 and 30 seconds."
        )
    values["connect_timeout"] = str(timeout)
    return make_conninfo(**values)


def check_connection(dsn: str) -> None:
    """Read the synthetic-company guard without provisioning or taking a row lock."""
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.read_only = True
        connection.execute("set local statement_timeout = '10s'")
        company = connection.execute(
            "select is_demo from app.companies where id=%s", (COMPANY,)
        ).fetchone()
        if company is None or not company["is_demo"]:
            raise OperatorConfigurationError(
                "Connected, but the fixed Northstar company is missing or not marked as a demo."
            )
    print("Connection OK. Northstar is marked as a synthetic demo. No data changed.")


def safe_database_error(error: psycopg.Error) -> str:
    """Report stable diagnostics, never server messages, row details or connection strings."""
    details = [type(error).__name__]
    if error.sqlstate and re.fullmatch(r"[A-Z0-9]{5}", error.sqlstate):
        details.append("SQLSTATE " + error.sqlstate)
    constraint = error.diag.constraint_name
    if constraint and re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", constraint):
        details.append("constraint " + constraint)
    return (
        "Database operation failed ("
        + "; ".join(details)
        + "). No credentials or row values printed."
    )


# Each tuple is an explicitly synthetic directory record, not a real employee.
PRODUCT = (
    ("jordan", "Jordan", "Product Strategy Director", "leadership"),
    ("iris", "Iris", "Product Designer", "design"),
    ("nora", "Nora", "Product Marketing Lead", "marketing"),
    ("aiko", "Aiko", "Interaction Designer", "design"),
    ("ben", "Ben", "Content Designer", "design"),
    ("celia", "Celia", "Visual Designer", "design"),
    ("dev", "Dev", "Design Systems Specialist", "design"),
    ("elena", "Elena", "Product Designer", "design"),
    ("farah", "Farah", "Customer Education Writer", "support"),
    ("gabe", "Gabe", "Product Marketing Specialist", "marketing"),
    ("hana", "Hana", "Release Communications Writer", "marketing"),
    ("inez", "Inez", "Content Strategist", "marketing"),
    ("jules", "Jules", "Customer Education Specialist", "support"),
    ("kai", "Kai", "Product Research Coordinator", "design"),
    ("leah", "Leah", "Visual Designer", "design"),
    ("mina", "Mina", "Customer Guide Writer", "support"),
    ("noel", "Noel", "Product Marketing Specialist", "marketing"),
    ("omar", "Omar", "Design Systems Specialist", "design"),
    ("paula", "Paula", "Product Coordinator", "design"),
    ("quinn", "Quinn", "Content Designer", "design"),
    ("ren", "Ren", "Marketing Coordinator", "marketing"),
    ("sara", "Sara", "Product Coordinator", "design"),
    ("talia", "Talia", "Customer Education Writer", "support"),
    ("uma", "Uma", "Marketing Coordinator", "marketing"),
    ("vera", "Vera", "Visual Designer", "design"),
)
SOFTWARE = (
    ("maya", "Maya", "Delivery Director", "leadership"),
    ("alex", "Alex", "Software Engineer", "engineering"),
    ("priya", "Priya", "QA Engineer", "qa"),
    ("sam", "Sam", "Customer Support Specialist", "support"),
    ("amir", "Amir", "Backend Engineer", "engineering"),
    ("bea", "Bea", "Frontend Engineer", "engineering"),
    ("chen", "Chen", "Platform Engineer", "engineering"),
    ("dana", "Dana", "QA Engineer", "qa"),
    ("ellis", "Ellis", "Release Engineer", "engineering"),
    ("finn", "Finn", "Support Engineer", "support"),
    ("gia", "Gia", "QA Engineer", "qa"),
    ("haru", "Haru", "Backend Engineer", "engineering"),
    ("imani", "Imani", "Frontend Engineer", "engineering"),
    ("jo", "Jo", "Support Engineer", "support"),
    ("kiran", "Kiran", "Platform Engineer", "engineering"),
    ("lucas", "Lucas", "QA Engineer", "qa"),
    ("mei", "Mei", "Software Engineer", "engineering"),
    ("nico", "Nico", "Customer Support Specialist", "support"),
    ("oliver", "Oliver", "Software Engineer", "engineering"),
    ("paz", "Paz", "QA Engineer", "qa"),
    ("ravi", "Ravi", "Support Engineer", "support"),
    ("suki", "Suki", "Software Engineer", "engineering"),
    ("theo", "Theo", "Platform Engineer", "engineering"),
    ("val", "Val", "QA Engineer", "qa"),
    ("wren", "Wren", "Customer Support Specialist", "support"),
)


def record_id(key: str) -> UUID:
    return uuid5(COMPANY, key)


def instant(day: int, hour: int, minute: int = 0) -> str:
    return (
        datetime(2026, 9, 28, hour, minute, tzinfo=ZoneInfo(ZONE)) + timedelta(days=day)
    ).isoformat()


def manifest() -> dict[str, Any]:
    from coordination.planning.northstar import GATES, TASKS
    from coordination.planning.northstar_authority import canonical_authority_manifest

    planning_authority = canonical_authority_manifest().model_dump(mode="json")

    sources = [
        (
            "LAUNCH-01",
            "Directors' launch handoff",
            "Synthetic directors' call, 25 September 2026: Jordan (Product) requests the "
            "analytics product launch on Friday 2 October at 10:00 America/Los_Angeles. Maya "
            "(Software), Delivery Director with cross-group delivery authority, confirms the "
            "scope: coordinate Engineering, Design, QA, Marketing and Customer Support; propose "
            "remaining work, owners, reviews and handoffs; respect working hours and existing "
            "commitments. Maya must approve the exact plan and its disclosure separately. A "
            "call summary is not execution approval.",
        ),
        (
            "LAUNCH-02",
            "Approved product and release brief",
            "Core analytics is already implemented. Remaining work is the interface package, "
            "integration connector, tested workflow, launch visuals and messaging, customer "
            "guide, staging deployment and rollback rehearsal, readiness, release, support and "
            "post-release acceptance. The approved interface must match product behavior. "
            "Integration must pass the approved checklist. Customer claims, screenshots and "
            "instructions must match the accepted build. Deployment requires a tested rollback "
            "and exact approved artifacts. Release begins Friday 2 October at 10:00; milestone "
            "acceptance is Friday 11:15, not the release time. Each work owner submits a "
            "versioned deliverable and the appointed reviewer accepts that exact version; never "
            "infer acceptance from elapsed time.",
        ),
        (
            "LAUNCH-03",
            "Five-function Teams Posts excerpts",
            "Alex / Engineering: Core analytics is already implemented. The remaining connector "
            "work needs the accepted interface and the approved integration checklist.\nIris / "
            "Design: Once the interface is accepted, I can prepare launch visuals from the "
            "tested build. My approved profile includes product-storytelling work.\nNora / "
            "Marketing: We can draft messaging from the approved scope now. Final visuals and "
            "product claims must match the accepted build.\nSam / Customer Support: I can "
            "outline the guide now. Final steps and screenshots need the validated "
            "workflow.\nPriya / QA: Use my current availability and the approved review "
            "checklist. The reserved Tuesday hour remains protected.\nThese synthetic posts "
            "provide context, not qualification or approval authority.",
        ),
        (
            "LAUNCH-04",
            "Working hours and protected capacity",
            "All scenario scheduling uses America/Los_Angeles, 28 September-2 October 2026. "
            "Working windows are Monday-Friday 09:00-12:00 and 13:00-17:00, no overtime. Every "
            "active participant consumes their full own interval; L1 reserves both Alex and "
            "Nora. Priya's Tuesday 29 September 11:00-12:00 commitment is protected and "
            "private; only the busy interval is disclosed. Review time is real capacity and is "
            "counted once, as the review task. Schedules must not split or move protected "
            "commitments.",
        ),
        (
            "LAUNCH-05",
            "Synthetic skills and permitted launch inputs",
            "Operator-authored eligibility: Iris owns design and launch visuals; Alex owns "
            "connector, deployment and release; Priya owns QA and appointed technical reviews; "
            "Nora owns messaging and publication; Sam owns customer guide and support; Maya "
            "owns delivery approvals and appointed acceptance. Jordan defines scope with Maya, "
            "not replacement reviewers. Skill declarations are not verified qualifications. No "
            "accepted-contribution history is pre-populated: it is recorded only after actual "
            "accepted scenario work. All seven actors may read the company-readable launch "
            "evidence; private feedback is excluded.",
        ),
        (
            "LAUNCH-06",
            "Employee-confirmed pre-planning preferences",
            "Synthetic, employee-confirmed on25September2026, shareable to the launch directors "
            "and correctable: Iris would like more product-storytelling assignments. Sam would "
            "like more customer-education work with protected writing time. These are soft "
            "preferences, never hard qualifications or performance scores. New Friday feedback "
            "cannot change historical planning evidence.",
        ),
        (
            "LAUNCH-07",
            "Exact-version review and launch authority",
            "Maya approves the exact checked plan, separately approves employee brief "
            "audiences, and commits atomically. D1 is reviewed by D2(Maya); E1 by Q1(Priya); M2 "
            "and M1 final package by M3(Nora); S2 by S3(Priya); E2 by Q2(Priya); L1 by "
            "Q3(Priya); S4 by R2(Maya). M1 and S1 alone are explicitly self-certifiable "
            "internal drafts, not public release. D2 acceptance unlocks E1; Q1 acceptance "
            "unlocks M2,S2,E2. M1 self-certification and M2 submission precede M3. S1 "
            "self-certification precedes S2. R1(Maya) requires D2,Q1,M3,S3,Q2 accepted; R1 "
            "readiness approval unlocks L1 and S4. L1 has Alex as owner and Nora as active "
            "publisher. Q3 requires the exact L1 submission. R2 requires Q3 accepted and S4 "
            "submitted; Maya accepts S4's exact evidence and milestone. Only R2 acceptance "
            "marks the project completed. A clock advance never completes work or grants "
            "approval.",
        ),
    ]
    task_details = []
    for key, _day, start, end, owner, title, deliverable in TASKS:
        start_hour, start_minute = map(int, start.split(":"))
        end_hour, end_minute = map(int, end.split(":"))
        task_details.append(
            {
                "task_key": key,
                "title": title,
                "owner": owner,
                "deliverable": deliverable,
                "active_minutes": 60 * (end_hour - start_hour) + end_minute - start_minute,
            }
        )
    sources = [
        (
            key,
            title,
            text
            + (
                "\nAuthoritative task definitions: " + json.dumps(task_details)
                if key == "LAUNCH-02"
                else "\nExact execution gates: "
                + json.dumps(GATES)
                + "\nTyped finite planning authority: "
                + json.dumps(planning_authority, sort_keys=True, separators=(",", ":"))
                if key == "LAUNCH-07"
                else ""
            ),
        )
        for key, title, text in sources
    ]
    result: dict[str, Any] = {
        "project": {
            "title": "Northstar Analytics Launch",
            "purpose": "Coordinate the remaining launch work across five functions.",
            "goal_label": "Launch analytics · Friday 10:00",
            "owning_team_id": str(record_id("team:software")),
            "manager_employee_id": str(record_id("person:maya")),
            "requested_deadline": instant(4, 11, 15),
        },
        "sources": [
            {
                "key": key,
                "title": title,
                "text": text,
                "classification": "internal",
                **({"planning_authority": planning_authority} if key == "LAUNCH-07" else {}),
            }
            for key, title, text in sources
        ],
        "connections": [
            {"provider": provider, "timezone": ZONE}
            for provider in ("teams", "outlook", "sharepoint")
        ],
        "calendar": [
            {
                "employee_id": str(record_id("person:priya")),
                "provider": "outlook",
                "key": "priya-protected-tuesday",
                "start_at": instant(1, 11),
                "end_at": instant(1, 12),
                "timezone": ZONE,
                "visibility": "busy_only",
                "status": "busy",
            }
        ],
        "resource_profiles": [],
        "groups": [],
        "skills": [],
        "working_rules": [],
    }
    for source in result["sources"]:
        if source["key"] == "LAUNCH-06":
            source["audience_employee_ids"] = [
                str(record_id("person:maya")),
                str(record_id("person:jordan")),
            ]
    for group, people in (("product", PRODUCT), ("software", SOFTWARE)):
        for index, (key, _name, _title, function) in enumerate(people):
            employee = str(record_id("person:" + key))
            result["groups"].append(
                {
                    "employee_id": employee,
                    "group_id": str(record_id("group:" + group)),
                    "valid_from": instant(-7, 0),
                }
            )
            windows = [
                {"start_at": instant(day, start), "end_at": instant(day, end)}
                for day in range(5)
                for start, end in ((9, 12), (13, 17))
            ]
            if index < 18:
                result["skills"].append(
                    {"employee_id": employee, "skill_id": str(record_id("skill:" + function))}
                )
                result["working_rules"].append(
                    {
                        "employee_id": employee,
                        "timezone": ZONE,
                        "weekly_windows": windows,
                        "capacity_limits": {"daily_active_minutes": 420},
                        "valid_from": instant(-7, 0),
                    }
                )
                result["resource_profiles"].append(
                    {
                        "resource_id": employee,
                        "timezone": ZONE,
                        "availability_windows": windows,
                        "capability_keys": ["northstar." + key],
                        "permission_keys": ["northstar.launch"],
                        "daily_active_minutes": 420,
                    }
                )
            if key not in {"maya", "jordan", "alex", "iris", "priya", "nora", "sam"}:
                result["calendar"].append(
                    {
                        "employee_id": employee,
                        "provider": "outlook",
                        "key": key + "-background",
                        "start_at": instant(index % 5, 15),
                        "end_at": instant(index % 5, 16),
                        "timezone": ZONE,
                        "visibility": "busy_only",
                        "status": "busy",
                    }
                )
    return result


def provision(dsn: str) -> None:
    payload = manifest()
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).digest()
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        company = connection.execute(
            "select is_demo from app.companies where id=%s for update", (COMPANY,)
        ).fetchone()
        if company is None or not company["is_demo"]:
            raise ValueError(
                "The fixed Northstar demo company must already exist and be explicitly synthetic"
            )
        existing = connection.execute(
            "select manifest_digest from app.demo_scenario_manifests where company_id=%s and "
            "scenario_key=%s and version=%s",
            (COMPANY, SCENARIO, VERSION),
        ).fetchone()
        if existing and bytes(existing["manifest_digest"]) != digest:
            raise ValueError(
                "Immutable scenario version differs; create a new reviewed version instead of "
                "overwriting"
            )
        connection.execute(
            "update app.companies set name='Northstar "
            "Labs',default_timezone=%s,default_locale='en-US' where id=%s",
            (ZONE, COMPANY),
        )
        for group, people in (("product", PRODUCT), ("software", SOFTWARE)):
            connection.execute(
                "insert into app.operating_groups(id,company_id,key,label) values(%s,%s,%s,%s) "
                "on conflict(company_id,key) do nothing",
                (record_id("group:" + group), COMPANY, group, group.title()),
            )
            connection.execute(
                "insert into app.teams(id,company_id,name,description) values(%s,%s,%s,'ALTO "
                "synthetic operating group') on conflict(company_id,id) do nothing",
                (record_id("team:" + group), COMPANY, group.title()),
            )
            for index, (key, name, title, function) in enumerate(people):
                employee = record_id("person:" + key)
                connection.execute(
                    """insert into app.employee_profiles(
                  id,company_id,membership_id,timezone,preferred_locale,
                  profile_kind,synthetic_key,display_name,title,function_key,scenario_detail)
                  values(%s,%s,null,%s,'en-US','synthetic',%s,%s,%s,%s,%s)
                  on conflict(id) do nothing""",
                    (
                        employee,
                        COMPANY,
                        ZONE,
                        key,
                        name,
                        title,
                        function,
                        "rich" if index < 18 else "background",
                    ),
                )
                connection.execute(
                    """insert into app.team_memberships(
                  company_id,team_id,employee_id,team_role,assignment_eligible,valid_from)
                  values(%s,%s,%s,%s,true,%s) on conflict(company_id,team_id,employee_id)
                  where valid_to is null do nothing""",
                    (
                        COMPANY,
                        record_id("team:" + group),
                        employee,
                        "manager"
                        if function == "leadership"
                        else "reviewer"
                        if function == "qa"
                        else "contributor",
                        instant(-7, 0),
                    ),
                )
                connection.execute(
                    "insert into app.skills(id,company_id,key,label) values(%s,%s,%s,%s) on "
                    "conflict(company_id,key) do nothing",
                    (record_id("skill:" + function), COMPANY, function, function.title()),
                )
        connection.execute(
            """insert into app.demo_scenario_manifests(company_id,scenario_key,version,
            manifest_digest,fixture_schema_version,manifest_payload)
            values(%s,%s,%s,%s,'alto-scenario.v1',%s)
            on conflict(company_id,scenario_key,version) do nothing""",
            (COMPANY, SCENARIO, VERSION, digest, Jsonb(payload)),
        )
        connection.execute(
            """insert into app.demo_workspace_policies(
            company_id,enabled,scenario_key,scenario_version)
            values(%s,true,%s,%s) on conflict(company_id) do update set enabled=true,
            scenario_key=excluded.scenario_key,scenario_version=excluded.scenario_version""",
            (COMPANY, SCENARIO, VERSION),
        )


def configure_hackathon_demo(dsn: str, provider_version: UUID | None) -> None:
    """Enable or disable the shared default without ever reading its Vault secret."""
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        company = connection.execute(
            "select is_demo from app.companies where id=%s for update", (COMPANY,)
        ).fetchone()
        if company is None or not company["is_demo"]:
            raise OperatorConfigurationError(
                "The fixed Northstar company is missing or is not marked as a demo."
            )
        if provider_version is None:
            updated = connection.execute(
                """update app.demo_operator_provider_defaults
                set enabled=false,disabled_at=clock_timestamp()
                where company_id=%s and enabled returning company_id""",
                (COMPANY,),
            ).fetchone()
            if updated is None:
                raise OperatorConfigurationError("Hackathon demo is not currently enabled.")
            return
        version = connection.execute(
            """select v.id,p.owner_membership_id from app.demo_provider_profile_versions v
            join app.demo_provider_profiles p
              on p.company_id=v.company_id and p.id=v.profile_id
            where v.company_id=%s and v.id=%s and v.provider='vertex_ai'
              and v.credential_kind='vertex_service_account'
              and v.validation_status='validated' and v.revoked_at is null
              and p.status='active'""",
            (COMPANY, provider_version),
        ).fetchone()
        if version is None:
            raise OperatorConfigurationError(
                "Provider version must be an active validated Northstar Vertex service account."
            )
        connection.execute(
            """insert into app.demo_operator_provider_defaults(
              company_id,profile_version_id,credential_owner_membership_id,enabled,configured_at,disabled_at)
            values(%s,%s,%s,true,clock_timestamp(),null)
            on conflict(company_id) do update set
              profile_version_id=excluded.profile_version_id,
              credential_owner_membership_id=excluded.credential_owner_membership_id,
              enabled=true,configured_at=clock_timestamp(),disabled_at=null""",
            (COMPANY, provider_version, version["owner_membership_id"]),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-synthetic-company", choices=[str(COMPANY)])
    parser.add_argument(
        "--check-connection", action="store_true", help="Check access read-only; do not provision"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--enable-hackathon-demo",
        action="store_true",
        help="Use a validated Vault-backed Vertex version for new judge workspaces",
    )
    mode.add_argument(
        "--disable-hackathon-demo",
        action="store_true",
        help="Immediately disable shared-provider resolution for judge workspaces",
    )
    parser.add_argument("--provider-version", type=UUID)
    args = parser.parse_args()
    if args.enable_hackathon_demo != (args.provider_version is not None):
        parser.error("--enable-hackathon-demo requires exactly one --provider-version")
    if not args.check_connection and args.confirm_synthetic_company != str(COMPANY):
        parser.error("--confirm-synthetic-company is required when provisioning")
    try:
        dsn = operator_connection_string()
        if args.check_connection:
            check_connection(dsn)
            return
        if args.enable_hackathon_demo:
            configure_hackathon_demo(dsn, args.provider_version)
            print("Enabled the Northstar hackathon demo with an immutable Vault-backed default.")
            return
        if args.disable_hackathon_demo:
            configure_hackathon_demo(dsn, None)
            print("Disabled the Northstar hackathon demo shared-provider default.")
            return
        provision(dsn)
    except OperatorConfigurationError as error:
        raise SystemExit(str(error)) from None
    except psycopg.Error as error:
        raise SystemExit(safe_database_error(error)) from None
    except ValueError:
        raise SystemExit(
            "Provisioning failed validation. Check the synthetic-company policy and immutable "
            "scenario version; no credentials are printed."
        ) from None
    print(
        "Provisioned Northstar: 50 synthetic profiles, 36 rich, 14 background; versioned "
        "template only. No Auth accounts or completed work created."
    )


if __name__ == "__main__":
    sys.path.insert(0, str(REPOSITORY_ROOT / "services" / "backend" / "src"))
    main()
