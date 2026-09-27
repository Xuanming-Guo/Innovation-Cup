import { invalidateAltoResourceCache, rejectAltoResourceScope } from "./alto-resource-cache";

export interface AuthorisedApiContext {
  apiOrigin: string;
  companyId: string;
  accessToken: string;
  authUserId?: string;
  demoRunId?: string;
  demoActorSessionId?: string;
}

export interface PlanningSource {
  source_id: string;
  title: string;
  classification: string;
  source_kind: string;
}

export interface PlanningRequestSummary {
  request_id: string;
  original_request: string;
  status: string;
  created_at: string;
}

export interface PlanningContext {
  sources: PlanningSource[];
  requests: PlanningRequestSummary[];
  demo_intake?: {
    kind: "northstar_launch";
    title: string;
    original_request: string;
    description: string;
  } | null;
}

export interface GeminiProviderConfiguration {
  provider: "gemini_developer_api" | "vertex_ai";
  credential_kind: "api_key" | "vertex_service_account";
  status: "configured" | "not_configured";
  credential_hint: string | null;
  validated_model: string | null;
  vertex_project_id: string | null;
  vertex_client_email: string | null;
  vertex_location: string | null;
  configured_at: string | null;
  validated_at: string | null;
  rotated_at: string | null;
}

export interface PlanningRequestDetail {
  request_id: string;
  original_request?: string;
  project_id?: string | null;
  intake_supported?: boolean;
  intake_limitation?: string | null;
  status: string;
  request_version: number;
  latest_outcome: string | null;
  candidate_digest: string | null;
  candidate_contract_id: string | null;
  snapshot_id: string | null;
  plan_id: string | null;
  interpretation_job_state: string | null;
  materialization_job_state: string | null;
  planning_job_state: string | null;
  interpretation_job?: PlanningStageJob | null;
  materialization_job?: PlanningStageJob | null;
  planning_job?: PlanningStageJob | null;
  clarifications: Array<{
    question_key: string;
    category: string;
    question: string;
    blocks_planning: boolean;
    status: string;
  }>;
}

export interface PlanningStageJob {
  job_id: string;
  state: string;
  attempt_count: number;
  max_attempts: number;
  last_error_code: string | null;
  model_call_count?: number | null;
  latest_model_error_code?: string | null;
  can_retry?: boolean;
}

// A saved request must stay reachable if enqueueing subsequently fails. Retrying
// the same stage is safer than asking the manager to create a duplicate request.
export class PlanningStartError extends Error {
  constructor(public readonly requestId: string, cause: unknown) {
    super(cause instanceof Error ? cause.message : "The request was saved, but processing could not start.");
    this.name = "PlanningStartError";
  }
}

export interface PlanBinding {
  proposal_digest: string;
  snapshot_digest: string;
  source_manifest_digest: string;
  base_company_revision: number;
  policy_revision: number;
  policy_version: string;
}

export interface PlanReview {
  author_kind?: "legacy_solver" | "ai_authored" | "authored_replay" | "authored_check";
  plan_id: string;
  request_id: string;
  request_summary: string;
  classification: string;
  status: string;
  binding: PlanBinding;
  tasks: Array<{
    task_id: string;
    task_key: string;
    title: string;
    scheduling_kind: string;
    start_at: string;
    finish_at: string;
    owner_resource_id: string | null;
  }>;
  changes: Array<{
    change_id: string;
    kind: string;
    summary: string;
  }>;
  requirements: Array<{
    requirement_id: string;
    domain: "planning" | "disclosure";
    kind: string;
    authority_kind: string;
    artifact_digest: string;
    reason: string;
    status: string;
  }>;
  can_commit: boolean;
}

export interface PlanEvidence {
  plan_id: string;
  author_kind?: "legacy_solver" | "ai_authored" | "authored_replay" | "authored_check";
  fixed_verification?: {
    product_status: string;
    native_status: string;
    required_rule_ids: string[];
    covered_rule_ids: string[];
    unverified_required_rule_ids: string[];
    diagnostic_rule_ids: string[];
  } | null;
  independent_validation?: { passed: boolean; candidate_digest: string; validator_version: string; issues: unknown[] } | null;
  constraints: Array<{
    constraint_key: string;
    family: string;
    strength: string;
    confidentiality: string;
  }>;
  assumptions: string[];
  solver: {
    classification: string;
    raw_status: string;
    termination: string;
    solver_version: string;
    validator_version: string | null;
    runtime_ms: number;
    diagnostic_constraint_keys: string[];
  } | null;
}

export interface EmployeeTask {
  task_id: string;
  task_key: string;
  title: string;
  scheduling_kind: string;
  status: string;
  row_version: number;
  start_at: string;
  finish_at: string;
  reviewer_name: string | null;
  latest_submission_id: string | null;
  latest_submission_version: number | null;
  approved_brief: {
    brief_version_id: string;
    version: number;
    content: Record<string, unknown>;
  } | null;
}

export interface PendingReview {
  submission_id: string;
  task_id: string;
  task_title: string;
  version: number;
  state: string;
  narrative: string;
  external_evidence_refs: string[];
  submission_digest: string;
  submitting_employee_id: string;
  submitting_employee_name: string;
  review_policy_version: number;
  submitted_at: string;
  files: Array<{
    file_id: string;
    display_filename: string;
    detected_mime_type: string;
    size_bytes: number;
    content_sha256: string;
  }>;
}

function headers(context: AuthorisedApiContext, mutating = false): Record<string, string> {
  return {
    Authorization: `Bearer ${context.accessToken}`,
    "X-Company-ID": context.companyId,
    ...(context.demoRunId ? { "X-Demo-Run-ID": context.demoRunId } : {}),
    ...(context.demoActorSessionId ? { "X-Demo-Actor-Session-ID": context.demoActorSessionId } : {}),
    ...(mutating ? { "Content-Type": "application/json" } : {}),
  };
}

async function requestJson<T>(url: string, init: RequestInit, context?: AuthorisedApiContext): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const value = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    const detail = typeof value?.detail === "string" ? value.detail : `HTTP ${response.status}`;
    if (context && init.method && init.method !== "GET") rejectAltoResourceScope(context, response.status, detail);
    throw new Error(detail);
  }
  const value = await response.json() as T;
  if (context && init.method && init.method !== "GET") invalidateAltoResourceCache(context);
  return value;
}

function idempotencyKey(prefix: string): string {
  return `${prefix}:${crypto.randomUUID()}`;
}

function companyUrl(context: AuthorisedApiContext, suffix: string): string {
  return `${context.apiOrigin}/v1/companies/${context.companyId}${suffix}`;
}

export function getPlanningContext(context: AuthorisedApiContext): Promise<PlanningContext> {
  return requestJson(companyUrl(context, "/planning-context"), {
    headers: headers(context),
  });
}

export function getGeminiProviderConfiguration(
  context: AuthorisedApiContext,
): Promise<GeminiProviderConfiguration> {
  return requestJson(companyUrl(context, "/ai-provider/gemini"), {
    headers: headers(context),
  });
}

export function configureGeminiProvider(
  context: AuthorisedApiContext,
  credential: {
    kind: "api_key" | "vertex_service_account";
    value: string;
  },
): Promise<GeminiProviderConfiguration> {
  return requestJson(companyUrl(context, "/ai-provider/gemini"), {
    method: "PUT",
    headers: headers(context, true),
    body: JSON.stringify({
      credential_kind: credential.kind,
      ...(credential.kind === "api_key"
        ? { api_key: credential.value }
        : { service_account_json: credential.value }),
      correlation_id: crypto.randomUUID(),
    }),
  }, context);
}

export function removeGeminiProvider(
  context: AuthorisedApiContext,
): Promise<GeminiProviderConfiguration> {
  const correlationId = encodeURIComponent(crypto.randomUUID());
  return requestJson(companyUrl(context, `/ai-provider/gemini?correlation_id=${correlationId}`), {
    method: "DELETE",
    headers: headers(context),
  }, context);
}

export async function createPlanningRequest(
  context: AuthorisedApiContext,
  input: {
    originalRequest: string;
    sourceIds: string[];
    requestedDeadline: string;
    requestedPriorityKey: string;
    idempotencyKey?: string;
  },
): Promise<{ request_id: string }> {
  const deadline = input.requestedDeadline
    ? new Date(input.requestedDeadline)
    : null;
  if (deadline && Number.isNaN(deadline.getTime())) {
    throw new Error("Target deadline is invalid");
  }
  const created = await requestJson<{ request_id: string }>(
    companyUrl(context, "/planning-requests"),
    {
      method: "POST",
      headers: {
        ...headers(context, true),
        "Idempotency-Key": input.idempotencyKey ?? idempotencyKey("planning-request"),
      },
      body: JSON.stringify({
        project_id: null,
        original_request: input.originalRequest,
        selected_source_ids: input.sourceIds,
        requested_priority_key: input.requestedPriorityKey || null,
        requested_deadline: deadline?.toISOString() ?? null,
        requested_deadline_timezone: deadline
          ? Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"
          : null,
      }),
    },
    context,
  );
  try {
    await startPlanningInterpretation(context, created.request_id);
  } catch (error) {
    throw new PlanningStartError(created.request_id, error);
  }
  return created;
}

export function startPlanningInterpretation(
  context: AuthorisedApiContext,
  requestId: string,
): Promise<unknown> {
  return requestJson(companyUrl(context, `/planning-requests/${encodeURIComponent(requestId)}/interpret`), {
    method: "POST",
    headers: { ...headers(context, true), "Idempotency-Key": `interpretation:${requestId}` },
    body: "{}",
  }, context);
}

export async function createNorthstarPlanningRequest(
  context: AuthorisedApiContext,
  commandKey: string,
): Promise<{ request_id: string }> {
  if (!context.demoRunId) throw new Error("Select a demo workspace before preparing Northstar.");
  const created = await requestJson<{ request_id: string }>(companyUrl(context, `/demo/runs/${encodeURIComponent(context.demoRunId)}/launch-request`), {
    method: "POST",
    headers: { ...headers(context, true), "Idempotency-Key": commandKey },
    body: "{}",
  }, context);
  try {
    await startPlanningInterpretation(context, created.request_id);
  } catch (error) {
    throw new PlanningStartError(created.request_id, error);
  }
  return created;
}

export function retryPlanningJob(
  context: AuthorisedApiContext,
  jobId: string,
  reason: string,
  retryKey: string,
): Promise<PlanningStageJob> {
  return requestJson(companyUrl(context, `/jobs/${encodeURIComponent(jobId)}/retry`), {
    method: "POST",
    headers: { ...headers(context, true), "Idempotency-Key": retryKey },
    body: JSON.stringify({ reason: reason.trim() }),
  }, context);
}

export function getPlanningRequest(
  context: AuthorisedApiContext,
  requestId: string,
): Promise<PlanningRequestDetail> {
  return requestJson(companyUrl(context, `/planning-requests/${requestId}`), {
    headers: headers(context),
  });
}

export async function answerPlanningClarifications(
  context: AuthorisedApiContext,
  request: PlanningRequestDetail,
  answers: Record<string, string>,
  commandKey?: string,
): Promise<{ request_id: string }> {
  if (!request.candidate_contract_id) {
    throw new Error("The clarification candidate is unavailable");
  }
  const resumed = await requestJson<{ request_id: string }>(
    companyUrl(context, `/planning-requests/${request.request_id}/clarifications`),
    {
      method: "POST",
      headers: {
        ...headers(context, true),
        "Idempotency-Key": commandKey ?? idempotencyKey("clarification-answers"),
      },
      body: JSON.stringify({
        request_version: request.request_version,
        candidate_contract_id: request.candidate_contract_id,
        answers,
      }),
    },
    context,
  );
  try {
    await startPlanningInterpretation(context, resumed.request_id);
  } catch (error) {
    throw new PlanningStartError(resumed.request_id, error);
  }
  return resumed;
}

export function getPlan(context: AuthorisedApiContext, planId: string): Promise<PlanReview> {
  return requestJson(companyUrl(context, `/plans/${planId}`), { headers: headers(context) });
}

export function getPlanEvidence(
  context: AuthorisedApiContext,
  planId: string,
): Promise<PlanEvidence> {
  return requestJson(companyUrl(context, `/plans/${planId}/evidence`), {
    headers: headers(context),
  });
}

export function approveRequirement(
  context: AuthorisedApiContext,
  plan: PlanReview,
  requirement: PlanReview["requirements"][number],
): Promise<unknown> {
  return requestJson(companyUrl(context, `/plans/${plan.plan_id}/approve`), {
    method: "POST",
    headers: {
      ...headers(context, true),
      "Idempotency-Key": idempotencyKey("plan-approval"),
    },
    body: JSON.stringify({
      requirement_id: requirement.requirement_id,
      artifact_digest: requirement.artifact_digest,
      binding: plan.binding,
      explanation: "Approved after reviewing the exact proposal and disclosure boundary.",
      correlation_id: crypto.randomUUID(),
    }),
  }, context);
}

export function commitPlan(context: AuthorisedApiContext, plan: PlanReview): Promise<unknown> {
  return requestJson(companyUrl(context, `/plans/${plan.plan_id}/commit`), {
    method: "POST",
    headers: {
      ...headers(context, true),
      "Idempotency-Key": idempotencyKey("plan-commit"),
    },
    body: JSON.stringify({ binding: plan.binding, correlation_id: crypto.randomUUID() }),
  }, context);
}

export async function getEmployeeTasks(
  context: AuthorisedApiContext,
  view: "today" | "upcoming" | "blocked" | "submitted",
): Promise<EmployeeTask[]> {
  const value = await requestJson<{ tasks: EmployeeTask[] }>(
    companyUrl(context, `/me/tasks?view=${view}`),
    { headers: headers(context) },
  );
  return value.tasks;
}

export function transitionTask(
  context: AuthorisedApiContext,
  task: EmployeeTask,
  command: "acknowledge" | "start" | "block" | "unblock",
): Promise<unknown> {
  return requestJson(companyUrl(context, `/tasks/${task.task_id}/events`), {
    method: "POST",
    headers: {
      ...headers(context, true),
      "Idempotency-Key": idempotencyKey(`task-${command}`),
    },
    body: JSON.stringify({
      command,
      expected_task_version: task.row_version,
      payload: {},
      correlation_id: crypto.randomUUID(),
    }),
  }, context);
}

export function submitTask(
  context: AuthorisedApiContext,
  task: EmployeeTask,
  narrative: string,
): Promise<unknown> {
  return requestJson(companyUrl(context, `/tasks/${task.task_id}/submissions`), {
    method: "POST",
    headers: {
      ...headers(context, true),
      "Idempotency-Key": idempotencyKey("task-submit"),
    },
    body: JSON.stringify({
      narrative,
      external_evidence_refs: [],
      file_ids: [],
      reported_active_minutes: null,
      expected_task_version: task.row_version,
      correlation_id: crypto.randomUUID(),
    }),
  }, context);
}

export async function getPendingReviews(
  context: AuthorisedApiContext,
): Promise<PendingReview[]> {
  const value = await requestJson<{ reviews: PendingReview[] }>(
    companyUrl(context, "/reviews/pending"),
    { headers: headers(context) },
  );
  return value.reviews;
}

export function reviewSubmission(
  context: AuthorisedApiContext,
  review: PendingReview,
  decision: "accepted" | "revision_requested",
): Promise<unknown> {
  return requestJson(
    companyUrl(context, `/submissions/${review.submission_id}/review`),
    {
      method: "POST",
      headers: {
        ...headers(context, true),
        "Idempotency-Key": idempotencyKey(`submission-${decision}`),
      },
      body: JSON.stringify({
        expected_submission_version: review.version,
        submission_digest: review.submission_digest,
        decision,
        criterion_findings: [{ criterion: "connected-demo", result: decision }],
        correction_request:
          decision === "revision_requested"
            ? "Please add the missing acceptance evidence and submit a new exact version."
            : "",
        correlation_id: crypto.randomUUID(),
      }),
    },
    context,
  );
}
