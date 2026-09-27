from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from coordination.auth.models import CompanyContext
from coordination.db.session import company_transaction
from coordination.employee.contracts import EmployeeTask
from coordination.employee.persistence import PostgresEmployeeStore
from coordination.workspace.contracts import (
    CalendarData,
    DemoQuickstartResponse,
    HomeData,
    PreferencesUpdate,
    Project,
    ProjectGraphData,
    RuleTechnicalDetail,
    WorkspaceBootstrap,
    WorkspacePreferences,
)


class WorkspaceUnavailableError(RuntimeError):
    """The workspace schema/service cannot currently fulfil the operation."""


class WorkspaceNotFoundError(LookupError):
    """The requested record is absent from the current authorised projection."""


class WorkspaceConflictError(ValueError):
    """An expected version or idempotency binding is stale."""


class WorkspaceInputError(ValueError):
    """The command violates a domain invariant."""


class DemoAiUnavailableError(RuntimeError):
    """The locked demo has no usable operator-managed Vertex version."""


class PostgresWorkspaceStore:
    def __init__(
        self, dsn: str, *, connect_timeout_seconds: int = 5, voice_enabled: bool = False,
        gemini_model: str = "gemini-3.8-flash",
    ) -> None:
        self.dsn = dsn
        self.timeout = connect_timeout_seconds
        self.voice_enabled = voice_enabled
        self.gemini_model = gemini_model

    @contextmanager
    def transaction(self, context: CompanyContext, purpose: str) -> Iterator[Any]:
        try:
            with company_transaction(
                self.dsn,
                role="coordination_api",
                actor_id=context.actor.user_id,
                company_id=context.company_id,
                purpose=purpose,
                connect_timeout_seconds=self.timeout,
                demo_run_id=context.demo_run_id,
                demo_actor_session_id=context.demo_actor_session_id,
            ) as connection:
                yield connection
        except (psycopg.errors.InsufficientPrivilege, psycopg.errors.NoDataFound) as error:
            raise WorkspaceNotFoundError("record was not found") from error
        except (
            psycopg.errors.SerializationFailure,
            psycopg.errors.UniqueViolation,
            psycopg.errors.ExclusionViolation,
        ) as error:
            raise WorkspaceConflictError("the record changed; refresh and review again") from error
        except (psycopg.errors.CheckViolation, psycopg.errors.InvalidParameterValue) as error:
            raise WorkspaceInputError("command is not valid in the current state") from error
        except psycopg.errors.RaiseException as error:
            if error.diag.message_primary == "hackathon_demo_ai_unavailable":
                raise DemoAiUnavailableError("Demo AI is temporarily unavailable") from error
            raise WorkspaceUnavailableError("workspace service is unavailable") from error
        except psycopg.Error as error:
            raise WorkspaceUnavailableError("workspace service is unavailable") from error

    def command(
        self,
        context: CompanyContext,
        *,
        name: str,
        key: str,
        body: dict[str, Any],
        operation: Callable[[Any], dict[str, Any]],
    ) -> dict[str, Any]:
        """Serialize retries and store only non-content-bearing command receipts."""
        digest = hashlib.sha256(
            json.dumps(
                {"body": body, "actor_session": str(context.demo_actor_session_id)},
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode()
        ).digest()
        with self.transaction(context, f"workspace:{name}") as connection:
            lock = (
                f"{context.company_id}:{context.demo_run_id}:{context.actor.user_id}:{name}:{key}"
            )
            connection.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))", (lock,))
            receipt = connection.execute(
                """select command_digest,result from app.alto_command_receipts
                where company_id=%s and scope_id=app.current_scope_id() and actor_id=%s
                  and command_key=%s and idempotency_key=%s""",
                (context.company_id, context.actor.user_id, name, key),
            ).fetchone()
            if receipt:
                if bytes(receipt["command_digest"]) != digest:
                    raise WorkspaceConflictError("idempotency key was reused with different input")
                return dict(receipt["result"])
            result = operation(connection)
            connection.execute(
                """insert into app.alto_command_receipts
                (company_id,demo_run_id,actor_id,command_key,idempotency_key,command_digest,result)
                values(%s,%s,%s,%s,%s,%s,%s)""",
                (
                    context.company_id,
                    context.demo_run_id,
                    context.actor.user_id,
                    name,
                    key,
                    digest,
                    Jsonb(result),
                ),
            )
            return result

    def workspace(self, context: CompanyContext) -> WorkspaceBootstrap:
        with self.transaction(context, "workspace:bootstrap") as connection:
            company = connection.execute(
                "select id,name,is_demo from app.companies where id=%s",
                (context.company_id,),
            ).fetchone()
            if company is None:
                raise WorkspaceNotFoundError("company was not found")
            person = connection.execute(
                """select coalesce(e.display_name,u.display_name,'Team member') as display_name,
                   coalesce(e.title,'') as job_title
                from app.user_profiles u left join app.employee_profiles e
                  on e.company_id=%s and e.id=%s where u.user_id=%s""",
                (context.company_id, context.effective_employee_id, context.actor.user_id),
            ).fetchone() or {"display_name": "Team member", "job_title": ""}
            run = None
            if context.demo_run_id:
                run = connection.execute(
                    """select id,mode,clock_at,clock_version,row_version from app.demo_runs
                    where company_id=%s and id=%s""",
                    (context.company_id, context.demo_run_id),
                ).fetchone()
                if run is None:
                    raise WorkspaceNotFoundError("run was not found")
                run = dict(run)
                run["actor_name"] = (
                    person["display_name"] if context.simulated_employee_id else None
                )
                run["actor_session_id"] = context.demo_actor_session_id
            role = (
                "manager"
                if context.administrative_role in {"manager", "company_admin"}
                else "employee"
            )
            if context.simulated_employee_id:
                actor = connection.execute(
                    "select function_key from app.employee_profiles where company_id=%s and id=%s",
                    (context.company_id, context.simulated_employee_id),
                ).fetchone()
                role = "manager" if actor and actor["function_key"] == "leadership" else "employee"
            return WorkspaceBootstrap.model_validate(
                {
                    "company": dict(company),
                    "demo_run": run,
                    "viewer": {
                        "user_id": context.actor.user_id,
                        "employee_id": context.effective_employee_id,
                        "display_name": person["display_name"],
                        "role": role,
                        "job_title": person["job_title"],
                    },
                    "capabilities": [
                        "projects",
                        "people",
                        "calendar",
                        "tasks",
                        "assistant",
                        "preferences",
                        *(["demo"] if company["is_demo"] else []),
                        *(["voice"] if self.voice_enabled else []),
                    ],
                }
            )

    def preferences(self, context: CompanyContext) -> WorkspacePreferences:
        with self.transaction(context, "workspace:preferences") as connection:
            row = connection.execute(
                """select row_version,sidebar_mode='icons' as sidebar_collapsed,
                graph_motion as graph_breathing,reduce_motion,
                overlay_enabled as desktop_shortcut_enabled,shortcut
                from app.workspace_preferences where company_id=%s and membership_id=%s""",
                (context.company_id, context.membership_id),
            ).fetchone()
            return WorkspacePreferences.model_validate(row or {})

    def update_preferences(
        self,
        context: CompanyContext,
        update: PreferencesUpdate,
        key: str,
    ) -> WorkspacePreferences:
        def write(connection: Any) -> dict[str, Any]:
            values = (
                "icons" if update.sidebar_collapsed else "expanded",
                update.graph_breathing,
                update.reduce_motion,
                update.desktop_shortcut_enabled,
                update.shortcut,
            )
            if update.expected_row_version == 0:
                row = connection.execute(
                    """insert into app.workspace_preferences(company_id,membership_id,
                    sidebar_mode,graph_motion,reduce_motion,overlay_enabled,shortcut)
                    values(%s,%s,%s,%s,%s,%s,%s) returning row_version""",
                    (context.company_id, context.membership_id, *values),
                ).fetchone()
            else:
                row = connection.execute(
                    """update app.workspace_preferences set sidebar_mode=%s,graph_motion=%s,
                    reduce_motion=%s,overlay_enabled=%s,shortcut=%s
                    where company_id=%s and membership_id=%s and row_version=%s
                    returning row_version""",
                    (
                        *values,
                        context.company_id,
                        context.membership_id,
                        update.expected_row_version,
                    ),
                ).fetchone()
            if row is None:
                raise WorkspaceConflictError("workspace preferences changed")
            return {"row_version": row["row_version"]}

        self.command(
            context, name="preferences", key=key, body=update.model_dump(), operation=write
        )
        return self.preferences(context)

    def projects(self, context: CompanyContext, *, search: str = "") -> list[Project]:
        with self.transaction(context, "workspace:projects") as connection:
            rows = connection.execute(
                """select p.id,p.title,p.goal_label,p.status,
                coalesce(p.agreed_deadline,p.requested_deadline)
                  as deadline,p.updated_at,p.purpose as description,p.accepted_at,
                  p.accepted_by_employee_id::text as accepted_by,
                  (select count(*) from app.work_items w where w.company_id=p.company_id
                    and w.project_id=p.id) as task_count,
                  (select count(*) from app.work_items w where w.company_id=p.company_id
                    and w.project_id=p.id and w.status='accepted') as completed_task_count,
                  (select plan.id from app.plans plan join app.planning_requests r
                    on r.company_id=plan.company_id and r.id=plan.request_id
                    where r.company_id=p.company_id and r.project_id=p.id
                    order by plan.created_at desc,plan.id desc limit 1) as plan_id
                from app.projects p where p.company_id=%s and p.title ilike %s
                order by p.updated_at desc,p.id limit 100""",
                (context.company_id, f"%{search}%"),
            ).fetchall()
            return [Project.model_validate(row) for row in rows]

    def project(
        self, context: CompanyContext, project_id: UUID, *, connection: Any | None = None
    ) -> Project:
        if connection is None:
            with self.transaction(context, "workspace:project") as selected:
                return self.project(context, project_id, connection=selected)
        row = connection.execute(
            """select p.id,p.title,p.goal_label,p.status,
            coalesce(p.agreed_deadline,p.requested_deadline)
              as deadline,p.updated_at,p.purpose as description,p.accepted_at,
              p.accepted_by_employee_id::text as accepted_by,
              (select count(*) from app.work_items w where w.company_id=p.company_id
                and w.project_id=p.id) as task_count,
              (select count(*) from app.work_items w where w.company_id=p.company_id
                and w.project_id=p.id and w.status='accepted') as completed_task_count,
              (select plan.id from app.plans plan join app.planning_requests r
                on r.company_id=plan.company_id and r.id=plan.request_id
                where r.company_id=p.company_id and r.project_id=p.id
                order by plan.created_at desc,plan.id desc limit 1) as plan_id
            from app.projects p where p.company_id=%s and p.id=%s
              and p.demo_run_id is not distinct from %s""",
            (context.company_id, project_id, context.demo_run_id),
        ).fetchone()
        if row is None:
            raise WorkspaceNotFoundError("project was not found")
        return Project.model_validate(row)

    def actions(self, context: CompanyContext) -> list[dict[str, Any]]:
        with self.transaction(context, "workspace:actions") as connection:
            rows = connection.execute(
                """select q.id,q.question as title,'clarification' as kind,'pending' as status,
                  '/plan-review?request=' || q.request_id::text as target_path,
                  'A recorded answer is needed before planning can continue.' as detail
                from app.clarification_questions q where q.company_id=%s
                  and q.blocks_planning and q.status='open' order by q.created_at limit 50""",
                (context.company_id,),
            ).fetchall()
            review_rows = connection.execute(
                """select s.id,'Review: '||w.title as title,'review' as kind,'pending' as status,
              '/reviews/'||s.id::text as
              target_path,'Inspect and decide on the exact submitted version.' as detail
              from app.submissions s join app.work_items w on w.company_id=s.company_id and
              w.task_id=s.task_id
              join app.task_review_policies rp on rp.company_id=s.company_id and
              rp.id=s.review_policy_id
              where s.company_id=%s and s.state='submitted' and rp.reviewer_employee_id=%s
                and coalesce(w.task_code,'')<>'S4' order by s.submitted_at limit 50""",
                (context.company_id, context.effective_employee_id),
            ).fetchall()
            plan_rows = connection.execute(
                """select p.id,'Review plan: '||pr.title as title,
              'plan' as kind,p.state as status,'/projects/'||pr.id::text as target_path,
              'Plan approval, brief audience approval and commitment are separate decisions.' as
              detail
              from app.plans p join app.planning_requests r on r.company_id=p.company_id and
              r.id=p.request_id
              join app.projects pr on pr.company_id=r.company_id and pr.id=r.project_id
              where p.company_id=%s and p.state='proposed'
                and not exists(select 1 from app.plan_commitments committed
                  where committed.company_id=p.company_id and committed.plan_id=p.id)
                and app.can_manage_planning(p.company_id,app.current_actor_id())
              order by p.created_at limit 50""",
                (context.company_id,),
            ).fetchall()
            corrections = connection.execute(
                """select c.id,'Correction: '||w.title as title,'correction' as kind,c.status,
              '/tasks/'||c.task_id::text as
              target_path,'A versioned work correction needs review before fresh planning.' as
              detail
              from app.task_corrections c join app.work_items w on w.company_id=c.company_id and
              w.task_id=c.task_id
              where c.company_id=%s and c.status='open' order by c.created_at limit 30""",
                (context.company_id,),
            ).fetchall()
            return [dict(row) for row in [*rows, *review_rows, *plan_rows, *corrections]][:100]

    def home(self, context: CompanyContext) -> HomeData:
        projects = self.projects(context)
        tasks: list[EmployeeTask] = []
        if context.effective_employee_id:
            employee = PostgresEmployeeStore(self.dsn, connect_timeout_seconds=self.timeout)
            for view in ("today", "upcoming", "blocked", "submitted"):
                tasks.extend(employee.list_tasks(context=context, view=view))
        return HomeData.model_validate(
            {
                "recent_projects": [p for p in projects if p.status != "completed"][:6],
                "completed_projects": [p for p in projects if p.status == "completed"][:6],
                "actions": self.actions(context),
                "tasks": tasks[:50],
            }
        )

    def demo_runs(self, context: CompanyContext) -> dict[str, Any]:
        with self.transaction(context, "workspace:runs") as connection:
            runs = connection.execute(
                """select id,scenario_key as
                name,mode,clock_at,clock_version,row_version,protected,state as status
                from app.demo_runs where company_id=%s order by created_at desc limit 50""",
                (context.company_id,),
            ).fetchall()
            actors = connection.execute(
                """select id,synthetic_key,display_name,coalesce(title,'') as job_title,
                case when synthetic_key in ('maya','jordan') then 'manager'
                  else 'employee' end as role
                from app.employee_profiles where company_id=%s and profile_kind='synthetic'
                  and scenario_detail='rich' and status='active' order by display_name""",
                (context.company_id,),
            ).fetchall()
            policy = connection.execute(
                "select enabled from app.demo_workspace_policies where company_id=%s",
                (context.company_id,),
            ).fetchone()
            return {
                "runs": [dict(row) for row in runs],
                "actors": [dict(row) for row in actors],
                "can_create": bool(policy and policy["enabled"]),
            }

    def quickstart(
        self,
        context: CompanyContext,
        preferred_actor_key: str | None,
        key: str,
    ) -> DemoQuickstartResponse:
        owner = context

        def start(connection: Any) -> dict[str, Any]:
            # A stable membership-level lock also serializes simultaneous requests
            # carrying different HTTP idempotency keys.
            connection.execute(
                "select pg_advisory_xact_lock(hashtextextended(%s,0))",
                (f"hackathon-quickstart:{owner.company_id}:{owner.membership_id}",),
            )
            run = connection.execute(
                """select id from app.demo_runs
                where company_id=%s and owner_membership_id=%s
                  and mode='live' and state='active'
                order by created_at desc,id desc limit 1""",
                (owner.company_id, owner.membership_id),
            ).fetchone()
            if run is None:
                run = connection.execute(
                    "select app.fork_demo_run(%s,'live',null,%s) as id",
                    (owner.company_id, key),
                ).fetchone()
            run_id = run["id"]
            connection.execute(
                "select app.bind_demo_operator_provider(%s,%s,%s)",
                (owner.company_id, run_id, self.gemini_model),
            )
            actor = connection.execute(
                """select id,synthetic_key from app.employee_profiles
                where company_id=%s and profile_kind='synthetic'
                  and scenario_detail='rich' and status='active'
                order by case when synthetic_key=%s then 0
                  when synthetic_key='maya' then 1 else 2 end,synthetic_key
                limit 1""",
                (owner.company_id, preferred_actor_key),
            ).fetchone()
            if actor is None:
                raise WorkspaceUnavailableError("demo people are unavailable")
            selected = connection.execute(
                "select app.select_demo_actor(%s,%s,%s) as id",
                (owner.company_id, run_id, actor["id"]),
            ).fetchone()
            return {
                "run_id": str(run_id),
                "actor_session_id": str(selected["id"]),
                "actor_key": actor["synthetic_key"],
                "provider_status": "configured",
            }

        result = self.command(
            owner,
            name="hackathon-quickstart",
            key=key,
            body={"preferred_actor_key": preferred_actor_key},
            operation=start,
        )
        return DemoQuickstartResponse.model_validate(result)

    def create_run(
        self,
        context: CompanyContext,
        mode: str,
        parent_run_id: UUID | None,
        key: str,
    ) -> dict[str, str]:
        with self.transaction(context, "demo:fork") as connection:
            row = connection.execute(
                "select app.fork_demo_run(%s,%s,%s,%s) as id",
                (context.company_id, mode, parent_run_id, key),
            ).fetchone()
            return {"id": str(row["id"])}

    def select_actor(
        self,
        context: CompanyContext,
        run_id: UUID,
        employee_id: UUID,
        key: str,
    ) -> dict[str, str]:
        def select(connection: Any) -> dict[str, str]:
            row = connection.execute(
                "select app.select_demo_actor(%s,%s,%s) as id",
                (context.company_id, run_id, employee_id),
            ).fetchone()
            return {"actor_session_id": str(row["id"]), "run_id": str(run_id)}

        return self.command(
            context,
            name="demo-select-actor",
            key=key,
            body={"run_id": str(run_id), "employee_id": str(employee_id)},
            operation=select,
        )

    def advance_clock(
        self,
        context: CompanyContext,
        run_id: UUID,
        expected_version: int,
        clock_at: datetime,
        key: str,
    ) -> dict[str, Any]:
        with self.transaction(context, "demo:advance-clock") as connection:
            row = connection.execute(
                "select app.advance_demo_clock(%s,%s,%s,%s,%s) as value",
                (context.company_id, run_id, expected_version, clock_at, key),
            ).fetchone()
            return dict(row["value"])

    def graph(
        self,
        context: CompanyContext,
        project_id: UUID,
        *,
        proposal_id: UUID | None = None,
        plan_id: UUID | None = None,
    ) -> ProjectGraphData:
        from coordination.workspace.graph_read import graph

        return graph(self, context, project_id, proposal_id=proposal_id, plan_id=plan_id)

    def rule_detail(
        self,
        context: CompanyContext,
        project_id: UUID,
        rule_result_id: UUID,
        *,
        proposal_id: UUID,
    ) -> RuleTechnicalDetail:
        from coordination.workspace.graph_read import rule_detail

        return rule_detail(
            self,
            context,
            project_id,
            rule_result_id,
            proposal_id=proposal_id,
        )

    def calendar(
        self,
        context: CompanyContext,
        start: datetime,
        end: datetime,
        employee_id: UUID | None = None,
    ) -> CalendarData:
        if (
            start.utcoffset() is None
            or end.utcoffset() is None
            or not timedelta(0) < end - start <= timedelta(days=42)
        ):
            raise WorkspaceInputError("calendar interval must be offset-aware and at most 42 days")
        with self.transaction(context, "workspace:calendar") as connection:
            company = connection.execute(
                "select default_timezone from app.companies where id=%s",
                (context.company_id,),
            ).fetchone()
            blocks = connection.execute(
                """select b.id::text,w.title,b.start_at,b.end_at,'work' as kind,'ALTO' as source,
                w.status,b.task_id,w.project_id,coalesce(w.purpose,'') as
                description,e.display_name as owner_name
                from app.committed_schedule_blocks b join app.work_items w
                  on w.company_id=b.company_id and w.task_id=b.task_id
                join app.execution_resources r on r.company_id=b.company_id and r.id=b.resource_id
                left join app.employee_profiles e on e.company_id=r.company_id and
                e.id=r.employee_id
                where b.company_id=%s and b.active and b.end_at>%s and b.start_at<%s
                  and r.employee_id=%s order by b.start_at,b.id limit 1000""",
                (context.company_id, start, end, employee_id),
            ).fetchall()
            events = connection.execute(
                """select ev.id::text,case when ev.visibility='busy_only' then
                'Protected commitment'
                    else coalesce(ev.title,'Busy') end as title,ev.start_at,ev.end_at,
                  case when ev.visibility='busy_only' then 'protected' else 'meeting' end as kind,
                  c.provider as source,c.mode as status,null::uuid as task_id,null::uuid as
                  project_id,
                  '' as description,e.display_name as owner_name
                from app.calendar_event_versions ev join app.integration_connections c
                  on c.company_id=ev.company_id and c.id=ev.connection_id
                join app.employee_profiles e on e.company_id=ev.company_id and e.id=ev.employee_id
                where ev.company_id=%s and ev.status<>'cancelled' and c.status<>'revoked'
                  and ev.end_at>%s and ev.start_at<%s and ev.employee_id=%s
                  and not exists(select 1 from app.calendar_event_versions newer
                    where newer.company_id=ev.company_id and newer.connection_id=ev.connection_id
                      and newer.external_object_key=ev.external_object_key
                      and (newer.created_at,newer.id)>(ev.created_at,ev.id))
                order by ev.start_at,ev.id limit 1000""",
                (context.company_id, start, end, employee_id),
            ).fetchall()
            deadlines = connection.execute(
                """select 'deadline:'||p.id::text as id,p.title,
                  coalesce(p.agreed_deadline,p.requested_deadline) as start_at,
                  coalesce(p.agreed_deadline,p.requested_deadline) as end_at,
                  'deadline' as kind,'ALTO' as source,p.status,null::uuid as task_id,p.id as
                  project_id,
                  'Project deadline — not a meeting or work reservation.' as description,
                  null::text as owner_name from app.projects p where p.company_id=%s
                  and coalesce(p.agreed_deadline,p.requested_deadline)>=%s
                  and coalesce(p.agreed_deadline,p.requested_deadline)<%s limit 100""",
                (context.company_id, start, end),
            ).fetchall()
            sources = connection.execute(
                "select provider as name,case when mode='fixture' then 'fixture' else status end "
                "as status "
                "from app.integration_connections where company_id=%s order by provider",
                (context.company_id,),
            ).fetchall()
            return CalendarData.model_validate(
                {
                    "items": [dict(row) for row in [*blocks, *events, *deadlines]],
                    "timezone": company["default_timezone"],
                    "sources": [dict(row) for row in sources],
                }
            )

    def people(self, context: CompanyContext, *, search: str = "") -> list[dict[str, Any]]:
        with self.transaction(context, "workspace:people") as connection:
            rows = connection.execute(
                """select e.id,coalesce(e.display_name,u.display_name,'Team member') as
                display_name,
                coalesce(e.title,'') as job_title,coalesce(e.function_key,'') as function,
                e.timezone,
                e.scenario_detail as profile_depth,coalesce(po.row_version,e.row_version) as
                row_version,
                coalesce((select g.label from app.employee_operating_group_memberships gm
                  join app.operating_groups g on g.company_id=gm.company_id and g.id=gm.group_id
                  where gm.company_id=e.company_id and gm.employee_id=e.id and gm.valid_to is null
                  order by gm.valid_from desc limit 1),'') as operating_group
                from app.employee_profiles e left join app.employee_profile_overrides po
                  on po.company_id=e.company_id and po.employee_id=e.id
                left join app.company_memberships m
                  on m.company_id=e.company_id and m.id=e.membership_id
                left join app.user_profiles u on u.user_id=m.user_id
                where e.company_id=%s and e.status='active'
                  and (%s::uuid is null or e.profile_kind='synthetic')
                  and coalesce(e.display_name,u.display_name,'') ilike %s order by
                  display_name,e.id limit 100""",
                (context.company_id, context.demo_run_id, f"%{search}%"),
            ).fetchall()
            return [
                {
                    **dict(row),
                    "skills": [],
                    "past_projects": [],
                    "ongoing_projects": [],
                    "availability": [],
                    "shared_preferences": [],
                }
                for row in rows
            ]

    def person(self, context: CompanyContext, employee_id: UUID) -> dict[str, Any]:
        person = next((row for row in self.people(context) if row["id"] == employee_id), None)
        if person is None:
            raise WorkspaceNotFoundError("person was not found")
        with self.transaction(context, "workspace:person") as connection:
            skills = connection.execute(
                """select s.label as name,e.evidence_kind as provenance from
                app.employee_skill_evidence e
                join app.skills s on s.company_id=e.company_id and s.id=e.skill_id
                where e.company_id=%s and e.employee_id=%s and e.status<>'revoked'
                  and e.valid_to is null order by s.label""",
                (context.company_id, employee_id),
            ).fetchall()
            shared = connection.execute(
                """select p.id,p.text,d.decided_at as shared_at from
                app.employee_preference_versions p
                join app.employee_preference_share_decisions d on d.company_id=p.company_id
                  and d.preference_version_id=p.id and d.decision='share' and d.revoked_at is null
                where p.company_id=%s and p.employee_id=%s and d.audience_membership_id=%s
                order by d.decided_at desc limit 20""",
                (context.company_id, employee_id, context.membership_id),
            ).fetchall()
            project_ids = connection.execute(
                """select distinct w.project_id from app.work_items w join app.work_assignments a
                  on a.company_id=w.company_id and a.task_id=w.task_id
                join app.execution_resources r on r.company_id=a.company_id and r.id=a.resource_id
                where w.company_id=%s and r.employee_id=%s and w.project_id is not null""",
                (context.company_id, employee_id),
            ).fetchall()
            clock = (
                connection.execute(
                    "select clock_at from app.demo_runs where company_id=%s and id=%s",
                    (context.company_id, context.demo_run_id),
                ).fetchone()
                if context.demo_run_id
                else None
            )
            person["skills"] = [dict(row) for row in skills]
            declared = connection.execute(
                "select declared_skills from app.employee_profile_overrides where company_id=%s "
                "and employee_id=%s",
                (context.company_id, employee_id),
            ).fetchone()
            if declared:
                person["skills"] = [
                    dict(row) for row in skills if row["provenance"] != "declaration"
                ] + [
                    {"name": label, "provenance": "self_declared"}
                    for label in declared["declared_skills"]
                ]
            person["shared_preferences"] = [dict(row) for row in shared]
        projects = [
            p for p in self.projects(context) if p.id in {row["project_id"] for row in project_ids}
        ]
        person["past_projects"] = [
            p.model_dump(mode="json") for p in projects if p.status == "completed"
        ]
        person["ongoing_projects"] = [
            p.model_dump(mode="json") for p in projects if p.status != "completed"
        ]
        at = clock["clock_at"] if clock else datetime.now(UTC)
        person["availability"] = [
            item.model_dump(mode="json")
            for item in self.calendar(context, at, at + timedelta(days=7), employee_id).items
            if item.kind != "deadline"
        ]
        return person

    def connections(self, context: CompanyContext) -> list[dict[str, Any]]:
        with self.transaction(context, "workspace:connections") as connection:
            rows = connection.execute(
                """select c.id,c.provider,c.mode,c.status,c.timezone,c.last_sync_at,c.row_version,
                c.owner_membership_id,g.access_mode,g.provider_scope,g.capability
                from app.integration_connections c left join app.integration_grants g
                  on g.company_id=c.company_id and g.connection_id=c.id and g.revoked_at is null
                where c.company_id=%s order by c.provider,g.access_mode""",
                (context.company_id,),
            ).fetchall()
            return [
                {
                    "id": str(r["id"]),
                    "name": r["provider"].title(),
                    "provider": r["provider"],
                    "direction": r["access_mode"] or "read",
                    "description": "Synthetic source preview"
                    if r["mode"] == "fixture"
                    else "Connected work source",
                    "scope": r["provider_scope"] or "No permission granted",
                    "status": "fixture"
                    if r["mode"] == "fixture" and r["status"] != "revoked"
                    else r["status"],
                    "timezone": r["timezone"],
                    "imports": [r["capability"]] if r["capability"] else [],
                    "last_synced_at": r["last_sync_at"],
                    "row_version": r["row_version"],
                    "can_revoke": r["owner_membership_id"] == context.membership_id
                    and r["status"] != "revoked",
                }
                for r in rows
            ]
