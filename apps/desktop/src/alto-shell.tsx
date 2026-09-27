import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import type { AuthorisedSessionController, AuthorisedSessionState } from "./authorised-session";
import { AltoApiError, altoRequest, defaultPreferences, type AltoApiContext, type DemoQuickstart, type WorkspaceBootstrap, type WorkspacePreferences } from "./alto-api";
import { Assistant, type GuidedAssistantPrompt } from "./alto-assistant";
import { AuthView } from "./alto-auth";
import { CalendarView, PeopleDirectory, PersonProfile } from "./alto-calendar-profile";
import { ProjectGraph } from "./alto-graph";
import { ActionsView, HomeView, NotificationsView, ProjectsView, SimulationView } from "./alto-pages";
import { AboutView, ConnectionsView, DemoProviderSettings, SettingsTabs, WorkspaceSettings } from "./alto-settings";
import { TaskBrief } from "./alto-task";
import { SharedPreference, SourceEvidence, SubmissionReview } from "./alto-evidence";
import { AltoLogo, Badge, EmptyState, ErrorNotice, Icon, IconButton, Loading, PageHeading, type IconName } from "./alto-ui";
import { initials, humanize, navigate, useRoute, useResource, useResourceActivity } from "./alto-state";
import { CompanyConnections } from "./company-connections";
import { DeploymentSettings } from "./deployment-settings";
import { EmployeeWorkspace } from "./employee-workspace";
import { PlanReviewWorkspace } from "./plan-review";
import { PlanningConversation } from "./planning-conversation";
import { invalidateAltoResourceCache } from "./alto-resource-cache";
import { DemoSetup } from "./alto-demo-setup";
import type { PublicRuntimeConfig, PublicRuntimeConfigInput } from "./runtime-config";
import type { ServiceStatus } from "./service-status";
import { MayaOnboardingCoachmark } from "./maya-onboarding";
import { MAYA_ONBOARDING_PROMPT, freshMayaOnboarding, mayaOnboardingRoute, readMayaOnboarding, retryMayaQuestion, writeMayaOnboarding, type MayaOnboardingState } from "./maya-onboarding-state";
interface WorkspaceProps {
    config: PublicRuntimeConfig;
    session: AuthorisedSessionState;
    service: ServiceStatus;
    onSignOut: () => Promise<void>;
    saveDeployment: (value: PublicRuntimeConfigInput) => void;
    resetDeployment: () => void;
    authController: RefObject<AuthorisedSessionController | null>;
}
interface Scope {
    run?: string;
    actor?: string;
    actorKey?: string;
}
function readScope(raw: string | null): Scope { try {
    const value: unknown = JSON.parse(raw ?? "{}");
    if (!value || typeof value !== "object")
        return {};
    const row = value as Record<string, unknown>;
    const valid = (id: unknown): id is string => typeof id === "string" && /^[0-9a-f-]{36}$/i.test(id);
    const actorKey = typeof row.actorKey === "string" && /^[a-z][a-z0-9_-]{0,63}$/.test(row.actorKey) ? row.actorKey : undefined;
    return { run: valid(row.run) ? row.run : undefined, actor: valid(row.actor) ? row.actor : undefined, actorKey };
}
catch {
    return {};
} }
export function AltoShell({ config, session, service, onSignOut, saveDeployment, resetDeployment, authController }: WorkspaceProps) {
    const route = useRoute();
    const routeQuery = route.query.toString();
    const scopeKey = session.status === "connected" ? `alto.scope.${session.userId}.${session.api.companyId}` : null;
    const [scope, setScope] = useState<Scope>(() => { try {
        return scopeKey ? readScope(window.localStorage.getItem(scopeKey)) : {};
    }
    catch {
        return {};
    } });
    const sessionUserId = session.status === "connected" ? session.userId : undefined;
    const sessionApiOrigin = session.status === "connected" ? session.api.apiOrigin : undefined;
    const sessionCompanyId = session.status === "connected" ? session.api.companyId : undefined;
    const sessionAccessToken = session.status === "connected" ? session.api.accessToken : undefined;
    const baseApi = useMemo<AltoApiContext | undefined>(() => sessionUserId && sessionApiOrigin && sessionCompanyId && sessionAccessToken
        ? { apiOrigin: sessionApiOrigin, companyId: sessionCompanyId, accessToken: sessionAccessToken, authUserId: sessionUserId }
        : undefined, [sessionAccessToken, sessionApiOrigin, sessionCompanyId, sessionUserId]);
    const scopedApi = useMemo<AltoApiContext | undefined>(() => baseApi ? { ...baseApi, demoRunId: scope.run, demoActorSessionId: scope.actor } : undefined, [baseApi, scope.run, scope.actor]);
    const [quickstart, setQuickstart] = useState<{ status: "loading" | "ready" | "error"; detail?: string; statusCode?: number; providerStatus?: "configured" }>(() => config.hackathonDemo ? { status: "loading" } : { status: "ready" });
    const [quickstartAttempt, setQuickstartAttempt] = useState(0);
    const quickstartIdentity = useRef<string | null>(null);
    const renewalScope = useRef<string | null>(null);
    const api = config.hackathonDemo && quickstart.status !== "ready" ? undefined : scopedApi;
    const bootstrap = useResource<WorkspaceBootstrap>(api, "/workspace");
    const resourceActivity = useResourceActivity(api);
    const settings = useResource<WorkspacePreferences>(api, "/me/preferences");
    const [localPreferences, setLocalPreferences] = useState<WorkspacePreferences | null>(null);
    const preferences = localPreferences ?? settings.data ?? defaultPreferences;
    const reduceMotion = preferences.reduce_motion
        || (typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    const [collapsedOverride, setCollapsedOverride] = useState<boolean | null>(null);
    const collapsed = collapsedOverride ?? (route.path.includes("/graph") || preferences.sidebar_collapsed);
    const [notifications, setNotifications] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [overlayVisible, setOverlayVisible] = useState(true);
    const [planningDraft, setPlanningDraft] = useState<{ scope: string; text: string } | null>(null);
    const [onboarding, setOnboarding] = useState<MayaOnboardingState>(() => readMayaOnboarding());
    const onboardingRef = useRef(onboarding);
    const [onboardingQuestionFailure, setOnboardingQuestionFailure] = useState<string | null>(null);
    const draftScope = `${scopeKey}:${scope.run ?? "real"}:${scope.actor ?? "self"}`;
    const workspace = bootstrap.data;
    const employee = workspace?.viewer.role === "employee" || (workspace === null && session.status === "connected" && session.administrativeRole === "member");
    const isOverlay = route.path === "/assistant/overlay";
    const onboardingEligible = Boolean(
        config.hackathonDemo
        && quickstart.status === "ready"
        && quickstart.providerStatus === "configured"
        && scope.actorKey === "maya"
        && workspace?.viewer.role === "manager"
        && workspace.demo_run?.mode === "live",
    );
    const onboardingActive = onboardingEligible && onboarding.stage !== "complete";
    const commitOnboarding = useCallback((next: MayaOnboardingState) => {
        onboardingRef.current = next;
        writeMayaOnboarding(next);
        setOnboarding(next);
    }, []);
    const guidedStatus = useCallback((result: { state: "waiting" | "completed" | "failed"; error?: string }) => {
        if (result.state === "failed") {
            setOnboardingQuestionFailure(result.error ?? "ALTO could not answer the guided question. Please retry.");
            return;
        }
        setOnboardingQuestionFailure(null);
        if (result.state !== "completed") return;
        const current = onboardingRef.current;
        if (!current.assistantThreadId || !["question_typing", "question_waiting"].includes(current.stage)) return;
        commitOnboarding({ ...current, stage: "question_result" });
    }, [commitOnboarding]);
    const guidedPrompt = useMemo<GuidedAssistantPrompt | undefined>(() => {
        if (!onboardingActive || !onboarding.stage.startsWith("question_")) return undefined;
        const commandKey = onboarding.messageCommandKey;
        return {
            prompt: MAYA_ONBOARDING_PROMPT,
            threadId: onboarding.assistantThreadId,
            threadCommandKey: onboarding.threadCommandKey,
            messageCommandKey: commandKey,
            reduceMotion,
            onThreadCreated: (id) => {
                const current = onboardingRef.current;
                if (current.messageCommandKey !== commandKey || current.assistantThreadId) return;
                commitOnboarding({ ...current, stage: "question_waiting", assistantThreadId: id });
            },
            onStatus: guidedStatus,
        };
    }, [commitOnboarding, guidedStatus, onboarding, onboardingActive, reduceMotion]);
    const guidedLaunch = useMemo(() => onboardingActive && onboarding.stage === "launch" ? {
        idempotencyKey: onboarding.launchCommandKey,
        onSuccess: () => {
            const current = onboardingRef.current;
            if (current.stage === "launch") commitOnboarding({ ...current, stage: "complete" });
        },
    } : undefined, [commitOnboarding, onboarding.launchCommandKey, onboarding.stage, onboardingActive]);
    function startPlanning(text: string) {
        setPlanningDraft({ scope: draftScope, text });
        navigate("/home?compose=plan");
    }
    useEffect(() => { document.title = workspace ? `ALTO · ${workspace.company.name}` : "ALTO"; }, [workspace]);
    useEffect(() => {
        if (!config.hackathonDemo || !baseApi || !scopeKey || !baseApi.authUserId) return;
        const identity = `${baseApi.authUserId}:${quickstartAttempt}`;
        if (quickstartIdentity.current === identity) return;
        quickstartIdentity.current = identity;
        let current = true;
        let settled = false;
        setQuickstart({ status: "loading" });
        void altoRequest<DemoQuickstart>(baseApi, "/demo/quickstart", {
            method: "POST",
            body: { preferred_actor_key: scope.actorKey ?? null },
        }).then((value) => {
            settled = true;
            if (!current) return;
            const next = { run: value.run_id, actor: value.actor_session_id, actorKey: value.actor_key };
            setScope(next);
            try {
                window.localStorage.setItem(scopeKey, JSON.stringify(next));
            } catch { /* Local selectors are a convenience, never authority. */ }
            setQuickstart({ status: "ready", providerStatus: value.provider_status });
            navigate("/home");
        }).catch((value: unknown) => {
            settled = true;
            if (!current) return;
            setQuickstart({
                status: "error",
                detail: value instanceof Error ? value.message : "Demo AI is temporarily unavailable.",
                statusCode: value instanceof AltoApiError ? value.status : undefined,
            });
        });
        return () => {
            current = false;
            if (!settled && quickstartIdentity.current === identity) quickstartIdentity.current = null;
        };
    }, [baseApi, config.hackathonDemo, quickstartAttempt, scope.actorKey, scopeKey]);
    useEffect(() => {
        onboardingRef.current = onboarding;
    }, [onboarding]);
    useEffect(() => {
        if (!onboardingEligible) return;
        writeMayaOnboarding(onboardingRef.current);
        if (!onboardingActive) return;
        const required = mayaOnboardingRoute(onboardingRef.current.stage);
        if (!required) return;
        const hasQuery = routeQuery.length > 0;
        if (route.path !== required || (required === "/home" && hasQuery)) navigate(required);
    }, [onboardingActive, onboardingEligible, onboarding.stage, route.path, routeQuery]);
    useEffect(() => { if (!scopeKey)
        return; const listener = (event: StorageEvent) => { if (event.key === scopeKey)
        setScope(readScope(event.newValue)); }; window.addEventListener("storage", listener); return () => window.removeEventListener("storage", listener); }, [scopeKey]);
    useEffect(() => {
        if (!isTauri() || !isOverlay)
            return;
        const hidden = listen("alto:overlay-hidden", () => setOverlayVisible(false));
        const shown = listen("alto:overlay-shown", () => setOverlayVisible(true));
        const key = (event: KeyboardEvent) => { if (event.key === "Escape") {
            setOverlayVisible(false);
            void invoke("hide_assistant_overlay");
        } };
        window.addEventListener("keydown", key);
        return () => { void hidden.then((unlisten) => unlisten()); void shown.then((unlisten) => unlisten()); window.removeEventListener("keydown", key); };
    }, [isOverlay]);
    useEffect(() => { if (!isTauri() || isOverlay || !settings.data)
        return; void invoke("set_assistant_shortcut", { enabled: settings.data.desktop_shortcut_enabled, shortcut: settings.data.shortcut }).catch((value: unknown) => setError(value instanceof Error ? value.message : "The desktop shortcut could not be registered.")); }, [isOverlay, settings.data]);
    useEffect(() => {
        if (!config.hackathonDemo || quickstart.status !== "ready" || !bootstrap.error || !scope.actor) return;
        const failedScope = `${scope.run}:${scope.actor}`;
        if (renewalScope.current === failedScope) return;
        renewalScope.current = failedScope;
        quickstartIdentity.current = null;
        setQuickstartAttempt((value) => value + 1);
    }, [bootstrap.error, config.hackathonDemo, quickstart.status, scope.actor, scope.run]);
    function selectRun(run?: string, actor?: string, actorKey?: string) { const next = { run, actor, actorKey: actorKey ?? scope.actorKey }; setScope(next); if (scopeKey) {
        try {
            window.localStorage.setItem(scopeKey, JSON.stringify(next));
        }
        catch { /* Selectors are optional persistence, never authority. */ }
    } }
    async function restartDemo() {
        if (!baseApi || !scope.run || !workspace?.demo_run) return;
        setError(null);
        try {
            await altoRequest(baseApi, `/demo/runs/${scope.run}/archive-reset`, {
                method: "POST",
                body: { expected_row_version: workspace.demo_run.row_version },
            });
            selectRun(undefined, undefined, scope.actorKey);
            quickstartIdentity.current = null;
            setQuickstartAttempt((value) => value + 1);
        } catch (value) {
            setError(value instanceof Error ? value.message : "The demo could not be restarted.");
        }
    }
    async function toggleRail() { const next = !collapsed; setCollapsedOverride(next); if (!api)
        return; try {
        const result = await altoRequest<WorkspacePreferences>(api, "/me/preferences", { method: "PATCH", body: { ...preferences, row_version: undefined, expected_row_version: preferences.row_version, sidebar_collapsed: next } });
        setLocalPreferences(result);
    }
    catch (value) {
        setError(value instanceof Error ? value.message : "Sidebar preference could not be saved.");
    } }
    async function logout() { setError(null); try {
        if (scopeKey)
            window.localStorage.removeItem(scopeKey);
        await onSignOut();
    }
    catch (value) {
        setError(value instanceof Error ? value.message : "Sign out failed.");
    } }
    if (isOverlay)
        return <div className="alto-native-overlay">{workspace?.demo_run && <span className="alto-overlay-scope">Demo run · {workspace.demo_run.actor_name ?? workspace.viewer.display_name}</span>}{overlayVisible && workspace ? <Assistant key={`${scope.run ?? "real"}:${scope.actor ?? "self"}`} api={api} overlay voiceEnabled={workspace.capabilities.includes("voice.transcribe")} placeholder="Ask ALTO… explicit context only"/> : <p>Open the main ALTO window to connect or renew your workspace.</p>}</div>;
    const nav: {
        path: string;
        label: string;
        icon: IconName;
    }[] = [{ path: "/home", label: "Home", icon: "home" }, { path: "/projects", label: employee ? "My projects" : "Projects", icon: "projects" }, { path: "/calendar", label: "My calendar", icon: "calendar" }, ...(!employee ? [{ path: "/plan-review", label: "Plan review", icon: "document" as const }, { path: "/people", label: "People", icon: "people" as const }, { path: "/settings/connections", label: "Connections", icon: "connections" as const }] : [{ path: "/profile", label: "My profile", icon: "people" as const }]), { path: "/notifications", label: "Notifications", icon: "bell" }];
    function isCurrent(path: string) { return route.path === path || (path === "/projects" && (route.path.startsWith("/projects/") || route.path.startsWith("/tasks/"))) || (path === "/people" && route.path.startsWith("/people/")); }
    const displayName = workspace?.viewer.display_name ?? (session.status === "connected" ? "Connected user" : "Your workspace");
    const showAuth = !config.hackathonDemo && session.status !== "connected" && !route.path.startsWith("/settings/");
    const projectMatch = /^\/projects\/([^/]+)\/graph$/.exec(route.path), taskMatch = /^\/tasks\/([^/]+)$/.exec(route.path), personMatch = /^\/people\/([^/]+)$/.exec(route.path), reviewMatch = /^(?:\/tasks\/[^/]+)?\/reviews\/([^/]+)$/.exec(route.path), sourceMatch = /^\/sources\/([^/]+)$/.exec(route.path), preferenceMatch = /^\/preferences\/([^/]+)$/.exec(route.path);
    let content;
    if (config.hackathonDemo && session.status !== "connected")
        content = session.status === "unreachable" ? <EmptyState title="The demo could not start">{session.detail}<button className="alto-primary" onClick={() => void authController.current?.retry()}>Retry</button></EmptyState> : <Loading label="Preparing your private demo workspace…"/>;
    else if (config.hackathonDemo && quickstart.status === "loading")
        content = <Loading label="Preparing Maya and live AI…"/>;
    else if (config.hackathonDemo && quickstart.status === "error")
        content = <EmptyState title="Demo AI is temporarily unavailable">{quickstart.detail}<button className="alto-primary" onClick={() => {
            quickstartIdentity.current = null;
            if (quickstart.statusCode === 403) {
                setQuickstart({ status: "loading" });
                void authController.current?.retry();
                return;
            }
            setQuickstartAttempt((value) => value + 1);
        }}>Retry</button></EmptyState>;
    else if (showAuth)
        content = <AuthView config={config} session={session} controller={authController}/>;
    else if (!workspace && !["/settings/demo", "/settings/deployment", "/settings/about"].includes(route.path))
        content = bootstrap.error ? <EmptyState title="Your workspace could not be opened">Use Retry above, renew your demo role, or check connection settings.<button className="alto-text-button" onClick={() => navigate("/settings/deployment")}>Connection settings</button></EmptyState> : null;
    else if (route.path === "/settings/demo" && api && (workspace?.company.is_demo || scope.run))
        content = <DemoSetup api={api} workspace={workspace} onSelectRun={selectRun} locked={config.hackathonDemo}/>;
    else if ((route.path === "/home" || route.path === "/") && !employee && (route.query.has("request") || route.query.has("plan") || route.query.get("compose") === "plan"))
        content = <PlanningConversation key={`${draftScope}:${route.query.get("request") ?? route.query.get("plan") ?? "new"}`}
            api={api} requestId={route.query.get("request")} planId={route.query.get("plan")}
            initialDraft={planningDraft?.scope === draftScope ? planningDraft.text : undefined}
            lockedDemo={config.hackathonDemo}
            onRequestChange={(id) => navigate(`/home?request=${encodeURIComponent(id)}`)} onClose={() => navigate("/home")}/>;
    else if (route.path === "/home" || route.path === "/")
        content = <HomeView api={api} workspace={workspace} onStartPlanning={startPlanning} threadId={route.query.get("thread")} guidedPrompt={guidedPrompt} guidedLaunch={guidedLaunch}/>;
    else if (route.path === "/projects")
        content = <ProjectsView api={api} employee={employee} completedInitially={route.query.get("status") === "completed"}/>;
    else if (projectMatch?.[1])
        content = <ProjectGraph key={`${projectMatch[1]}:${route.query.toString()}`} api={api} projectId={projectMatch[1]} taskId={route.query.get("task")} initialPanel={route.query.get("panel")} initialPlanId={route.query.get("plan")} employee={employee} breathing={preferences.graph_breathing && !preferences.reduce_motion} locked={config.hackathonDemo}/>;
    else if (taskMatch?.[1])
        content = <TaskBrief key={taskMatch[1]} api={api} taskId={taskMatch[1]}/>;
    else if (reviewMatch?.[1])
        content = <SubmissionReview key={reviewMatch[1]} api={api} submissionId={reviewMatch[1]}/>;
    else if (sourceMatch?.[1])
        content = <SourceEvidence key={sourceMatch[1]} api={api} sourceVersionId={sourceMatch[1]}/>;
    else if (preferenceMatch?.[1])
        content = <SharedPreference key={preferenceMatch[1]} api={api} preferenceId={preferenceMatch[1]}/>;
    else if (route.path === "/calendar")
        content = <CalendarView api={api} scenarioNow={workspace?.demo_run?.clock_at}/>;
    else if (route.path === "/profile")
        content = <PersonProfile key={workspace?.viewer.employee_id ?? "unlinked"} api={api} personId={workspace?.viewer.employee_id ?? null} self/>;
    else if (route.path === "/people" && !employee)
        content = <PeopleDirectory api={api}/>;
    else if (personMatch?.[1] && !employee)
        content = <PersonProfile key={personMatch[1]} api={api} personId={personMatch[1]}/>;
    else if ((route.path === "/plan-review" || route.path === "/projects/new") && !employee)
        content = <div className="alto-legacy-workflow">
<PageHeading title="Plan review" subtitle="Source-grounded proposals, exact approvals and specialist review."/>
<PlanReviewWorkspace key={route.query.toString()} api={api} initialRequestId={route.query.get("request")} initialPlanId={route.query.get("plan")}/>
</div>;
    else if (route.path === "/actions" && !employee)
        content = <ActionsView api={api}/>;
    else if (route.path === "/my-work")
        content = <div className="alto-legacy-workflow">
<EmployeeWorkspace api={api}/>
</div>;
    else if (route.path === "/notifications")
        content = <NotificationsView api={api}/>;
    else if (route.path === "/simulation" && api && workspace?.company.is_demo)
        content = <SimulationView api={api} workspace={workspace} onSelectRun={selectRun}/>;
    else if (route.path === "/settings/connections" && !employee)
        content = <ConnectionsView api={api} isDemo={workspace?.company.is_demo}/>;
    else if (route.path === "/settings/ai" && !employee)
        content = <div>
<PageHeading title="AI & credentials" subtitle="Google model credentials are write-only and permission-scoped."/>
<SettingsTabs active="ai"/>{workspace?.company.is_demo ? <DemoProviderSettings api={api} runMode={workspace.demo_run?.mode} locked={config.hackathonDemo}/> : <CompanyConnections api={api} canManage={session.status === "connected" && session.administrativeRole === "company_admin"}/>}</div>;
    else if (route.path === "/settings/deployment")
        content = <div>
<PageHeading title="Deployment" subtitle="Public endpoint configuration for this installation."/>
<SettingsTabs active="deployment"/>
<DeploymentSettings config={config} onSave={saveDeployment} onReset={resetDeployment} locked={config.hackathonDemo}/>
</div>;
    else if (route.path === "/settings/about")
        content = <AboutView hostStatus={service.detail} apiOrigin={api?.apiOrigin ?? null} locked={config.hackathonDemo} onReplayOnboarding={onboardingEligible ? () => { const next = freshMayaOnboarding(); setOnboardingQuestionFailure(null); commitOnboarding(next); navigate("/home"); } : undefined}/>;
    else if (route.path === "/settings" || route.path === "/settings/workspace")
        content = <>{workspace?.company.is_demo && <section className="alto-settings-section"><h2>Your demo role</h2><p>Explore ALTO as a manager or employee. Your real account permissions stay unchanged.</p><button className="alto-primary" onClick={() => navigate("/settings/demo")}>Choose or switch demo role</button></section>}<WorkspaceSettings key={preferences.row_version} api={api} preferences={preferences} onSaved={(value) => { setLocalPreferences(value); setCollapsedOverride(null); }}/></>;
    else
        content = <EmptyState title="This view is unavailable">It may not exist or may not be permitted for your current role.<button className="alto-text-button" onClick={() => navigate("/home")}>Return home</button>
</EmptyState>;
    return <div className={`alto-shell ${collapsed ? "rail-collapsed" : ""} ${preferences.reduce_motion ? "reduce-motion" : ""}`}>
    <aside className="alto-rail" aria-label="Primary navigation">
<div className="alto-brand-row">{!collapsed && <AltoLogo />}<IconButton icon={collapsed ? "expand" : "collapse"} label={collapsed ? "Expand sidebar" : "Collapse sidebar"} onClick={() => void toggleRail()}/>
</div>
<nav>{nav.map((item) => <button key={item.path} className={`alto-nav-item ${isCurrent(item.path) ? "active" : ""}`} aria-current={isCurrent(item.path) ? "page" : undefined} title={collapsed ? item.label : undefined} aria-label={item.label} onClick={() => navigate(item.path)}>
<Icon name={item.icon}/>
<span>{item.label}</span>
</button>)}</nav>
<div className="alto-rail-footer">
<button className={`alto-nav-item ${route.path.startsWith("/settings") && route.path !== "/settings/connections" ? "active" : ""}`} aria-label="Settings" title={collapsed ? "Settings" : undefined} onClick={() => navigate("/settings/workspace")}>
<Icon name="settings"/>
<span>Settings</span>
</button>
<div className="alto-identity">
<span className="alto-avatar">{initials(displayName)}</span>
<div>
<strong>{displayName}</strong>
<small>{workspace?.viewer.job_title ?? (session.status === "connected" ? humanize(session.administrativeRole) : "Sign in to ALTO")}</small>
</div>
</div>{workspace?.demo_run?.actor_name && <div className="alto-actor-badge">Demo {workspace.viewer.role}: {workspace.demo_run.actor_name}</div>}{(workspace?.company.is_demo || scope.run) && <button className="alto-secondary alto-role-switch" title="Switch demo person" onClick={() => navigate("/settings/demo")}>{collapsed ? <Icon name="people"/> : "Switch demo person"}</button>}{config.hackathonDemo && session.status === "connected" ? <button className="alto-nav-item alto-signout" title="Restart demo" aria-label="Restart demo" onClick={() => void restartDemo()}>
<Icon name="logout" size={18}/>
<span>Restart demo</span>
</button> : session.status === "connected" && <button className="alto-nav-item alto-signout" title="Sign out" aria-label="Sign out" onClick={() => void logout()}>
<Icon name="logout" size={18}/>
<span>Sign out</span>
</button>}</div>
</aside>
    <main className="alto-main">
<div className="alto-topline">
<span>{workspace?.company.is_demo ? "All info here is demo data" : workspace?.company.name ?? "ALTO"}</span>{workspace?.demo_run && <Badge tone="pending">{humanize(workspace.demo_run.mode)}{workspace.demo_run.actor_name ? ` · Demo actor: ${workspace.demo_run.actor_name}` : ""}</Badge>}{session.status === "connected" && <button className="alto-notification-trigger" aria-label="Open notifications" aria-expanded={notifications} onClick={() => setNotifications(!notifications)}>
<Icon name="bell" size={27}/>{session.unreadNotifications > 0 && <span />}</button>}</div>
      {session.status === "connected" && bootstrap.loading && !workspace && <Loading label="Opening your workspace…"/>}{resourceActivity === "stale" && workspace && <span className="alto-background-status" role="status">Some information may be out of date.<button className="alto-text-button" onClick={() => { if (api) invalidateAltoResourceCache(api); }}>Retry refresh</button></span>}<ErrorNotice error={error}/>{bootstrap.error && <div className="alto-bootstrap-error">
<ErrorNotice error={bootstrap.error} retry={bootstrap.refresh}/>{scope.actor && <button className="alto-secondary" onClick={() => { selectRun(scope.run); navigate("/settings/demo"); }}>Choose or renew my demo role</button>}{scope.run && <button className="alto-text-button" onClick={() => { selectRun(); navigate("/home"); }}>Leave unavailable demo workspace</button>}</div>}{session.status === "unreachable" && <div className="alto-offline" role="status">{session.detail}<button className="alto-secondary" onClick={() => void authController.current?.retry()}>Retry connection</button><button className="alto-text-button" onClick={() => navigate("/settings/deployment")}>Connection settings</button></div>}
      <div key={`${scope.run ?? "real"}:${scope.actor ?? "self"}:${route.path}`} className="alto-page">{content}</div>{notifications && <NotificationsView key={`${scope.run}:${scope.actor}`} api={api} compact onClose={() => setNotifications(false)}/>}
    </main>
    {onboardingActive && onboarding.stage !== "complete" && <MayaOnboardingCoachmark
        stage={onboarding.stage}
        questionReady={onboarding.stage === "question_result" && !onboardingQuestionFailure}
        questionFailure={onboardingQuestionFailure}
        onStart={() => { const current = onboardingRef.current; commitOnboarding({ ...current, stage: "ai" }); navigate("/settings/ai"); }}
        onContinueAI={() => { const current = onboardingRef.current; commitOnboarding({ ...current, stage: "deployment" }); navigate("/settings/deployment"); }}
        onContinueDeployment={() => { const current = onboardingRef.current; setOnboardingQuestionFailure(null); commitOnboarding({ ...current, stage: "question_typing", assistantThreadId: undefined }); navigate("/home"); }}
        onContinueQuestion={() => { const current = onboardingRef.current; if (current.stage === "question_result") { commitOnboarding({ ...current, stage: "launch" }); navigate("/home"); } }}
        onRetryQuestion={() => { setOnboardingQuestionFailure(null); commitOnboarding(retryMayaQuestion(onboardingRef.current)); navigate("/home"); }}
    />}
  </div>;
}
