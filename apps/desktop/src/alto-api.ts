import type { AuthorisedApiContext, EmployeeTask } from "./api-client";
import { COMMAND_TIMEOUT_MS, READ_TIMEOUT_MS, withRequestDeadline } from "./request-deadline";
import { invalidateAltoResourceCache, rejectAltoResourceScope } from "./alto-resource-cache";
/** Read models contain only server-authorised projections. No demo content is seeded in the UI. */
export interface AltoApiContext extends AuthorisedApiContext {
    authUserId?: string;
    demoRunId?: string;
    demoActorSessionId?: string;
}
export interface WorkspaceBootstrap {
    company: {
        id: string;
        name: string;
        is_demo: boolean;
    };
    viewer: {
        user_id: string;
        employee_id: string | null;
        display_name: string;
        role: "manager" | "employee";
        job_title: string;
    };
    demo_run: {
        id: string;
        mode: string;
        clock_at: string;
        actor_name: string | null;
        actor_session_id?: string | null;
        row_version: number;
        clock_version?: number;
    } | null;
    capabilities: string[];
}
export interface Project {
    id: string;
    title: string;
    goal_label?: string;
    status: string;
    deadline: string | null;
    updated_at: string;
    task_count: number;
    completed_task_count: number;
    plan_id: string | null;
    accepted_at?: string | null;
    accepted_by?: string | null;
    description?: string;
}
export interface ActionItem {
    id: string;
    title: string;
    kind: string;
    status: string;
    target_path: string;
    detail?: string;
}
export interface HomeData {
    recent_projects: Project[];
    completed_projects: Project[];
    actions: ActionItem[];
    tasks: EmployeeTask[];
}
export interface WorkspacePreferences {
    row_version: number;
    sidebar_collapsed: boolean;
    graph_breathing: boolean;
    reduce_motion: boolean;
    desktop_shortcut_enabled: boolean;
    shortcut: string;
}
export const defaultPreferences: WorkspacePreferences = { row_version: 0, sidebar_collapsed: false, graph_breathing: true, reduce_motion: false, desktop_shortcut_enabled: false, shortcut: "Control+Space" };
export interface GraphNode {
    id: string;
    task_key: string;
    title: string;
    team: string;
    owner_name: string | null;
    owner_employee_id: string | null;
    status: string;
    start_at: string | null;
    finish_at: string | null;
    reviewer_name: string | null;
    summary: string;
    is_mine: boolean;
    can_work: boolean;
    row_version: number;
}
export interface GraphEdge {
    id: string;
    from: string;
    to: string;
    kind: "dependency" | "handoff" | "review" | "acceptance";
    label: string;
}
export interface RuleResult {
    id: string;
    rule_id: string;
    title: string;
    status: string;
    description: string;
    formula: string | null;
    source_label: string | null;
    source_version: string | null;
    candidate_values: CandidateValue | null;
    category_key?: string | null;
    category_title?: string | null;
    category_keys?: string[] | null;
    category_titles?: string[] | null;
    encoding_version?: string | null;
    technical_expression_available?: boolean;
}
export type CandidateValue = string | number | boolean | null | CandidateValue[] | { [key: string]: CandidateValue };
export interface VerificationSummary {
    proposal_id: string;
    author_kind: string;
    product_status: string;
    native_status: string;
    z3_version: string | null;
    compiler_version: string | null;
    verifier_version: string | null;
    duration_ms: number | null;
    required_rule_count: number;
    covered_rule_count: number;
    unverified_rule_count: number;
    candidate_digest: string | null;
    snapshot_digest: string | null;
    digests_match: boolean;
    independent_validation_passed: boolean;
    validator_version: string | null;
    approval_status: string;
}
export interface RuleTechnicalDetail {
    rule_id: string;
    technical_expression: string | null;
    encoding_version: string | null;
}
export interface ProjectGraphData {
    candidate_history?: { proposal_id: string; version: number; author_kind: string; product_status: string; independent_validation_passed: boolean | null; candidate_digest: string; created_at: string }[];
    selected_proposal_id?: string | null;
    is_candidate_preview?: boolean;
    project: Project;
    nodes: GraphNode[];
    edges: GraphEdge[];
    rules: RuleResult[];
    verification_summary?: VerificationSummary | null;
    plan_id: string | null;
    can_approve: boolean;
    check_status: string;
    approval_disabled_reason: string | null;
    timezone: string;
}
export interface CalendarItem {
    id: string;
    title: string;
    start_at: string;
    end_at: string;
    kind: "meeting" | "busy" | "work" | "deadline" | "protected";
    source: string;
    status: string;
    task_id: string | null;
    project_id: string | null;
    description: string;
    owner_name: string | null;
}
export interface CalendarData {
    items: CalendarItem[];
    timezone: string;
    sources: {
        name: string;
        status: string;
    }[];
}
export interface Person {
    id: string;
    timezone?: string;
    display_name: string;
    job_title: string;
    operating_group: string;
    function: string;
    profile_depth: string;
    row_version: number;
    skills: {
        name: string;
        provenance: string;
    }[];
    past_projects: Project[];
    ongoing_projects: Project[];
    availability: CalendarItem[];
    shared_preferences: {
        id: string;
        text: string;
        shared_at: string;
    }[];
}
export interface Connection {
    id: string;
    name: string;
    provider: string;
    direction: "read" | "write";
    description: string;
    scope: string;
    status: string;
    timezone: string | null;
    imports: string[];
    last_synced_at: string | null;
    can_revoke: boolean;
    row_version: number;
}
export interface NotificationItem {
    notification_id: string;
    kind?: string;
    message_key: string;
    subject_type: string;
    subject_id: string;
    title?: string;
    body?: string;
    target_path?: string | null;
    created_at: string;
    seen_at: string | null;
    acknowledged_at?: string | null;
}
export interface EmployeePreference {
    id: string;
    text: string;
    status: string;
    row_version: number;
    manager_id: string | null;
    manager_name: string | null;
    shared_at: string | null;
}
export interface AssistantContext {
    kind: "global" | "project" | "task" | "person";
    id?: string;
    label?: string;
    proposal_id?: string;
}
export interface AssistantMessage {
    id: string;
    role: "user" | "assistant";
    content: string;
    created_at: string;
    citations: {
        label: string;
        target_path: string;
    }[];
}
export interface AssistantActionChange {
    id: string;
    label: string;
    field: string;
    before: string | null;
    after: string;
}
export interface AssistantPendingAction {
    id: string;
    kind: "plan_change" | "plan_approval" | "plan_commit";
    status: "pending_confirmation" | "executing" | "completed" | "dismissed" | "expired" | "failed";
    title: string;
    summary: string;
    project_id: string;
    proposal_id: string | null;
    plan_id: string | null;
    scope: {
        label: string;
        value: string;
    }[];
    changes: AssistantActionChange[];
    violations: RuleResult[];
    warnings: string[];
    confirmation: {
        label: string;
        consequence: string;
        expected_version: string | number;
    };
    result_target_path: string | null;
}
export interface AssistantThread {
    id: string;
    messages: AssistantMessage[];
    status: string;
    stage: string | null;
    error: string | null;
    pending_actions?: AssistantPendingAction[];
}
export interface TaskDetail {
    task: EmployeeTask;
    project: Project | null;
    owner_name: string | null;
    reviewer_name: string | null;
    approver_name: string | null;
    timezone: string;
    timeline: {
        id: string;
        title: string;
        start_at: string;
        end_at: string | null;
        kind: string;
    }[];
    protected_commitments: string[];
    attachments: {
        id: string;
        filename: string;
        version: number;
        state: string;
    }[];
    can_work: boolean;
    can_give_feedback?: boolean;
    draft: {
        text: string;
        row_version: number;
    } | null;
    gate?: {
        kind: "readiness" | "milestone";
        required_submission: {
            id: string;
            digest: string;
            version: number;
            narrative: string;
        } | null;
    } | null;
}
export interface DemoRun {
    id: string;
    name: string;
    mode: string;
    clock_at: string;
    row_version: number;
    clock_version: number;
    protected: boolean;
    status: string;
    actor_session_id?: string | null;
}
export interface DemoData {
    runs: DemoRun[];
    actors: {
        id: string;
        synthetic_key: string;
        display_name: string;
        job_title: string;
        role?: "manager" | "employee";
    }[];
    can_create: boolean;
}
export interface DemoQuickstart {
    run_id: string;
    actor_session_id: string;
    actor_key: string;
    provider_status: "configured";
}
export class AltoApiError extends Error {
    constructor(
        message: string,
        readonly status: number,
        readonly retryAfterSeconds: number | null = null,
    ) { super(message); }
}

function retryAfterSeconds(response: Response): number | null {
    const value = response.headers.get("Retry-After")?.trim();
    if (!value) return null;
    if (/^\d+$/.test(value)) return Math.max(1, Number.parseInt(value, 10));
    const retryAt = Date.parse(value);
    return Number.isNaN(retryAt) ? null : Math.max(1, Math.ceil((retryAt - Date.now()) / 1000));
}

export async function altoRequest<T>(context: AltoApiContext, path: string, options: {
    method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
    body?: unknown;
    signal?: AbortSignal;
    idempotencyKey?: string;
} = {}): Promise<T> {
    const isCommand = options.method !== undefined && options.method !== "GET";
    return withRequestDeadline(async (signal) => {
    const response = await fetch(`${context.apiOrigin}/v1/companies/${encodeURIComponent(context.companyId)}${path}`, {
        method: options.method ?? "GET", signal,
        headers: { Authorization: `Bearer ${context.accessToken}`, "X-Company-ID": context.companyId,
            ...(context.demoRunId ? { "X-Demo-Run-ID": context.demoRunId } : {}),
            ...(context.demoActorSessionId ? { "X-Demo-Actor-Session-ID": context.demoActorSessionId } : {}),
            ...(options.body === undefined ? {} : { "Content-Type": "application/json" }),
            ...(options.method && options.method !== "GET" ? { "Idempotency-Key": options.idempotencyKey ?? crypto.randomUUID() } : {}),
        }, body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
    if (!response.ok) {
        const value: unknown = await response.json().catch(() => null);
        const detail = typeof value === "object" && value !== null && "detail" in value && typeof value.detail === "string" ? value.detail : `Request failed (${response.status}).`;
        if (isCommand) rejectAltoResourceScope(context, response.status, detail);
        throw new AltoApiError(detail, response.status, retryAfterSeconds(response));
    }
    if (response.status === 204) {
        if (isCommand) invalidateAltoResourceCache(context);
        return undefined as T;
    }
    const result = await response.json() as T;
    if (isCommand) invalidateAltoResourceCache(context);
    return result;
    }, {
        signal: options.signal,
        timeoutMs: isCommand ? COMMAND_TIMEOUT_MS : READ_TIMEOUT_MS,
        timeoutMessage: isCommand ? "The change timed out and may have completed. Refresh its status before retrying." : undefined,
    });
}
export function safeTarget(path: string | null | undefined, fallback = "/home"): string {
    return path && /^\/(?!\/)[a-z][a-z0-9/?=&%_.:-]*$/i.test(path) ? path : fallback;
}
