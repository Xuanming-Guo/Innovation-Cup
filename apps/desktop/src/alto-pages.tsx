import { useState } from "react";
import { altoRequest, safeTarget, type AltoApiContext, type HomeData, type Project, type ActionItem, type EmployeePreference, type WorkspaceBootstrap, type NotificationItem, type DemoData, type DemoRun } from "./alto-api";
import { Assistant, type GuidedAssistantPrompt } from "./alto-assistant";
import { Badge, EmptyState, ErrorNotice, Icon, IconButton, Loading, Modal, PageHeading } from "./alto-ui";
import { dateTime, formatDate, humanize, navigate, useCommand, useResource } from "./alto-state";
function notificationTarget(item: NotificationItem): string {
    if (item.target_path) return safeTarget(item.target_path, "/notifications");
    if (item.subject_type.includes("preference")) return `/preferences/${item.subject_id}`;
    if (item.subject_type === "task" || item.subject_type === "work_item") return `/tasks/${item.subject_id}`;
    if (item.subject_type === "submission") return `/reviews/${item.subject_id}`;
    if (item.subject_type === "plan") return `/plan-review?plan=${item.subject_id}`;
    if (item.subject_type === "planning_request") return `/plan-review?request=${item.subject_id}`;
    return "/notifications";
}
export function ProjectRow({ project }: {
    project: Project;
}) {
    const completed = project.status === "completed" || project.status === "accepted";
    return <button className="alto-project-row" onClick={() => navigate(`/projects/${project.id}/graph`)}>
<span className={`alto-status-dot ${completed ? "accepted" : project.status.includes("approval") ? "pending" : "active"}`}/>
<div>
<strong>{project.title}</strong>
<p>{completed ? `Accepted ${formatDate(project.accepted_at)}${project.accepted_by ? ` · ${project.accepted_by}` : ""}` : `${humanize(project.status)}${project.deadline ? ` · Due ${dateTime(project.deadline)}` : ""}`}</p>
</div>
<Icon name="right"/>
</button>;
}
export function PreferenceConsentCard({ preference, api, onClose, onSaved }: {
    preference: EmployeePreference;
    api: AltoApiContext;
    onClose: () => void;
    onSaved: () => void;
}) {
    const [editing, setEditing] = useState(false);
    const [text, setText] = useState(preference.text);
    const command = useCommand();
    async function decide(action: "share" | "keep-private" | "revoke") {
        await altoRequest(api, `/me/employee-preferences/${preference.id}/${action}`, { method: "POST", body: { expected_row_version: preference.row_version, ...(action === "share" ? { manager_id: preference.manager_id } : {}) } });
        onSaved();
        onClose();
    }
    return <aside className="alto-notice-card" aria-label="Private preference consent">
<header>
<Icon name="lock"/>
<div>
<h3>A question for you</h3>
<span>Private to you</span>
</div>
<IconButton icon="close" label="Close without sharing" onClick={onClose}/>
</header>
    {editing ? <label className="alto-field">Your preference<textarea value={text} maxLength={1000} onChange={(event) => setText(event.target.value)} rows={4}/>
</label> : <p>{preference.text}</p>}
    <p>{preference.status === "shared" ? `Shared with ${preference.manager_name ?? "your selected manager"}. You can revoke future access.` : `Share this preference with ${preference.manager_name ?? "a permitted manager"}?`}</p>
    <div className="alto-button-row">
      {editing ? <button className="alto-primary" disabled={command.busy || !text.trim()} onClick={() => void command.run(async () => { await altoRequest(api, `/me/employee-preferences/${preference.id}`, { method: "PATCH", body: { text: text.trim(), expected_row_version: preference.row_version } }); setEditing(false); onSaved(); })}>Save private draft</button>
            : preference.status === "shared" ? <button className="alto-primary" disabled={command.busy} onClick={() => void command.run(() => decide("revoke"))}>Revoke sharing</button>
                : <button className="alto-primary" title={preference.manager_id ? undefined : "No permitted manager is available"} disabled={command.busy || !preference.manager_id} onClick={() => void command.run(() => decide("share"))}>Share with {preference.manager_name ?? "manager"}</button>}
      {preference.status !== "shared" && <button className="alto-secondary" disabled={command.busy} onClick={() => void command.run(() => decide("keep-private"))}>Keep private</button>}
      <button className="alto-secondary" disabled={command.busy} onClick={() => setEditing(!editing)}>{editing ? "Cancel edit" : "Edit"}</button>
    </div>
<small>Only the exact preference you approve will be shared. Closing is not consent.</small>
<ErrorNotice error={command.error}/>
  </aside>;
}
export function HomeView({ api, workspace, onStartPlanning, threadId, guidedPrompt, guidedLaunch }: {
    api?: AltoApiContext;
    workspace: WorkspaceBootstrap | null;
    onStartPlanning?: (text: string) => void;
    threadId?: string | null;
    guidedPrompt?: GuidedAssistantPrompt;
    guidedLaunch?: { idempotencyKey: string; onSuccess: (requestId: string) => void };
}) {
    const home = useResource<HomeData>(api, "/home");
    const preferences = useResource<{
        preferences: EmployeePreference[];
    }>(api, workspace?.viewer.role === "employee" ? "/me/employee-preferences" : null);
    const [dismissed, setDismissed] = useState<string | null>(null);
    const employee = workspace?.viewer.role === "employee";
    const setupNeeded = workspace?.company.is_demo && (!workspace.demo_run || !workspace.demo_run.actor_name);
    const provider = useResource<{ current_profile_version_id?: string | null; management_mode?: string; status?: string }>(api,
      !employee && workspace?.company.is_demo && workspace.demo_run?.mode === "live" ? "/ai-provider/demo-binding" : null);
    const providerConfigured = provider.data?.management_mode === "operator_managed"
      ? provider.data.status === "configured"
      : Boolean(provider.data?.current_profile_version_id);
    const providerNeeded = workspace?.demo_run?.mode === "live" && !providerConfigured;
    const planningReady = workspace?.viewer.role === "manager" && !setupNeeded && !providerNeeded && !provider.error;
    const launch = useCommand();
    const now = workspace?.demo_run?.clock_at ?? new Date().toISOString();
    const firstName = workspace?.viewer.display_name.split(" ")[0];
    const greeting = new Date(now).getHours() < 12 ? "Good morning" : "Good afternoon";
    const pendingPreference = preferences.data?.preferences.find((item) => item.status === "draft" && item.id !== dismissed);
    return <div className={`alto-home alto-composer-page ${employee ? "alto-employee-home" : "alto-manager-home"}`}>
    <PageHeading eyebrow={formatDate(now, { weekday: "long", month: "long", day: "numeric" })} title={`${greeting}${firstName ? `, ${firstName}` : ""}`} subtitle={employee ? "Here’s what’s happening with your work." : "Your team’s commitments, thoughtfully coordinated by ALTO"}/>
    {setupNeeded && <div className="alto-info-banner"><strong>Choose how you want to explore ALTO.</strong><p>Start as a manager to plan work, or as an employee to see assignments. Your real account permissions stay unchanged.</p><button className="alto-primary" onClick={() => navigate("/settings/demo")}>Choose my demo role</button></div>}
    {!employee && !setupNeeded && providerNeeded && !provider.loading && <div className="alto-info-banner">Your Live workspace needs an AI credential bound before planning.<button className="alto-text-button" onClick={() => navigate("/settings/ai")}>Connect AI</button></div>}
    <ErrorNotice error={provider.error} retry={provider.refresh}/>
    {pendingPreference && api && <PreferenceConsentCard api={api} preference={pendingPreference} onClose={() => setDismissed(pendingPreference.id)} onSaved={preferences.refresh}/>}
    {home.loading && <Loading />}
    <ErrorNotice error={home.error} retry={home.refresh}/>
    <div className="alto-home-columns">
      <section>
<h2>{employee && <span className="alto-category-icon mint">
<Icon name="document"/>
</span>}Recently assigned</h2>
        {employee ? home.data?.tasks.filter((task) => !["submitted", "accepted"].includes(task.status)).slice(0, 4).map((task) => <button className="alto-home-item" key={task.task_id} onClick={() => navigate(`/tasks/${task.task_id}`)}>
<span className="alto-status-dot active"/>
<span>{task.title}<small>{humanize(task.status)}</small>
</span>
</button>)
            : home.data?.recent_projects.slice(0, 4).map((project) => <button className="alto-home-item" key={project.id} onClick={() => navigate(`/projects/${project.id}/graph`)}>
<span className="alto-status-dot active"/>
<span>{project.title}<small>{humanize(project.status)}</small>
</span>
</button>)}
        {!home.loading && (!home.data || (employee ? !home.data.tasks.some((task) => !["submitted", "accepted"].includes(task.status)) : home.data.recent_projects.length === 0)) && <p className="alto-muted">No assigned work yet.</p>}
      </section>
      <section>
<h2>{employee && <span className="alto-category-icon mint">
<Icon name="check"/>
</span>}Recently completed</h2>
        {home.data?.completed_projects.slice(0, 4).map((project) => <button className="alto-home-item" key={project.id} onClick={() => navigate(`/projects/${project.id}/graph`)}>
<span className="alto-status-dot accepted"/>
<span>{project.title}<small>Accepted {formatDate(project.accepted_at)}{project.accepted_by ? ` · ${project.accepted_by}` : ""}</small>
</span>
</button>)}
        {!home.loading && !home.data?.completed_projects.length && <p className="alto-muted">Accepted work will appear here.</p>}
      </section>
      <section>
<h2>{employee && <span className="alto-category-icon rose">
<Icon name="people"/>
</span>}{employee ? "Awaiting review" : "Awaiting plans"}</h2>
        {employee ? home.data?.tasks.filter((task) => task.status === "submitted").slice(0, 4).map((task) => <button className="alto-home-item" key={task.task_id} onClick={() => navigate(`/tasks/${task.task_id}`)}>
<span className="alto-status-dot pending"/>
<span>{task.title}<small>Submitted · reviewer acceptance pending</small>
</span>
</button>) : home.data?.actions.slice(0, 4).map((action) => <button className="alto-home-item" key={action.id} onClick={() => navigate(safeTarget(action.target_path, "/actions"))}>
<span className="alto-status-dot pending"/>
<span>{action.title}<small>{humanize(action.status)}</small>
</span>
</button>)}
        {!home.loading && (!home.data || (employee ? !home.data.tasks.some((task) => task.status === "submitted") : home.data.actions.length === 0)) && <p className="alto-muted">All clear for now.</p>}
      </section>
    </div>
    {!api && <div className="alto-inline-hint">Sign in to load your authorised workspace. No company data is stored in this screen.</div>}
    {workspace?.company.is_demo && employee && !home.data?.tasks.length && <p className="alto-info-banner">No tasks have been assigned in this demo workspace yet. A manager needs to approve and apply a plan first.<button className="alto-text-button" onClick={() => navigate("/settings/demo")}>Switch demo role</button></p>}
    <div className="alto-home-composer">
<Assistant key={guidedPrompt ? `guided:${guidedPrompt.messageCommandKey}` : threadId ?? "home-composer"} api={api} initialThreadId={guidedPrompt?.threadId ?? threadId} onThreadChange={guidedPrompt ? undefined : (id) => navigate(`/home?thread=${encodeURIComponent(id)}`)} guidedPrompt={guidedPrompt} onPlanRequest={!employee && planningReady ? onStartPlanning : undefined} voiceEnabled={workspace?.capabilities.includes("voice.transcribe")} placeholder={employee ? "What would you like help with?" : "What would you like to coordinate?"}/>
      {!employee && <div className="alto-suggestions">
{workspace?.demo_run && <button data-onboarding-target={guidedLaunch ? "launch" : undefined} disabled={!api || !planningReady || launch.busy} onClick={() => void launch.run(async () => { if (!api || !workspace.demo_run) return; const created = await altoRequest<{request_id: string}>(api, `/demo/runs/${workspace.demo_run.id}/launch-request`, { method: "POST", body: {}, ...(guidedLaunch ? { idempotencyKey: guidedLaunch.idempotencyKey } : {}) }); guidedLaunch?.onSuccess(created.request_id); navigate(`/home?request=${encodeURIComponent(created.request_id)}`); })}>{launch.busy ? "Preparing your request…" : "Prepare the Northstar launch plan"}</button>}
<button onClick={() => navigate("/plan-review")}>Continue a planning request</button>
<button onClick={() => navigate("/calendar")}>Show this week’s commitments</button>
</div>}
<ErrorNotice error={launch.error}/>
    </div>
  </div>;
}
export function ProjectsView({ api, employee = false, completedInitially = false }: {
    api?: AltoApiContext;
    employee?: boolean;
    completedInitially?: boolean;
}) {
    const resource = useResource<{
        projects: Project[];
    }>(api, "/projects");
    const [completed, setCompleted] = useState(completedInitially);
    const [search, setSearch] = useState("");
    const projects = resource.data?.projects.filter((project) => (project.status === "completed" || project.status === "accepted") === completed && project.title.toLowerCase().includes(search.toLowerCase())) ?? [];
    return <div className="alto-composer-page">
<PageHeading title={employee ? "My projects" : "Projects"} subtitle="Your team’s work, in one place."/>
<div className="alto-list-toolbar">
<div className="alto-tabs" role="tablist" aria-label="Project status">
<button role="tab" aria-selected={!completed} className={!completed ? "active" : ""} onClick={() => setCompleted(false)}>Ongoing</button>
<button role="tab" aria-selected={completed} className={completed ? "active" : ""} onClick={() => setCompleted(true)}>Completed</button>
</div>
<label className="alto-search">
<Icon name="search"/>
<input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search projects…" aria-label="Search projects"/>
</label>
</div>
    {resource.loading && <Loading />}<ErrorNotice error={resource.error} retry={resource.refresh}/>
<div className="alto-project-list">{projects.map((project) => <ProjectRow project={project} key={project.id}/>)}</div>
    {!resource.loading && !resource.error && !projects.length && <EmptyState title={search ? "No matching projects" : completed ? "No accepted projects yet" : "No projects yet"}>{search ? "Try another project name." : completed ? "Projects appear here only after their final acceptance gate." : "Your authorised projects will appear here."}</EmptyState>}
    <Assistant api={api} placeholder="Ask ALTO about your projects…"/>
  </div>;
}
export function ActionsView({ api }: {
    api?: AltoApiContext;
}) {
    const resource = useResource<{
        actions: ActionItem[];
    }>(api, "/manager/actions");
    const [filter, setFilter] = useState("all");
    const actions = resource.data?.actions.filter((action) => filter === "all" || action.kind === filter) ?? [];
    const kinds = Array.from(new Set(resource.data?.actions.map((action) => action.kind) ?? []));
    return <div>
<PageHeading title="Needs your attention" subtitle="Clarifications, exact-plan approvals and authorised reviews."/>
<div className="alto-tabs">
<button className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>All actions</button>{kinds.map((kind) => <button key={kind} className={filter === kind ? "active" : ""} onClick={() => setFilter(kind)}>{humanize(kind)}</button>)}</div>{resource.loading && <Loading />}<ErrorNotice error={resource.error} retry={resource.refresh}/>{actions.map((action) => <button key={action.id} className="alto-project-row" onClick={() => navigate(safeTarget(action.target_path, "/plan-review"))}>
<Icon name="document"/>
<div>
<strong>{action.title}</strong>
<p>{action.detail ?? humanize(action.status)}</p>
</div>
<Icon name="right"/>
</button>)}{!resource.loading && !resource.error && !actions.length && <EmptyState title="All clear for now">There are no authorised pending actions in this view.</EmptyState>}</div>;
}
export function NotificationsView({ api, compact = false, onClose }: {
    api?: AltoApiContext;
    compact?: boolean;
    onClose?: () => void;
}) {
    const resource = useResource<{
        notifications: NotificationItem[];
    }>(api, "/me/notifications");
    const command = useCommand();
    return <section className={compact ? "alto-notification-popover" : ""} aria-label="Notifications">
<header className="alto-notification-heading">
<h2>Notifications</h2>{compact && onClose && <IconButton icon="close" label="Close notifications" onClick={onClose}/>}</header>{resource.loading && <Loading />}<ErrorNotice error={resource.error ?? command.error} retry={resource.refresh}/>{resource.data?.notifications.map((item) => <article className={`alto-notification-row ${item.seen_at ? "seen" : ""}`} key={item.notification_id}>
<Icon name={(item.kind ?? item.message_key).includes("preference") ? "people" : "bell"}/>
<div>
<strong>{item.title ?? humanize(item.kind ?? item.message_key)}</strong>{item.body && <p>{item.body}</p>}<small>{dateTime(item.created_at)}</small>
<div className="alto-button-row"><button className="alto-text-button" onClick={() => { navigate(notificationTarget(item)); onClose?.(); }}>View details</button>{!item.seen_at && <button className="alto-text-button" disabled={command.busy} onClick={() => void command.run(async () => { if (!api)
        return; await altoRequest(api, `/me/notifications/${item.notification_id}/seen`, { method: "POST", body: {} }); resource.refresh(); })}>Dismiss</button>}</div>
</div>
</article>)}{!resource.loading && !resource.error && !resource.data?.notifications.length && <EmptyState title="You’re all caught up">Notifications appear when there is something for you to see.</EmptyState>}{compact && <button className="alto-text-button" onClick={() => { navigate("/notifications"); onClose?.(); }}>Open notification inbox</button>}</section>;
}
export function SimulationView({ api, workspace, onSelectRun }: {
    api: AltoApiContext;
    workspace: WorkspaceBootstrap;
    onSelectRun: (runId?: string, actorSessionId?: string) => void;
}) {
    const resource = useResource<DemoData>(api, "/demo/runs");
    const command = useCommand();
    const [mode, setMode] = useState("authored_replay");
    const [actor, setActor] = useState("");
    const [clock, setClock] = useState("");
    const [reset, setReset] = useState(false);
    const active = resource.data?.runs.find((run) => run.id === workspace.demo_run?.id);
    return <div>
<PageHeading title="Simulation" subtitle="A clearly labelled, isolated Northstar run. Clock changes never complete work."/>
<div className="alto-info-banner">
<Icon name="info"/>Synthetic company · Demo data. Your real identity remains recorded for every action.</div>
<ErrorNotice error={resource.error ?? command.error} retry={resource.refresh}/>{resource.loading && <Loading />}
    <section className="alto-settings-section">
<h2>Create a run</h2>
<label className="alto-field">Execution mode<select value={mode} onChange={(event) => setMode(event.target.value)}>
<option value="authored_replay">Authored replay — no live model claims</option>
<option value="live">Live — requires your provider profile</option>
<option value="authored_d0_check">Authored D0 check</option>
</select>
</label>
<button className="alto-primary" disabled={command.busy || !resource.data?.can_create} onClick={() => void command.run(async () => { const result = await altoRequest<DemoRun>({ ...api, demoRunId: undefined, demoActorSessionId: undefined }, "/demo/runs", { method: "POST", body: { mode } }); onSelectRun(result.id); resource.refresh(); })}>Create isolated run</button>
</section>
    <section className="alto-settings-section">
<h2>Your runs</h2>{resource.data?.runs.map((run) => <div className="alto-project-row" key={run.id}>
<div>
<strong>{run.name}</strong>
<p>{humanize(run.mode)} · {dateTime(run.clock_at)} · {humanize(run.status)}{run.protected ? " · Protected" : ""}</p>
</div>
<button className="alto-secondary" disabled={run.status === "archived"} onClick={() => onSelectRun(run.id)}>{run.id === active?.id ? "Selected" : "Open run"}</button>
</div>)}{!resource.loading && !resource.data?.runs.length && <p>No demo runs yet. Create one above.</p>}</section>
    {active && <section className="alto-settings-section">
<h2>Current run</h2>
<Badge tone="pending">{humanize(active.mode)}</Badge>
<p>Scenario time: {dateTime(active.clock_at)}. This does not change the real audit clock.</p>
<div className="alto-button-row">
<button className="alto-secondary" disabled={command.busy} onClick={() => void command.run(async () => { const next = await altoRequest<DemoRun>({ ...api, demoRunId: undefined, demoActorSessionId: undefined }, `/demo/runs/${active.id}/fork`, { method: "POST", body: {} }); onSelectRun(next.id); resource.refresh(); })}>Fork run</button>
<button className="alto-secondary" disabled={command.busy || active.protected} title={active.protected ? "Protected runs cannot be reset here" : undefined} onClick={() => setReset(true)}>Archive and reset</button>
<button className="alto-text-button" onClick={() => onSelectRun()}>Leave run</button>
</div>
      <label className="alto-field">Scenario clock (your local time)<input type="datetime-local" value={clock} onChange={(event) => setClock(event.target.value)}/>
</label>
<button className="alto-secondary" disabled={command.busy || !clock} onClick={() => void command.run(async () => { await altoRequest(api, `/demo/runs/${active.id}/clock`, { method: "POST", body: { clock_at: new Date(clock).toISOString(), expected_clock_version: active.clock_version } }); resource.refresh(); onSelectRun(active.id, api.demoActorSessionId); })}>Advance clock only</button>
      <label className="alto-field">Explicit demo actor<select value={actor} onChange={(event) => setActor(event.target.value)}>
<option value="">Select a permitted actor</option>{resource.data?.actors.map((person) => <option value={person.id} key={person.id}>{person.display_name} · {person.job_title}</option>)}</select>
</label>
<div className="alto-button-row">
<button className="alto-primary" disabled={!actor || command.busy} onClick={() => void command.run(async () => { const result = await altoRequest<{
            actor_session_id: string;
        }>(api, `/demo/runs/${active.id}/actor-sessions`, { method: "POST", body: { employee_id: actor } }); onSelectRun(active.id, result.actor_session_id); })}>Start labelled actor session</button>{api.demoActorSessionId && <button className="alto-secondary" disabled={command.busy} onClick={() => void command.run(async () => { await altoRequest({ ...api, demoRunId: undefined, demoActorSessionId: undefined }, `/demo/runs/${active.id}/actor-sessions/${api.demoActorSessionId}/end`, { method: "POST", body: {} }); onSelectRun(active.id); })}>End actor session</button>}</div>
<div className="alto-settings-section"><h3>Northstar launch</h3><p>Create the canonical launch request with the run’s authoritative source versions. Authored replay remains visibly labelled; live mode uses your explicitly bound provider.</p><button className="alto-primary" disabled={command.busy || workspace.viewer.role !== "manager"} onClick={() => void command.run(async () => { const created = await altoRequest<{ request_id: string }>(api, `/demo/runs/${active.id}/launch-request`, { method: "POST", body: {} }); navigate(`/plan-review?request=${created.request_id}`); })}>Prepare the Northstar launch plan</button></div>
    </section>}
    {reset && active && <Modal title="Archive this run and start again?" onClose={() => setReset(false)}>
<p>The old run and its audit history will be preserved. Other visitors’ runs are unaffected.</p>
<button className="alto-primary" disabled={command.busy} onClick={() => void command.run(async () => { const next = await altoRequest<DemoRun>({ ...api, demoRunId: undefined, demoActorSessionId: undefined }, `/demo/runs/${active.id}/archive-reset`, { method: "POST", body: { expected_row_version: active.row_version } }); setReset(false); onSelectRun(next.id); resource.refresh(); })}>Archive and create a new run</button>
<ErrorNotice error={command.error}/>
</Modal>}
  </div>;
}
