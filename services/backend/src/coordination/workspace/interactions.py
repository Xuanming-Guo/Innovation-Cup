"""Private employee drafts/consent and assistant thread adapters.

All SQL executes through the role-scoped workspace store. Returned command receipts
contain identifiers only; response content is refetched under current permissions.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4, uuid5

from psycopg.types.json import Jsonb

from coordination.approval.contracts import ApprovalCommand, CommitCommand, PlanBinding
from coordination.approval.persistence import (
    ApprovalAuthorityError,
    ApprovalIdempotencyConflictError,
    ApprovalIncompleteError,
    ApprovalStaleError,
    ApprovalStoreError,
    PlanNotFoundError,
    PostgresApprovalStore,
    ScheduleConflictError,
)
from coordination.auth.models import CompanyContext
from coordination.durable.persistence import DurableStoreError, PostgresDurableStore
from coordination.employee.contracts import ApprovedBrief, EmployeeTask
from coordination.interpretation.persistence import (
    CreatePlanningRequest,
    InterpretationStoreUnavailableError,
    PlanningRequestIdempotencyConflictError,
    PlanningRequestNotFoundError,
    PlanningRequestSourceNotFoundError,
    PostgresInterpretationStore,
)
from coordination.workspace.contracts import (
    AssistantActionDecision,
    AssistantContext,
    DraftUpdate,
    PreferenceDecision,
    PreferenceUpdate,
)
from coordination.workspace.persistence import (
    PostgresWorkspaceStore,
    WorkspaceConflictError,
    WorkspaceInputError,
    WorkspaceNotFoundError,
    WorkspaceUnavailableError,
)


def task_detail(
    store: PostgresWorkspaceStore, context: CompanyContext, task_id: UUID
) -> dict[str, Any]:
    with store.transaction(context, "workspace:task-detail") as connection:
        row = connection.execute(
            """select w.task_id,w.task_key,w.title,w.scheduling_kind,w.status,w.row_version,
            w.start_at,w.finish_at,w.project_id,w.purpose,w.deliverable,w.acceptance_criteria,w.task_code,
            app.task_reviewer_display_name(app.current_actor_id(),w.company_id,rp.id) as
            reviewer_name,
            e.display_name as owner_name,r.employee_id as owner_employee_id,
            s.id as latest_submission_id,s.version as latest_submission_version,
            b.id as brief_id,b.version as brief_version,b.brief_payload,
            c.default_timezone as timezone,p.manager_employee_id,
            manager.display_name as approver_name
            from app.work_items w join app.companies c on c.id=w.company_id
            left join app.execution_resources r on r.company_id=w.company_id and
            r.id=w.owner_resource_id
            left join app.employee_profiles e on e.company_id=r.company_id and e.id=r.employee_id
            left join app.projects p on p.company_id=w.company_id and p.id=w.project_id
            left join app.employee_profiles manager on manager.company_id=p.company_id and
            manager.id=p.manager_employee_id
            left join app.task_review_policies rp on rp.company_id=w.company_id and
            rp.task_id=w.task_id and rp.active
            left join lateral(select sub.id,sub.version from app.submissions sub
              where sub.company_id=w.company_id and sub.task_id=w.task_id order by version desc
              limit 1) s on true
            left join app.employee_brief_versions b on b.company_id=w.company_id and
            b.id=w.employee_brief_version_id
            where w.company_id=%s and w.task_id=%s""",
            (context.company_id, task_id),
        ).fetchone()
        if row is None:
            raise WorkspaceNotFoundError("task was not found")
        task = EmployeeTask(
            **{
                key: row[key]
                for key in (
                    "task_id",
                    "task_key",
                    "title",
                    "scheduling_kind",
                    "status",
                    "row_version",
                    "start_at",
                    "finish_at",
                    "reviewer_name",
                    "latest_submission_id",
                    "latest_submission_version",
                )
            },
            approved_brief=ApprovedBrief(
                brief_version_id=row["brief_id"],
                version=row["brief_version"],
                content=row["brief_payload"],
            )
            if row["brief_id"]
            else None,
        )
        draft = connection.execute(
            "select body as text,version as row_version from app.submission_drafts "
            "where company_id=%s and task_id=%s and employee_id=%s",
            (context.company_id, task_id, context.effective_employee_id),
        ).fetchone()
        attachments = connection.execute(
            """select distinct f.id,f.display_filename as filename,
              coalesce(s.version,1) as version,f.state
            from app.private_files f left join app.submission_files sf on
            sf.company_id=f.company_id and sf.file_id=f.id
            left join app.submissions s on s.company_id=sf.company_id and s.id=sf.submission_id
            where f.company_id=%s and f.deleted_at is null and (
              s.task_id=%s or (f.task_id=%s and f.uploader_employee_id=%s) or exists(
                select 1 from app.task_input_links l where l.company_id=f.company_id and
                l.private_file_id=f.id and l.task_id=%s))
            order by version,f.id""",
            (context.company_id, task_id, task_id, context.effective_employee_id, task_id),
        ).fetchall()
        blocks = connection.execute(
            """select id::text,block_role as title,start_at,end_at,'work' as kind
            from app.committed_schedule_blocks where company_id=%s and task_id=%s and active
            order by start_at,id""",
            (context.company_id, task_id),
        ).fetchall()
        events = connection.execute(
            """select id::text,event_type as title,occurred_at as start_at,
            null::timestamptz as end_at,'event' as kind from app.task_events
            where company_id=%s and task_id=%s order by occurred_at,id limit 100""",
            (context.company_id, task_id),
        ).fetchall()
        required_submission = None
        if row["task_code"] == "R2":
            required_submission = connection.execute(
                """select s.id,s.version,encode(s.submission_digest,'hex') as digest,
              s.narrative from app.submissions s join app.work_items w on
              w.company_id=s.company_id and w.task_id=s.task_id
              where w.company_id=%s and w.project_id=%s and w.task_code='S4' and s.state='submitted'
              order by s.version desc limit 1""",
                (context.company_id, row["project_id"]),
            ).fetchone()
        protected = connection.execute(
            """select id::text,'Protected commitment' as title,start_at,end_at
          from app.calendar_event_versions c where company_id=%s and employee_id=%s and
          status='busy'
            and end_at>%s and start_at<%s and not exists(select 1 from app.calendar_event_versions
            newer
              where newer.company_id=c.company_id and newer.connection_id=c.connection_id
                and newer.employee_id=c.employee_id and
                newer.external_object_key=c.external_object_key
                and newer.created_at>c.created_at) order by start_at limit 20""",
            (context.company_id, row["owner_employee_id"], row["start_at"], row["finish_at"]),
        ).fetchall()
    return {
        "task": task.model_dump(mode="json"),
        "project": store.project(context, row["project_id"]).model_dump(mode="json")
        if row["project_id"]
        else None,
        "owner_name": row["owner_name"],
        "reviewer_name": row["reviewer_name"],
        "approver_name": row["approver_name"],
        "timezone": row["timezone"],
        "timeline": [dict(r) for r in [*blocks, *events]],
        "protected_commitments": [
            f"Protected commitment · {r['start_at'].isoformat()} to {r['end_at'].isoformat()}"
            for r in protected
        ],
        "attachments": [dict(r) for r in attachments],
        "can_work": row["owner_employee_id"] == context.effective_employee_id
        and row["status"] not in {"accepted", "cancelled"},
        "can_give_feedback": row["owner_employee_id"] == context.effective_employee_id
        and row["status"] == "accepted",
        "draft": dict(draft) if draft else None,
        "gate": {
            "kind": "readiness" if row["task_code"] == "R1" else "milestone",
            "required_submission": dict(required_submission) if required_submission else None,
        }
        if row["task_code"] in {"R1", "R2"}
        else None,
    }


def save_draft(
    store: PostgresWorkspaceStore,
    context: CompanyContext,
    task_id: UUID,
    body: DraftUpdate,
    key: str,
) -> dict[str, Any]:
    def write(connection: Any) -> dict[str, Any]:
        task = connection.execute(
            """select w.status from app.work_items w join app.execution_resources r
            on r.company_id=w.company_id and r.id=w.owner_resource_id
            where w.company_id=%s and w.task_id=%s and r.employee_id=%s""",
            (context.company_id, task_id, context.effective_employee_id),
        ).fetchone()
        if task is None:
            raise WorkspaceNotFoundError("task was not found")
        if task["status"] in {"accepted", "cancelled", "submitted"}:
            raise WorkspaceConflictError("a new draft cannot edit the recorded submission")
        if body.expected_row_version == 0:
            row = connection.execute(
                """insert into
                app.submission_drafts(company_id,demo_run_id,task_id,employee_id,body)
                values(%s,%s,%s,%s,%s) returning id,version""",
                (
                    context.company_id,
                    context.demo_run_id,
                    task_id,
                    context.effective_employee_id,
                    body.text,
                ),
            ).fetchone()
        else:
            row = connection.execute(
                """update app.submission_drafts set
                body=%s,version=version+1,updated_at=clock_timestamp()
                where company_id=%s and task_id=%s and employee_id=%s and version=%s returning
                id,version""",
                (
                    body.text,
                    context.company_id,
                    task_id,
                    context.effective_employee_id,
                    body.expected_row_version,
                ),
            ).fetchone()
        if row is None:
            raise WorkspaceConflictError("draft changed")
        return {"id": str(row["id"]), "row_version": row["version"]}

    store.command(
        context, name=f"draft:{task_id}", key=key, body=body.model_dump(), operation=write
    )
    return task_detail(store, context, task_id)


def employee_preferences(
    store: PostgresWorkspaceStore, context: CompanyContext
) -> list[dict[str, Any]]:
    with store.transaction(context, "preferences:self") as connection:
        rows = connection.execute(
            """select p.id,p.text,p.status,p.version as row_version,d.decision,
            coalesce(d.audience_employee_id,d.audience_membership_id) as manager_id,
            manager.display_name as manager_name,d.decided_at as shared_at
            from app.employee_preference_versions p left join lateral(
              select audience_membership_id,audience_employee_id,decision,decided_at from
              app.employee_preference_share_decisions s
              where s.company_id=p.company_id and s.preference_version_id=p.id and s.revoked_at is
              null
              order by s.decided_at desc,s.id desc limit 1) d on true
            left join app.employee_profiles manager on manager.company_id=p.company_id
              and (manager.id=d.audience_employee_id or (d.audience_employee_id is null and
              manager.membership_id=d.audience_membership_id))
            where p.company_id=%s and p.employee_id=%s and not exists(
              select 1 from app.employee_preference_versions child where
              child.company_id=p.company_id
                and child.parent_version_id=p.id) order by p.created_at desc limit 30""",
            (context.company_id, context.effective_employee_id),
        ).fetchall()
        return [
            {
                "id": str(r["id"]),
                "text": r["text"],
                "status": "shared"
                if r["decision"] == "share"
                else "private"
                if r["decision"] == "keep_private"
                else r["status"],
                "row_version": r["row_version"],
                "manager_id": str(r["manager_id"]) if r["manager_id"] else None,
                "manager_name": r["manager_name"],
                "shared_at": r["shared_at"] if r["decision"] == "share" else None,
            }
            for r in rows
        ]


def edit_preference(
    store: PostgresWorkspaceStore,
    context: CompanyContext,
    preference_id: UUID,
    body: PreferenceUpdate,
    key: str,
) -> dict[str, Any]:
    def write(connection: Any) -> dict[str, Any]:
        connection.execute(
            "select pg_advisory_xact_lock(hashtextextended(%s,0))",
            (f"preference:{context.demo_run_id}:{context.effective_employee_id}",),
        )
        current = connection.execute(
            "select version from app.employee_preference_versions p where company_id=%s and id=%s "
            "and employee_id=%s "
            "and not exists(select 1 from app.employee_preference_versions child where "
            "child.company_id=p.company_id and child.parent_version_id=p.id)",
            (context.company_id, preference_id, context.effective_employee_id),
        ).fetchone()
        if current is None:
            raise WorkspaceNotFoundError("preference was not found")
        if current["version"] != body.expected_row_version:
            raise WorkspaceConflictError("preference changed")
        next_version = connection.execute(
            "select coalesce(max(version),0)+1 as version from app.employee_preference_versions "
            "where company_id=%s and employee_id=%s",
            (context.company_id, context.effective_employee_id),
        ).fetchone()["version"]
        row = connection.execute(
            """insert into app.employee_preference_versions(company_id,demo_run_id,employee_id,
            version,parent_version_id,text,origin,status)
            values(%s,%s,%s,%s,%s,%s,'employee','confirmed') returning id""",
            (
                context.company_id,
                context.demo_run_id,
                context.effective_employee_id,
                next_version,
                preference_id,
                body.text,
            ),
        ).fetchone()
        connection.execute(
            "update app.employee_preference_share_decisions set revoked_at=clock_timestamp() "
            "where company_id=%s and preference_version_id=%s and revoked_at is null",
            (context.company_id, preference_id),
        )
        return {"id": str(row["id"]), "row_version": next_version}

    receipt = store.command(
        context,
        name=f"preference-edit:{preference_id}",
        key=key,
        body=body.model_dump(),
        operation=write,
    )
    return {"id": receipt["id"], "preferences": employee_preferences(store, context)}


def decide_preference(
    store: PostgresWorkspaceStore,
    context: CompanyContext,
    preference_id: UUID,
    body: PreferenceDecision,
    decision: str,
    key: str,
) -> dict[str, Any]:
    def write(connection: Any) -> dict[str, Any]:
        connection.execute(
            "select pg_advisory_xact_lock(hashtextextended(%s,0))",
            (f"preference:{context.demo_run_id}:{context.effective_employee_id}",),
        )
        current = connection.execute(
            """select p.id,p.version,p.status,p.text from app.employee_preference_versions p
            where p.company_id=%s and p.id=%s and p.employee_id=%s and not exists(
              select 1 from app.employee_preference_versions child where
              child.company_id=p.company_id and child.parent_version_id=p.id)""",
            (context.company_id, preference_id, context.effective_employee_id),
        ).fetchone()
        if current is None:
            raise WorkspaceNotFoundError("preference was not found")
        if current["version"] != body.expected_row_version:
            raise WorkspaceConflictError("preference changed")
        connection.execute(
            "update app.employee_preference_share_decisions set revoked_at=clock_timestamp() "
            "where company_id=%s and preference_version_id=%s and revoked_at is null",
            (context.company_id, preference_id),
        )
        if decision == "revoke":
            return {"id": str(preference_id)}
        audience_membership = None
        audience_employee = None
        if decision == "share":
            if body.manager_id is None:
                raise WorkspaceInputError("select the exact manager audience before sharing")
            if context.demo_run_id:
                audience_membership, audience_employee = context.membership_id, body.manager_id
            else:
                audience_membership = body.manager_id
        selected = preference_id
        if current["status"] != "confirmed":
            row = connection.execute(
                """insert into
                app.employee_preference_versions(company_id,demo_run_id,employee_id,version,parent_version_id,text,origin,status)
                select %s,%s,%s,coalesce(max(version),0)+1,%s,%s,'employee','confirmed'
                from app.employee_preference_versions where company_id=%s and employee_id=%s
                returning id""",
                (
                    context.company_id,
                    context.demo_run_id,
                    context.effective_employee_id,
                    preference_id,
                    current["text"],
                    context.company_id,
                    context.effective_employee_id,
                ),
            ).fetchone()
            selected = row["id"]
        connection.execute(
            """insert into
            app.employee_preference_share_decisions(company_id,demo_run_id,preference_version_id,
              audience_membership_id,audience_employee_id,decision,decided_by_auth_user_id,simulated_actor_employee_id)
            values(%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                context.company_id,
                context.demo_run_id,
                selected,
                audience_membership,
                audience_employee,
                "share" if decision == "share" else "keep_private",
                context.actor.user_id,
                context.simulated_employee_id,
            ),
        )
        return {"id": str(selected)}

    receipt = store.command(
        context,
        name=f"preference-{decision}:{preference_id}",
        key=key,
        body=body.model_dump(),
        operation=write,
    )
    return {"id": receipt["id"], "preferences": employee_preferences(store, context)}


def create_thread(
    store: PostgresWorkspaceStore,
    context: CompanyContext,
    binding: AssistantContext,
    key: str,
) -> dict[str, Any]:
    if (binding.kind == "global") != (binding.id is None):
        raise WorkspaceInputError("assistant context requires one matching subject")
    if binding.proposal_id is not None and not context.can_manage_planning:
        # Do not reveal whether a proposal exists to an actor without planning
        # authority. Postgres rechecks current authority and exact project scope.
        raise WorkspaceNotFoundError("proposal was not found")

    def write(connection: Any) -> dict[str, Any]:
        if binding.proposal_id is not None:
            permitted = connection.execute(
                "select app.can_bind_assistant_proposal(%s,%s,%s) as permitted",
                (context.company_id, binding.id, binding.proposal_id),
            ).fetchone()
            if permitted is None or not permitted["permitted"]:
                raise WorkspaceNotFoundError("proposal was not found")
        row = connection.execute(
            """insert into app.assistant_threads(company_id,demo_run_id,owner_membership_id,
            context_type,context_id,simulated_employee_id,proposal_id)
            values(%s,%s,%s,%s,%s,%s,%s) returning id""",
            (
                context.company_id,
                context.demo_run_id,
                context.membership_id,
                "workspace" if binding.kind == "global" else binding.kind,
                binding.id,
                context.simulated_employee_id,
                binding.proposal_id,
            ),
        ).fetchone()
        return {"id": str(row["id"])}

    receipt = store.command(
        context, name="assistant-thread", key=key, body=binding.model_dump(), operation=write
    )
    return get_thread(store, context, UUID(receipt["id"]))


def get_thread(
    store: PostgresWorkspaceStore, context: CompanyContext, thread_id: UUID
) -> dict[str, Any]:
    with store.transaction(context, "assistant:thread") as connection:
        thread = connection.execute(
            "select id from app.assistant_threads where company_id=%s and id=%s",
            (context.company_id, thread_id),
        ).fetchone()
        if thread is None:
            raise WorkspaceNotFoundError("thread was not found")
        rows = connection.execute(
            """select m.id,m.role,m.content,m.created_at,m.operation_id from
            (select id,role,content,created_at,operation_id from app.assistant_messages
            where company_id=%s and thread_id=%s order by created_at desc,id desc limit 100) m
            order by m.created_at,m.id""",
            (context.company_id, thread_id),
        ).fetchall()
        citations = connection.execute(
            """select c.message_id,c.permitted_label as label,c.task_id,c.source_version_id
            from app.assistant_citations c join app.assistant_messages m
              on m.company_id=c.company_id and m.id=c.message_id
            where c.company_id=%s and m.thread_id=%s and m.id=any(%s::uuid[])""",
            (context.company_id, thread_id, [row["id"] for row in rows]),
        ).fetchall()
        action_rows = connection.execute(
            """
            select action.id,action.command_type,action.state,action.title,action.summary,
              action.project_id,action.proposal_id,action.plan_id,action.expected_version,
              action.row_version,action.expires_at,action.action_payload,action.result
            from app.assistant_action_previews action
            join app.assistant_messages message
              on message.company_id=action.company_id and message.id=action.message_id
            where action.company_id=%s and message.thread_id=%s
            order by message.created_at,action.id
            """,
            (context.company_id, thread_id),
        ).fetchall()
        job = connection.execute(
            """select j.id,j.state,j.last_error_code from app.durable_jobs j
            where j.company_id=%s and j.job_kind='assistant.respond'
              and j.payload->>'thread_id'=%s order by j.created_at desc,j.id desc limit 1""",
            (context.company_id, str(thread_id)),
        ).fetchone()
        state = str(job["state"]) if job else "idle"
        public_state = {
            "leased": "running",
            "retry_scheduled": "queued",
            "succeeded": "completed",
            "dead_letter": "failed",
            "review_required": "failed",
        }.get(state, state)
        return {
            "id": str(thread_id),
            "messages": [
                {
                    "id": str(r["id"]),
                    "role": r["role"],
                    "content": r["content"],
                    "created_at": r["created_at"],
                    "citations": [
                        {
                            "label": c["label"],
                            "target_path": f"/tasks/{c['task_id']}"
                            if c["task_id"]
                            else f"/sources/{c['source_version_id']}",
                        }
                        for c in citations
                        if c["message_id"] == r["id"]
                    ],
                }
                for r in rows
            ],
            "pending_actions": [
                {
                    "id": str(action["id"]),
                    "kind": action["command_type"],
                    "status": (
                        "expired"
                        if action["state"] == "pending_confirmation"
                        and action["expires_at"] <= datetime.now(UTC)
                        else action["state"]
                    ),
                    "title": action["title"],
                    "summary": action["summary"],
                    "project_id": str(action["project_id"]) if action["project_id"] else None,
                    "proposal_id": str(action["proposal_id"]) if action["proposal_id"] else None,
                    "plan_id": str(action["plan_id"]) if action["plan_id"] else None,
                    "scope": action["action_payload"].get("scope", []),
                    "changes": action["action_payload"].get("changes", []),
                    "violations": action["action_payload"].get("violations", []),
                    "warnings": action["action_payload"].get("warnings", []),
                    "confirmation": {
                        "label": (
                            "Start checked revision"
                            if action["command_type"] == "plan_change"
                            and action["action_payload"].get("executable", False)
                            else "Open plan review"
                            if action["command_type"] == "plan_change"
                            else "Confirm approval"
                            if action["command_type"] == "plan_approval"
                            else "Confirm and assign work"
                            if action["command_type"] == "plan_commit"
                            else "Confirm"
                        ),
                        "consequence": (
                            "This opens the exact proposal. It does not change or assign work."
                            if action["command_type"] == "plan_change"
                            and not action["action_payload"].get("executable", False)
                            else action["summary"]
                        ),
                        "expected_version": action["row_version"],
                    },
                    "result_target_path": (
                        (action["result"] or {}).get("target_path")
                        or action["action_payload"].get("result_target_path")
                    ),
                }
                for action in action_rows
                if action["command_type"] in {"plan_change", "plan_approval", "plan_commit"}
            ],
            "status": public_state,
            "stage": "Preparing an authorised answer"
            if public_state in {"queued", "running"}
            else None,
            "error": job["last_error_code"] if job and public_state == "failed" else None,
        }


def decide_action(
    store: PostgresWorkspaceStore,
    context: CompanyContext,
    thread_id: UUID,
    action_id: UUID,
    body: AssistantActionDecision,
    key: str,
    before_ai_command: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Confirm a staged action through existing domain commands.

    Model output only creates the preview. The authenticated manager's separate
    decision reaches this function, and every downstream store rechecks its own
    exact binding, authority, freshness and idempotency invariants.
    """
    if not context.can_manage_planning:
        raise WorkspaceNotFoundError("action was not found")
    with store.transaction(context, "assistant:action-read") as connection:
        action = connection.execute(
            """
            select action.id,action.command_type,action.state,action.row_version,
              action.expires_at,action.project_id,action.proposal_id,action.plan_id,
              action.action_payload
            from app.assistant_action_previews action
            join app.assistant_messages message
              on message.company_id=action.company_id and message.id=action.message_id
            where action.company_id=%s and action.id=%s and message.thread_id=%s
            """,
            (context.company_id, action_id, thread_id),
        ).fetchone()
        if action is None:
            raise WorkspaceNotFoundError("action was not found")
        action = dict(action)
        if action["state"] == "completed":
            return get_thread(store, context, thread_id)
        if action["state"] != "pending_confirmation":
            raise WorkspaceConflictError("action is no longer awaiting confirmation")
        if action["row_version"] != body.expected_version:
            raise WorkspaceConflictError("action changed; review it again")
        expired = action["expires_at"] <= datetime.now(UTC)

    terminal_state = "dismissed" if body.decision == "dismiss" else "completed"
    result: dict[str, Any]
    if expired:
        terminal_state = "expired"
        result = {"target_path": f"/projects/{action['project_id']}/graph"}
    elif body.decision == "dismiss":
        result = {"target_path": f"/projects/{action['project_id']}/graph"}
    elif action["command_type"] == "plan_change":
        if before_ai_command is not None and action["action_payload"].get("executable", False):
            before_ai_command()
        result = _confirm_plan_change(store, context, action_id, action)
    elif action["command_type"] == "plan_approval":
        payload = action["action_payload"]
        try:
            decision = PostgresApprovalStore(
                store.dsn, connect_timeout_seconds=store.timeout
            ).decide(
                context=context,
                plan_id=action["plan_id"],
                command=ApprovalCommand(
                    requirement_id=UUID(payload["requirement_id"]),
                    decision="approved",
                    explanation="Confirmed from an ALTO assistant action preview.",
                    artifact_digest=payload["artifact_digest"],
                    binding=PlanBinding.model_validate(payload["binding"]),
                    idempotency_key=f"assistant-action:{action_id}:approve",
                    correlation_id=uuid5(action_id, "approve"),
                ),
            )
        except (PlanNotFoundError, ApprovalAuthorityError) as error:
            raise WorkspaceNotFoundError("action is no longer authorised") from error
        except (ApprovalStaleError, ApprovalIdempotencyConflictError) as error:
            raise WorkspaceConflictError("the exact plan binding changed") from error
        except (ApprovalStoreError, ValueError, KeyError) as error:
            raise WorkspaceUnavailableError("plan approval could not be completed") from error
        result = {
            "decision_id": str(decision.decision_id),
            "target_path": f"/projects/{action['project_id']}/graph",
        }
    elif action["command_type"] == "plan_commit":
        payload = action["action_payload"]
        try:
            commitment = PostgresApprovalStore(
                store.dsn, connect_timeout_seconds=store.timeout
            ).commit(
                context=context,
                plan_id=action["plan_id"],
                command=CommitCommand(
                    binding=PlanBinding.model_validate(payload["binding"]),
                    idempotency_key=f"assistant-action:{action_id}:commit",
                    correlation_id=uuid5(action_id, "commit"),
                ),
            )
        except (PlanNotFoundError, ApprovalAuthorityError) as error:
            raise WorkspaceNotFoundError("action is no longer authorised") from error
        except (
            ApprovalIncompleteError,
            ApprovalStaleError,
            ApprovalIdempotencyConflictError,
            ScheduleConflictError,
        ) as error:
            raise WorkspaceConflictError(
                "the exact approved plan is no longer committable"
            ) from error
        except (ApprovalStoreError, ValueError, KeyError) as error:
            raise WorkspaceUnavailableError("plan commitment could not be completed") from error
        result = {
            "commitment_id": str(commitment.commitment_id),
            "target_path": f"/projects/{action['project_id']}/graph",
        }
    else:
        raise WorkspaceInputError("action type is not confirmable")

    def finish(connection: Any) -> dict[str, Any]:
        row = connection.execute(
            """
            update app.assistant_action_previews set state=%s,result=%s,
              row_version=row_version+1,decided_by_auth_user_id=app.current_actor_id(),
              decided_at=clock_timestamp()
            where company_id=%s and id=%s and state='pending_confirmation'
              and row_version=%s returning id
            """,
            (
                terminal_state,
                Jsonb(result),
                context.company_id,
                action_id,
                body.expected_version,
            ),
        ).fetchone()
        if row is None:
            raise WorkspaceConflictError("action changed; refresh before trying again")
        return {"id": str(action_id), "state": terminal_state}

    store.command(
        context,
        name=f"assistant-action:{action_id}",
        key=key,
        body=body.model_dump(mode="json"),
        operation=finish,
    )
    return get_thread(store, context, thread_id)


def _confirm_plan_change(
    store: PostgresWorkspaceStore,
    context: CompanyContext,
    action_id: UUID,
    action: dict[str, Any],
) -> dict[str, Any]:
    payload = action["action_payload"]
    if not payload.get("executable", False):
        # The bounded synthetic scenario has no typed authority for arbitrary
        # revisions. Confirmation is still useful as explicit navigation, but
        # it deliberately creates no request and changes no schedule.
        return {
            "outcome": "open_review",
            "target_path": payload["result_target_path"],
        }
    with store.transaction(context, "assistant:change-context") as connection:
        parent = connection.execute(
            """
            select request.id,request.original_prompt,request.requested_priority_key,
              request.requested_deadline,request.requested_deadline_timezone,
              array_agg(selected.source_id order by selected.source_id) as source_ids
            from app.ai_plan_proposals proposal
            join app.planning_snapshots snapshot
              on snapshot.company_id=proposal.company_id and snapshot.id=proposal.snapshot_id
            join app.planning_requests request
              on request.company_id=snapshot.company_id and request.id=snapshot.request_id
            join app.planning_request_sources selected
              on selected.company_id=request.company_id and selected.request_id=request.id
            where proposal.company_id=%s and proposal.id=%s and request.project_id=%s
              and proposal.scope_id=app.current_scope_id()
            group by request.id,request.original_prompt,request.requested_priority_key,
              request.requested_deadline,request.requested_deadline_timezone
            """,
            (context.company_id, action["proposal_id"], action["project_id"]),
        ).fetchone()
        if parent is None:
            raise WorkspaceConflictError("the selected proposal is no longer available")
    manager_request = str(payload.get("manager_request", "")).strip()
    if not manager_request:
        raise WorkspaceInputError("the staged change request is empty")
    request_key = f"assistant-action:{action_id}:request"
    try:
        request = PostgresInterpretationStore(
            store.dsn, connect_timeout_seconds=store.timeout
        ).create_request(
            context=context,
            command=CreatePlanningRequest(
                project_id=action["project_id"],
                original_request=(
                    f"{parent['original_prompt'].strip()}\n\n"
                    f"Manager-confirmed change request: {manager_request}"
                )[:8000],
                selected_source_ids=tuple(parent["source_ids"]),
                requested_priority_key=parent["requested_priority_key"],
                requested_deadline=parent["requested_deadline"],
                requested_deadline_timezone=parent["requested_deadline_timezone"],
                idempotency_key=request_key,
            ),
        )
        job_key = f"assistant-action:{action_id}:interpret"
        command_digest = hashlib.sha256(
            f"{request.request_id}:interpretation.run".encode()
        ).digest()
        job = PostgresDurableStore(store.dsn, connect_timeout_seconds=store.timeout).ensure_job(
            context=context,
            job_kind="interpretation.run",
            aggregate_id=request.request_id,
            idempotency_key=job_key,
            command_digest=command_digest,
            correlation_id=uuid5(action_id, "interpret"),
        )
    except (
        PlanningRequestNotFoundError,
        PlanningRequestSourceNotFoundError,
    ) as error:
        raise WorkspaceNotFoundError("the planning context is no longer available") from error
    except PlanningRequestIdempotencyConflictError as error:
        raise WorkspaceConflictError("the staged planning request changed") from error
    except (InterpretationStoreUnavailableError, DurableStoreError, ValueError) as error:
        raise WorkspaceUnavailableError("revised planning request could not be started") from error
    return {
        "request_id": str(request.request_id),
        "job_id": str(job.job_id),
        "target_path": f"/home?request={request.request_id}",
    }


def send_message(
    store: PostgresWorkspaceStore,
    context: CompanyContext,
    thread_id: UUID,
    content: str,
    binding: AssistantContext,
    key: str,
) -> dict[str, Any]:
    def write(connection: Any) -> dict[str, Any]:
        thread = connection.execute(
            "select context_type,context_id,proposal_id from app.assistant_threads "
            "where company_id=%s and id=%s",
            (context.company_id, thread_id),
        ).fetchone()
        if thread is None:
            raise WorkspaceNotFoundError("thread was not found")
        if (
            thread["context_type"] != ("workspace" if binding.kind == "global" else binding.kind)
            or thread["context_id"] != binding.id
            or thread["proposal_id"] != binding.proposal_id
        ):
            raise WorkspaceConflictError("thread context changed")
        message_id = uuid4()
        connection.execute(
            """insert into
            app.assistant_messages(id,company_id,demo_run_id,thread_id,role,content,status,idempotency_key)
            values(%s,%s,%s,%s,'user',%s,'completed',%s)""",
            (message_id, context.company_id, context.demo_run_id, thread_id, content, key),
        )
        job = connection.execute(
            "select app.enqueue_alto_assistant(%s,%s,%s,%s) as id",
            (context.company_id, thread_id, message_id, key),
        ).fetchone()
        return {"id": str(thread_id), "operation_id": str(job["id"])}

    store.command(
        context,
        name=f"assistant-send:{thread_id}",
        key=key,
        body={"content": content, "context": binding.model_dump()},
        operation=write,
    )
    return get_thread(store, context, thread_id)
