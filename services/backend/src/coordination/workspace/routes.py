from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from psycopg.types.json import Jsonb

from coordination.ai_rate_limit import (
    DemoAiCommandLimiterDependency,
    admit_demo_ai_command,
)
from coordination.auth.dependencies import AuthenticatedUserDependency, CompanyContextDependency
from coordination.auth.models import CompanyContext
from coordination.config import Settings, get_settings
from coordination.db.session import authenticated_transaction
from coordination.workspace import commands, interactions
from coordination.workspace.contracts import (
    AdvanceClock,
    AssistantActionDecision,
    AssistantTurn,
    CalendarData,
    CancelThread,
    CreateRun,
    CreateThread,
    DemoQuickstartRequest,
    DemoQuickstartResponse,
    DraftUpdate,
    FeedbackRequest,
    FinalizeUpload,
    GateApproval,
    HomeData,
    NewPreference,
    OnboardingRequest,
    PreferenceDecision,
    PreferencesUpdate,
    PreferenceUpdate,
    ProfileSkills,
    Project,
    ProjectGraphData,
    RuleTechnicalDetail,
    SelectActor,
    VersionCommand,
    VoiceRequest,
    WorkspaceBootstrap,
    WorkspacePreferences,
)
from coordination.workspace.persistence import DemoAiUnavailableError, PostgresWorkspaceStore

router = APIRouter(tags=["ALTO workspace"])


def get_workspace_store(
    settings: Annotated[Settings, Depends(get_settings)],
) -> PostgresWorkspaceStore:
    if settings.database_url is None:
        raise HTTPException(status_code=503, detail="workspace database is not configured")
    return PostgresWorkspaceStore(
        settings.database_url.get_secret_value(),
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
        voice_enabled=bool(settings.file_scanner_host and settings.supabase_url),
        gemini_model=settings.gemini_model,
    )


def workspace_context(company_id: UUID, context: CompanyContextDependency) -> CompanyContext:
    if company_id != context.company_id:
        raise HTTPException(status_code=404, detail="company was not found")
    return context


def command_key(
    value: Annotated[str, Header(alias="Idempotency-Key", min_length=16, max_length=128)],
) -> str:
    return value


Store = Annotated[PostgresWorkspaceStore, Depends(get_workspace_store)]
Context = Annotated[CompanyContext, Depends(workspace_context)]
Key = Annotated[str, Depends(command_key)]
C = "/v1/companies/{company_id}"


@router.post("/v1/demo/onboarding")
def onboard(
    body: OnboardingRequest, user: AuthenticatedUserDependency, store: Store, key: Key
) -> dict[str, Any]:
    if user.is_anonymous:
        body = OnboardingRequest(display_name="Hackathon judge", requested_role="manager")
    try:
        with authenticated_transaction(
            store.dsn,
            actor_id=user.user_id,
            purpose="demo:onboard",
            connect_timeout_seconds=store.timeout,
        ) as connection:
            row = connection.execute(
                "select app.bootstrap_demo_membership(%s,%s,%s) as value",
                (body.display_name, body.requested_role, key),
            ).fetchone()
            return dict(row["value"])
    except psycopg.errors.InsufficientPrivilege as error:
        raise HTTPException(
            status_code=403, detail="demo onboarding is unavailable for this account"
        ) from error
    except psycopg.Error as error:
        raise HTTPException(status_code=503, detail="demo onboarding is unavailable") from error


@router.get(C + "/workspace", response_model=WorkspaceBootstrap)
def workspace(context: Context, store: Store) -> WorkspaceBootstrap:
    return store.workspace(context)


@router.get(C + "/me/preferences", response_model=WorkspacePreferences)
def preferences(context: Context, store: Store) -> WorkspacePreferences:
    return store.preferences(context)


@router.patch(C + "/me/preferences", response_model=WorkspacePreferences)
def update_preferences(
    body: PreferencesUpdate, context: Context, store: Store, key: Key
) -> WorkspacePreferences:
    return store.update_preferences(context, body, key)


@router.get(C + "/home", response_model=HomeData)
def home(context: Context, store: Store) -> HomeData:
    return store.home(context)


@router.get(C + "/manager/actions")
def actions(context: Context, store: Store) -> dict[str, Any]:
    return {"actions": store.actions(context)}


@router.get(C + "/projects")
def projects(
    context: Context, store: Store, q: str = Query(default="", max_length=160)
) -> dict[str, Any]:
    return {"projects": store.projects(context, search=q)}


@router.get(C + "/projects/{project_id}", response_model=Project)
def project(project_id: UUID, context: Context, store: Store) -> Project:
    return store.project(context, project_id)


@router.get(C + "/projects/{project_id}/graph", response_model=ProjectGraphData)
def graph(
    project_id: UUID,
    context: Context,
    store: Store,
    proposal_id: UUID | None = None,
    plan_id: UUID | None = None,
) -> ProjectGraphData:
    return store.graph(context, project_id, proposal_id=proposal_id, plan_id=plan_id)


@router.get(
    C + "/projects/{project_id}/graph/rules/{rule_id}",
    response_model=RuleTechnicalDetail,
)
def graph_rule_detail(
    project_id: UUID,
    rule_id: UUID,
    context: Context,
    store: Store,
    proposal_id: UUID,
) -> RuleTechnicalDetail:
    return store.rule_detail(
        context,
        project_id,
        rule_id,
        proposal_id=proposal_id,
    )


@router.get(C + "/people")
def people(
    context: Context, store: Store, q: str = Query(default="", max_length=120)
) -> dict[str, Any]:
    return {"people": store.people(context, search=q)}


@router.get(C + "/people/{employee_id}")
def person(employee_id: UUID, context: Context, store: Store) -> dict[str, Any]:
    return store.person(context, employee_id)


@router.patch(C + "/me/profile")
def edit_profile(body: ProfileSkills, context: Context, store: Store, key: Key) -> dict[str, Any]:
    if context.effective_employee_id is None:
        raise HTTPException(status_code=403, detail="an employee profile is required")

    def write(connection: Any) -> dict[str, Any]:
        row = connection.execute(
            "select app.update_alto_profile_skills(%s,%s,%s,%s) as result",
            (
                context.company_id,
                context.effective_employee_id,
                body.expected_row_version,
                Jsonb(body.skills),
            ),
        ).fetchone()
        return {
            "employee_id": str(context.effective_employee_id),
            "row_version": row["result"]["row_version"],
        }

    store.command(context, name="profile-skills", key=key, body=body.model_dump(), operation=write)
    return store.person(context, context.effective_employee_id)


@router.get(C + "/calendar", response_model=CalendarData)
def calendar(
    context: Context,
    store: Store,
    start: datetime | None = None,
    end: datetime | None = None,
) -> CalendarData:
    first = start or datetime.now(UTC)
    last = end or first + timedelta(days=7)
    # Date-only query values denote UTC midnight; full timestamps must retain their offset.
    if first.utcoffset() is None:
        first = first.replace(tzinfo=UTC)
    if last.utcoffset() is None:
        last = last.replace(tzinfo=UTC)
    # This route is the viewer's personal calendar even when the effective actor
    # can manage planning.  In demo mode effective_employee_id is the selected
    # synthetic actor, not the authenticated visitor's real profile.
    return store.calendar(context, first, last, context.effective_employee_id)


@router.get(C + "/connections")
def connections(context: Context, store: Store) -> dict[str, Any]:
    return {"connections": store.connections(context)}


@router.post(C + "/connections/{connection_id}/revoke")
def revoke_connection(
    connection_id: UUID, body: VersionCommand, context: Context, store: Store, key: Key
) -> dict[str, Any]:
    def write(connection: Any) -> dict[str, Any]:
        row = connection.execute(
            "select app.revoke_alto_connection(%s,%s,%s) as result",
            (context.company_id, connection_id, body.expected_row_version),
        ).fetchone()
        return dict(row["result"])

    store.command(
        context,
        name=f"connection-revoke:{connection_id}",
        key=key,
        body=body.model_dump(),
        operation=write,
    )
    return {"connections": store.connections(context)}


@router.get(C + "/demo/runs")
def demo_runs(context: Context, store: Store) -> dict[str, Any]:
    return store.demo_runs(context)


@router.post(C + "/demo/quickstart", response_model=DemoQuickstartResponse)
def quickstart(
    body: DemoQuickstartRequest,
    context: Context,
    store: Store,
    key: Key,
    settings: Annotated[Settings, Depends(get_settings)],
) -> DemoQuickstartResponse:
    if not settings.hackathon_demo or not context.actor.is_anonymous:
        raise HTTPException(status_code=403, detail="hackathon quickstart is unavailable")
    try:
        return store.quickstart(context, body.preferred_actor_key, key)
    except DemoAiUnavailableError as error:
        raise HTTPException(
            status_code=503,
            detail="Demo AI is temporarily unavailable. Retry shortly.",
        ) from error


@router.post(C + "/demo/runs")
def create_run(body: CreateRun, context: Context, store: Store, key: Key) -> dict[str, str]:
    return store.create_run(context, body.mode, body.parent_run_id, key)


def fork_owned_run(
    run_id: UUID,
    context: CompanyContext,
    store: PostgresWorkspaceStore,
    key: str,
    archive_version: int | None = None,
) -> dict[str, Any]:
    # Administrative run management is about the real visitor, not an impersonated
    # synthetic employee. Keep its receipt outside the run being archived.
    owner = replace(
        context, demo_run_id=None, demo_actor_session_id=None, simulated_employee_id=None
    )

    def write(connection: Any) -> dict[str, Any]:
        old = connection.execute(
            "select mode from app.demo_runs where company_id=%s and id=%s",
            (owner.company_id, run_id),
        ).fetchone()
        if old is None:
            raise HTTPException(status_code=404, detail="run was not found")
        row = connection.execute(
            "select app.fork_demo_run(%s,%s,%s,%s) as id",
            (owner.company_id, old["mode"], run_id, key),
        ).fetchone()
        if archive_version is not None:
            connection.execute(
                "select app.archive_demo_run(%s,%s,%s)", (owner.company_id, run_id, archive_version)
            )
        return {
            "id": str(row["id"]),
            "archived_run_id": str(run_id) if archive_version is not None else None,
        }

    return store.command(
        owner,
        name="demo-archive-reset" if archive_version is not None else "demo-fork",
        key=key,
        body={"run_id": str(run_id), "expected_row_version": archive_version},
        operation=write,
    )


@router.post(C + "/demo/runs/{run_id}/fork")
def fork_run(run_id: UUID, context: Context, store: Store, key: Key) -> dict[str, Any]:
    return fork_owned_run(run_id, context, store, key)


@router.post(C + "/demo/runs/{run_id}/archive-reset")
def archive_reset(
    run_id: UUID, body: VersionCommand, context: Context, store: Store, key: Key
) -> dict[str, Any]:
    return fork_owned_run(run_id, context, store, key, body.expected_row_version)


@router.post(C + "/demo/runs/{run_id}/actor-sessions/{session_id}/end")
def end_actor(
    run_id: UUID, session_id: UUID, context: Context, store: Store, key: Key
) -> dict[str, Any]:
    with store.transaction(context, "demo:end-actor") as connection:
        selected = connection.execute(
            "select id from app.demo_actor_sessions where company_id=%s and run_id=%s and id=%s",
            (context.company_id, run_id, session_id),
        ).fetchone()
        if selected is None:
            raise HTTPException(status_code=404, detail="actor session was not found")
        connection.execute(
            "select app.end_demo_actor_session(%s,%s)", (context.company_id, session_id)
        )
    return {"run_id": str(run_id), "actor_session_id": None}


@router.post(C + "/demo/runs/{run_id}/actor-sessions")
def select_actor(
    run_id: UUID, body: SelectActor, context: Context, store: Store, key: Key
) -> dict[str, str]:
    return store.select_actor(context, run_id, body.employee_id, key)


@router.post(C + "/demo/runs/{run_id}/clock")
def advance_clock(
    run_id: UUID, body: AdvanceClock, context: Context, store: Store, key: Key
) -> dict[str, Any]:
    return store.advance_clock(context, run_id, body.expected_clock_version, body.clock_at, key)


@router.post(C + "/demo/runs/{run_id}/launch-request")
def launch_request(
    run_id: UUID,
    context: Context,
    store: Store,
    key: Key,
    limiter: DemoAiCommandLimiterDependency,
) -> dict[str, Any]:
    from coordination.workspace.northstar import create_northstar_request

    admit_demo_ai_command(limiter, context, key)
    return create_northstar_request(
        store=store, context=context, run_id=run_id, idempotency_key=key
    )


@router.post(C + "/files/{file_id}/finalize")
def finalize_upload(
    file_id: UUID, body: FinalizeUpload, context: Context, store: Store, key: Key
) -> dict[str, Any]:
    return commands.finalize_upload(store, context, file_id, body.size_bytes, key)


@router.get(C + "/files/{file_id}")
def file_status(file_id: UUID, context: Context, store: Store) -> dict[str, Any]:
    return commands.file_status(store, context, file_id)


@router.post(C + "/voice/transcriptions")
def start_transcription(
    body: VoiceRequest,
    context: Context,
    store: Store,
    key: Key,
    limiter: DemoAiCommandLimiterDependency,
) -> dict[str, Any]:
    admit_demo_ai_command(limiter, context, key)
    return commands.start_transcription(store, context, body, key)


@router.get(C + "/voice/transcriptions/{job_id}")
def transcription(job_id: UUID, context: Context, store: Store) -> dict[str, Any]:
    return commands.transcription(store, context, job_id)


@router.post(C + "/me/feedback")
def feedback(
    body: FeedbackRequest,
    context: Context,
    store: Store,
    key: Key,
    limiter: DemoAiCommandLimiterDependency,
) -> dict[str, Any]:
    if body.suggest_preference:
        admit_demo_ai_command(limiter, context, key)
    return commands.record_feedback(store, context, body, key)


@router.post(C + "/me/employee-preferences")
def new_preference(body: NewPreference, context: Context, store: Store, key: Key) -> dict[str, Any]:
    receipt = commands.create_preference(store, context, body.text, key)
    return {**receipt, "preferences": interactions.employee_preferences(store, context)}


@router.get(C + "/tasks/{task_id}")
def task_detail(task_id: UUID, context: Context, store: Store) -> dict[str, Any]:
    return interactions.task_detail(store, context, task_id)


@router.post(C + "/tasks/{task_id}/approve-gate")
def approve_gate(
    task_id: UUID, body: GateApproval, context: Context, store: Store, key: Key
) -> dict[str, Any]:
    def write(connection: Any) -> dict[str, Any]:
        row = connection.execute(
            "select app.approve_alto_gate(%s,%s,%s,%s,%s,%s,%s) as result",
            (
                context.company_id,
                task_id,
                body.expected_row_version,
                body.required_submission_id,
                bytes.fromhex(body.required_submission_digest)
                if body.required_submission_digest
                else None,
                key,
                uuid4(),
            ),
        ).fetchone()
        return dict(row["result"])

    store.command(
        context, name=f"gate-approval:{task_id}", key=key, body=body.model_dump(), operation=write
    )
    return interactions.task_detail(store, context, task_id)


@router.get(C + "/sources/{source_version_id}")
def source_version(source_version_id: UUID, context: Context, store: Store) -> dict[str, Any]:
    with store.transaction(context, "source:excerpt") as connection:
        source = connection.execute(
            """select v.id,s.title,s.current_version_id=v.id as
            is_current,v.retrieved_at,v.expires_at
          from app.source_versions v join app.source_records s on s.company_id=v.company_id and
          s.id=v.source_id
          where v.company_id=%s and v.id=%s and
          app.can_read_source(app.current_actor_id(),s.company_id,s.id)""",
            (context.company_id, source_version_id),
        ).fetchone()
        if source is None:
            raise HTTPException(status_code=404, detail="source was not found")
        excerpts = connection.execute(
            "select locator,permitted_text as text from app.source_excerpts where company_id=%s "
            "and source_version_id=%s order by locator limit 50",
            (context.company_id, source_version_id),
        ).fetchall()
        return {**dict(source), "excerpts": [dict(row) for row in excerpts]}


@router.patch(C + "/tasks/{task_id}/draft")
def save_draft(
    task_id: UUID, body: DraftUpdate, context: Context, store: Store, key: Key
) -> dict[str, Any]:
    return interactions.save_draft(store, context, task_id, body, key)


@router.get(C + "/me/employee-preferences")
def employee_preferences(context: Context, store: Store) -> dict[str, Any]:
    return {"preferences": interactions.employee_preferences(store, context)}


@router.get(C + "/employee-preferences/{preference_id}")
def shared_preference(preference_id: UUID, context: Context, store: Store) -> dict[str, Any]:
    with store.transaction(context, "preference:current-consent") as connection:
        row = connection.execute(
            """select p.id,p.employee_id,p.version,p.text,p.created_at,e.display_name,
          exists(select 1 from app.employee_preference_versions child where
          child.company_id=p.company_id
            and child.parent_version_id=p.id) as superseded
          from app.employee_preference_versions p join app.employee_profiles e on
          e.company_id=p.company_id and e.id=p.employee_id
          where p.company_id=%s and p.id=%s and app.can_read_preference(p.company_id,p.id)""",
            (context.company_id, preference_id),
        ).fetchone()
        if row is None:
            raise HTTPException(
                status_code=404, detail="preference is no longer shared with this viewer"
            )
        return dict(row)


@router.patch(C + "/me/employee-preferences/{preference_id}")
def edit_preference(
    preference_id: UUID, body: PreferenceUpdate, context: Context, store: Store, key: Key
) -> dict[str, Any]:
    return interactions.edit_preference(store, context, preference_id, body, key)


@router.post(C + "/me/employee-preferences/{preference_id}/share")
def share_preference(
    preference_id: UUID, body: PreferenceDecision, context: Context, store: Store, key: Key
) -> dict[str, Any]:
    return interactions.decide_preference(store, context, preference_id, body, "share", key)


@router.post(C + "/me/employee-preferences/{preference_id}/keep-private")
def keep_preference(
    preference_id: UUID, body: PreferenceDecision, context: Context, store: Store, key: Key
) -> dict[str, Any]:
    return interactions.decide_preference(store, context, preference_id, body, "keep_private", key)


@router.post(C + "/me/employee-preferences/{preference_id}/revoke")
def revoke_preference(
    preference_id: UUID, body: PreferenceDecision, context: Context, store: Store, key: Key
) -> dict[str, Any]:
    return interactions.decide_preference(store, context, preference_id, body, "revoke", key)


@router.post(C + "/assistant/threads")
def create_thread(body: CreateThread, context: Context, store: Store, key: Key) -> dict[str, Any]:
    return interactions.create_thread(store, context, body.context, key)


@router.get(C + "/assistant/threads/{thread_id}")
def get_thread(thread_id: UUID, context: Context, store: Store) -> dict[str, Any]:
    return interactions.get_thread(store, context, thread_id)


@router.post(C + "/assistant/threads/{thread_id}/messages")
def send_message(
    thread_id: UUID,
    body: AssistantTurn,
    context: Context,
    store: Store,
    key: Key,
    limiter: DemoAiCommandLimiterDependency,
) -> dict[str, Any]:
    admit_demo_ai_command(limiter, context, key)
    return interactions.send_message(store, context, thread_id, body.content, body.context, key)


@router.post(C + "/assistant/threads/{thread_id}/actions/{action_id}/decision")
def decide_assistant_action(
    thread_id: UUID,
    action_id: UUID,
    body: AssistantActionDecision,
    context: Context,
    store: Store,
    key: Key,
    limiter: DemoAiCommandLimiterDependency,
) -> dict[str, Any]:
    return interactions.decide_action(
        store,
        context,
        thread_id,
        action_id,
        body,
        key,
        before_ai_command=lambda: admit_demo_ai_command(limiter, context, key),
    )


@router.post(C + "/assistant/threads/{thread_id}/cancel")
def cancel_thread(
    thread_id: UUID, body: CancelThread, context: Context, store: Store, key: Key
) -> dict[str, Any]:
    current = interactions.get_thread(store, context, thread_id)
    if current["status"] != body.expected_status:
        raise HTTPException(status_code=409, detail="assistant operation state changed")
    with store.transaction(context, "assistant:cancel") as connection:
        connection.execute(
            "select app.cancel_alto_assistant(%s,%s,%s)", (context.company_id, thread_id, key)
        )
    return interactions.get_thread(store, context, thread_id)
