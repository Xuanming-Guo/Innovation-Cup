import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AuthorisedApiContext, PlanEvidence, PlanningRequestDetail, PlanReview } from "./api-client";
import { PlanningConversation } from "./planning-conversation";
import { PlanReviewWorkspace } from "./plan-review";
import { clearAltoResourceCache } from "./alto-resource-cache";

const api: AuthorisedApiContext = { apiOrigin: "https://planning.example.invalid", companyId: "company-1", authUserId: "user-1", accessToken: "test-token", demoRunId: "run-1", demoActorSessionId: "actor-1" };
const request: PlanningRequestDetail = {
  request_id: "request-1", original_request: "Prepare the authorised launch handoff.", project_id: "project-1", status: "interpreting", request_version: 1,
  latest_outcome: null, candidate_digest: null, candidate_contract_id: null, snapshot_id: null, plan_id: null,
  interpretation_job_state: "review_required", materialization_job_state: null, planning_job_state: null,
  interpretation_job: { job_id: "job-1", state: "review_required", attempt_count: 1, max_attempts: 6, last_error_code: "model_invalid_output", can_retry: true }, clarifications: [],
};
const plan: PlanReview = {
  plan_id: "plan-1", request_id: "request-1", request_summary: "Checked launch handoff", classification: "feasible", status: "proposed", can_commit: false,
  binding: { proposal_digest: "proposal-v1", snapshot_digest: "snapshot-v1", source_manifest_digest: "sources-v1", base_company_revision: 7, policy_revision: 2, policy_version: "policy-v2" },
  tasks: [{ task_id: "task-1", task_key: "T1", title: "Prepare approved brief", scheduling_kind: "flexible_active", start_at: "2026-10-01T09:00:00Z", finish_at: "2026-10-01T10:00:00Z", owner_resource_id: "resource-1" }], changes: [],
  requirements: [
    { requirement_id: "approval-1", domain: "planning", kind: "manager", authority_kind: "manager", artifact_digest: "artifact-plan", reason: "Approve this exact schedule.", status: "pending" },
    { requirement_id: "disclosure-1", domain: "disclosure", kind: "employee_brief", authority_kind: "manager", artifact_digest: "artifact-disclosure", reason: "Share only the approved brief with its assignee.", status: "pending" },
  ],
};
const evidence: PlanEvidence = {
  plan_id: "plan-1", constraints: [], assumptions: [], solver: null,
  fixed_verification: { product_status: "CHECKED", native_status: "sat", required_rule_ids: ["R1"], covered_rule_ids: ["R1"], unverified_required_rule_ids: [], diagnostic_rule_ids: [] },
  independent_validation: { passed: true, candidate_digest: "proposal-v1", validator_version: "v1", issues: [] },
};
function json(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } }); }
function mockReads(detail = request, exactPlan = plan, exactEvidence = evidence) {
  return vi.fn().mockImplementation((input: string, options?: RequestInit) => {
    if (options?.method && options.method !== "GET") throw new Error(`Unexpected mutation: ${input}`);
    if (input.endsWith("/planning-context")) return Promise.resolve(json({ sources: [{ source_id: "source-1", title: "Authorised launch brief", source_kind: "fixture", classification: "internal" }], requests: [{ request_id: detail.request_id, original_request: detail.original_request, status: detail.status, created_at: "2026-09-27T09:00:00Z" }] }));
    if (input.endsWith("/planning-requests/request-1")) return Promise.resolve(json(detail));
    if (input.endsWith("/plans/plan-1/evidence")) return Promise.resolve(json(exactEvidence));
    if (input.endsWith("/plans/plan-1")) return Promise.resolve(json(exactPlan));
    if (input.endsWith("/projects/project-1/graph?plan_id=plan-1")) return Promise.resolve(json({ plan_id: "plan-1", nodes: [{ id: "task-1", owner_name: "Iris", reviewer_name: "Maya" }], rules: [] }));
    if (input.endsWith("/reviews/pending")) return Promise.resolve(json({ reviews: [] }));
    if (input.endsWith("/projects")) return Promise.resolve(json({ projects: [] }));
    throw new Error(`Unexpected read: ${input}`);
  });
}
afterEach(() => { cleanup(); clearAltoResourceCache(); vi.restoreAllMocks(); vi.unstubAllGlobals(); window.location.hash = "/home"; });

describe("durable planning conversation", () => {
  it("distinguishes one worker attempt from three recorded AI attempts and explains the final truncation", async () => {
    const fetcher = mockReads({ ...request, interpretation_job_state: "succeeded", interpretation_job: null, materialization_job_state: "succeeded", planning_job_state: "review_required", planning_job: { job_id: "authoring-1", state: "review_required", attempt_count: 1, max_attempts: 3, last_error_code: "fixed_plan_not_verified", model_call_count: 3, latest_model_error_code: "model_output_truncated", can_retry: false } });
    vi.stubGlobal("fetch", fetcher);
    render(<PlanningConversation api={api} requestId="request-1" />);
    expect(await screen.findByText(/latest AI attempt was cut off/)).toBeVisible();
    expect(screen.getByText(/did not produce a schedule that passed every required check/)).toBeVisible();
    fireEvent.click(screen.getByText("Processing details"));
    expect(screen.getByText(/Worker attempts: 1/)).toBeVisible();
    expect(screen.getByText("AI attempts recorded: 3")).toBeVisible();
    expect(screen.getByText(/not a provider billing count/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Review retry options" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Review plan" })).not.toBeInTheDocument();
    expect(screen.queryByRole("status", { name: "Planning in progress" })).not.toBeInTheDocument();
    expect(fetcher.mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
  });

  it.each(["fixed_plan_not_verified", "planning_cancelled_fenced_or_ambiguous"])("creates one fresh Northstar successor for a locked %s schedule failure", async (errorCode) => {
    const failed = {
      ...request,
      status: "failed",
      interpretation_job_state: "succeeded",
      interpretation_job: null,
      materialization_job_state: "succeeded",
      planning_job_state: "review_required",
      planning_job: { job_id: "authoring-1", state: "review_required", attempt_count: 1, max_attempts: 3, last_error_code: errorCode, model_call_count: 1, can_retry: true },
    };
    const reads = mockReads(failed);
    const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST" && url.endsWith("/demo/runs/run-1/launch-request")) return Promise.resolve(json({ request_id: "request-2" }));
      if (init?.method === "POST" && url.endsWith("/planning-requests/request-2/interpret")) return Promise.resolve(json({}));
      if (url.endsWith("/planning-requests/request-2")) return Promise.resolve(json({ ...request, request_id: "request-2", interpretation_job_state: "queued", interpretation_job: { ...request.interpretation_job!, state: "queued", can_retry: false } }));
      return reads(url, init);
    });
    vi.stubGlobal("fetch", fetcher);
    const onRequestChange = vi.fn();
    render(<PlanningConversation api={api} requestId="request-1" lockedDemo onRequestChange={onRequestChange} />);

    const prepare = await screen.findByRole("button", { name: "Prepare a new Northstar plan" });
    expect(screen.queryByRole("button", { name: "Review retry options" })).not.toBeInTheDocument();
    fireEvent.click(prepare);
    fireEvent.click(prepare);

    await waitFor(() => expect(onRequestChange).toHaveBeenCalledWith("request-2"));
    const writes = fetcher.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(writes).toHaveLength(2);
    expect(writes[0]![0]).toContain("/demo/runs/run-1/launch-request");
    expect(writes[0]![1].headers["Idempotency-Key"]).toMatch(/^planning-successor:/);
    expect(writes[1]![0]).toContain("/planning-requests/request-2/interpret");
    expect(writes.some(([url]) => String(url).includes("/jobs/authoring-1/retry"))).toBe(false);
  });

  it("explains a latest version conflict without claiming the model proved work changed", async () => {
    vi.stubGlobal("fetch", mockReads({ ...request, interpretation_job: { ...request.interpretation_job!, latest_model_error_code: "prior_work_version_changed" } }));
    render(<PlanningConversation api={api} requestId="request-1" />);
    expect(await screen.findByText(/did not match the recorded version of existing work/)).toBeVisible();
  });

  it.each([null, undefined])("does not invent a legacy AI count when metadata is %s", async (count) => {
    vi.stubGlobal("fetch", mockReads({ ...request, interpretation_job: { ...request.interpretation_job!, model_call_count: count, latest_model_error_code: "private-provider-error-must-not-render" } }));
    render(<PlanningConversation api={api} requestId="request-1" />);
    await screen.findByText("Processing details");
    fireEvent.click(screen.getByText("Processing details"));
    expect(screen.getByText(/Worker attempts: 1/)).toBeVisible();
    expect(screen.queryByText(/AI attempts recorded/)).not.toBeInTheDocument();
    expect(screen.queryByText(/private-provider-error-must-not-render/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Latest AI error/)).not.toBeInTheDocument();
  });

  it.each(["queued", "leased", "running", "retry_scheduled"])("shows an accessible running circle only for an active %s stage", async (state) => {
    const detail = { ...request, status: "failed", interpretation_job_state: state, interpretation_job: { ...request.interpretation_job!, state, can_retry: false } };
    const fetcher = mockReads(detail); vi.stubGlobal("fetch", fetcher);
    render(<PlanningConversation api={api} requestId="request-1" />);
    const indicator = await screen.findByRole("status", { name: "Planning in progress" });
    expect(indicator).toHaveAttribute("aria-live", "polite");
    expect(indicator.querySelector(".alto-planning-spinner")).toHaveAttribute("aria-hidden", "true");
    expect(indicator.querySelector(".alto-planning-sr-only")).toHaveTextContent("Understanding your request");
    expect(screen.getByRole("region", { name: "ALTO progress summary" })).toHaveTextContent(state === "queued" ? "Understanding your request is queued and waiting to start." : state === "retry_scheduled" ? "Understanding your request is waiting for its recorded retry." : "ALTO is checking the request's goal, deadline and permitted planning scope.");
    expect(screen.getByRole("region", { name: "ALTO progress summary" })).toHaveTextContent("No action is needed while this runs");
    expect(screen.queryByText(/Updating this saved request/)).not.toBeInTheDocument();
    expect(fetcher.mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
  });

  it("summarises recorded stage completion and the current constraint check without exposing model reasoning", async () => {
    const detail = {
      ...request,
      status: "interpreted",
      interpretation_job_state: "succeeded",
      interpretation_job: { ...request.interpretation_job!, state: "succeeded", last_error_code: null, can_retry: false },
      materialization_job_state: "running",
      materialization_job: { job_id: "materialize-1", state: "running", attempt_count: 1, max_attempts: 6, last_error_code: null, can_retry: false },
    };
    vi.stubGlobal("fetch", mockReads(detail));
    render(<PlanningConversation api={api} requestId="request-1" />);
    const summary = await screen.findByRole("region", { name: "ALTO progress summary" });
    expect(summary).toHaveTextContent("ALTO is checking the authorised sources, people, commitments and constraints needed for the plan.");
    expect(summary).toHaveTextContent(/Completed\s*Understanding your request/);
    expect(summary).not.toHaveTextContent(/thought|reasoning|provider response/i);
    expect(screen.getByRole("status", { name: "Planning in progress" })).toBeVisible();
  });

  it("gives a terminal next action from recorded access state and never shows a running indicator", async () => {
    vi.stubGlobal("fetch", mockReads({ ...request, interpretation_job: { ...request.interpretation_job!, last_error_code: "requester_authority_revoked" } }));
    render(<PlanningConversation api={api} requestId="request-1" />);
    const summary = await screen.findByRole("region", { name: "ALTO progress summary" });
    expect(summary).toHaveTextContent("Understanding your request stopped before a reviewable plan was ready.");
    expect(summary).toHaveTextContent("Ask your workspace administrator to review the required access.");
    expect(screen.queryByRole("status", { name: "Planning in progress" })).not.toBeInTheDocument();
  });

  it("summarises a ready proposal with the exact review action", async () => {
    vi.stubGlobal("fetch", mockReads({ ...request, plan_id: "plan-1", interpretation_job_state: "succeeded", interpretation_job: null, materialization_job_state: "succeeded", planning_job_state: "succeeded" }));
    render(<PlanningConversation api={api} requestId="request-1" />);
    await screen.findByText("The automated checks produced a proposal that is ready for your review.");
    const summary = screen.getByRole("region", { name: "ALTO progress summary" });
    expect(summary).toHaveTextContent("The automated checks produced a proposal that is ready for your review.");
    expect(summary).toHaveTextContent("Review the exact tasks, schedule, checks and approval requirements.");
    expect(summary).toHaveTextContent("Understanding your request · Checking sources and constraints · Checking the proposed schedule");
    expect(screen.queryByRole("status", { name: "Planning in progress" })).not.toBeInTheDocument();
  });

  it("keeps read-only polling through stage handoffs and stops once a proposal is ready", async () => {
    let poll: (() => void) | undefined;
    const realInterval = window.setInterval.bind(window);
    const intervals = vi.spyOn(window, "setInterval").mockImplementation((handler, delay, ...args) => {
      if (delay !== 2500) return realInterval(handler, delay, ...args) as unknown as NodeJS.Timeout;
      poll = handler as () => void;
      return 77 as unknown as NodeJS.Timeout;
    });
    const stop = vi.spyOn(window, "clearInterval");
    let detail: PlanningRequestDetail = { ...request, status: "interpreted", interpretation_job_state: "succeeded", interpretation_job: null };
    const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => mockReads(detail)(url, init));
    vi.stubGlobal("fetch", fetcher);
    render(<PlanningConversation api={api} requestId="request-1" />);
    expect(await screen.findByText("The previous step is complete. Waiting for the next planning stage.")).toBeVisible();
    expect(screen.queryByRole("status", { name: "Planning in progress" })).not.toBeInTheDocument();
    expect(intervals).toHaveBeenCalledWith(expect.any(Function), 2500);
    detail = { ...detail, materialization_job_state: "queued" };
    await act(async () => { poll?.(); });
    expect(await screen.findByRole("status", { name: "Planning in progress" })).toBeVisible();
    detail = { ...detail, materialization_job_state: "succeeded", plan_id: "plan-1" };
    await act(async () => { poll?.(); });
    expect(await screen.findByRole("button", { name: "Review plan" })).toBeVisible();
    expect(screen.queryByRole("status", { name: "Planning in progress" })).not.toBeInTheDocument();
    expect(stop).toHaveBeenCalledWith(77);
    expect(fetcher.mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
  });

  it("does not animate or poll a terminal stop or a genuine blocking question", async () => {
    const intervals = vi.spyOn(window, "setInterval");
    vi.stubGlobal("fetch", mockReads({ ...request, clarifications: [{ question_key: "owner", category: "authority", question: "Who may approve the handoff?", blocks_planning: true, status: "open" }] }));
    render(<PlanningConversation api={api} requestId="request-1" />);
    await screen.findByText("Who may approve the handoff?");
    expect(screen.queryByRole("status", { name: "Planning in progress" })).not.toBeInTheDocument();
    expect(intervals.mock.calls.some(([, delay]) => delay === 2500)).toBe(false);
  });

  it("does not wait forever when historical schedule checking finished without a plan", async () => {
    const intervals = vi.spyOn(window, "setInterval");
    vi.stubGlobal("fetch", mockReads({ ...request, status: "interpreted", interpretation_job_state: "succeeded", interpretation_job: null, materialization_job_state: "succeeded", planning_job_state: "succeeded" }));
    render(<PlanningConversation api={api} requestId="request-1" />);
    expect(await screen.findByText("Processing finished without a reviewable plan. No work has been assigned.")).toBeVisible();
    expect(screen.queryByRole("status", { name: "Planning in progress" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Waiting for the next planning stage/)).not.toBeInTheDocument();
    expect(intervals.mock.calls.some(([, delay]) => delay === 2500)).toBe(false);
  });

  it("keeps successful refreshes quiet and stops claiming active work while its status is unavailable", async () => {
    let refreshFailure = false;
    let finishRefresh: ((value: Response) => void) | undefined;
    const detail = { ...request, interpretation_job_state: "running", interpretation_job: { ...request.interpretation_job!, state: "running", can_retry: false } };
    const reads = mockReads(detail);
    let requestReads = 0;
    const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.endsWith("/planning-requests/request-1") && ++requestReads > 1) {
        if (refreshFailure) return Promise.reject(new TypeError("Connection unavailable"));
        return new Promise<Response>((resolve) => { finishRefresh = resolve; });
      }
      return reads(url, init);
    });
    vi.stubGlobal("fetch", fetcher);
    render(<PlanningConversation api={api} requestId="request-1" />);
    await screen.findByRole("status", { name: "Planning in progress" });
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(finishRefresh).toBeDefined());
    expect(screen.queryByText(/Updating this saved request/)).not.toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Planning in progress" })).toBeVisible();
    await act(async () => { finishRefresh?.(json(detail)); });
    refreshFailure = true;
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(await screen.findByText(/Planning status could not refresh/)).toBeVisible();
    expect(screen.queryByRole("status", { name: "Planning in progress" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry status" })).toBeEnabled();
    expect(fetcher.mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
  });

  it.each(["requester_authority_revoked", "demo_run_archived"])("explains confirmed access stop %s without offering a blind retry", async (code) => {
    vi.stubGlobal("fetch", mockReads({ ...request, interpretation_job: { ...request.interpretation_job!, last_error_code: code } }));
    render(<PlanningConversation api={api} requestId="request-1" />);
    expect(await screen.findByText("Planning needs an access change")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Review retry options" })).not.toBeInTheDocument();
    expect(screen.queryByRole("status", { name: "Planning in progress" })).not.toBeInTheDocument();
  });

  it.each(["authored_materialization_rejected", "candidate_materialization_rejected"])("does not misclassify legacy %s as a policy denial", async (code) => {
    vi.stubGlobal("fetch", mockReads({ ...request, interpretation_job: { ...request.interpretation_job!, last_error_code: code } }));
    render(<PlanningConversation api={api} requestId="request-1" />);
    expect(await screen.findByText(/could not verify the planning inputs/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Review retry options" })).toBeEnabled();
    expect(screen.queryByText("Planning needs an access change")).not.toBeInTheDocument();
  });

  it("restores a stopped request without creating work or presenting technical review as approval", async () => {
    const fetcher = mockReads(); vi.stubGlobal("fetch", fetcher);
    render(<PlanningConversation api={api} requestId="request-1" />);
    expect(await screen.findByText("Planning stopped — not awaiting your approval")).toBeVisible();
    expect(screen.getByText(request.original_request!)).toBeVisible();
    expect(screen.getByText(/AI response did not pass/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Prepare plan" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Review plan" })).not.toBeInTheDocument();
    expect(fetcher.mock.calls.every(([, options]) => !options.method || options.method === "GET")).toBe(true);
  });

  it.each(["model_output_truncated", "model_empty_output", "model_incomplete_output", "model_refusal"])("explains %s without fabricating clarification questions", async (code) => {
    vi.stubGlobal("fetch", mockReads({ ...request, interpretation_job: { ...request.interpretation_job!, last_error_code: code } }));
    render(<PlanningConversation api={{ ...api, accessToken: code }} requestId="request-1" />);
    await screen.findByText("Planning stopped — not awaiting your approval");
    expect(screen.queryByRole("button", { name: "Answer and continue" })).not.toBeInTheDocument();
    expect(screen.queryByText(/recorded error; do not create duplicate/)).not.toBeInTheDocument();
  });

  it.each([false, undefined])("does not offer a retry without server permission (%s)", async (canRetry) => {
    vi.stubGlobal("fetch", mockReads({ ...request, interpretation_job: { ...request.interpretation_job!, can_retry: canRetry } }));
    render(<PlanningConversation api={{ ...api, accessToken: String(canRetry) }} requestId="request-1" />);
    await screen.findByText("Planning stopped — not awaiting your approval");
    expect(screen.queryByRole("button", { name: "Review retry options" })).not.toBeInTheDocument();
  });

  it("retries only after a reason and cost confirmation, reusing the receipt after an ambiguous failure", async () => {
    const reads = mockReads();
    const fetcher = vi.fn().mockImplementation((input: string, options?: RequestInit) => options?.method === "POST" ? Promise.reject(new TypeError("Network interrupted")) : reads(input, options));
    vi.stubGlobal("fetch", fetcher);
    render(<PlanningConversation api={api} requestId="request-1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Review retry options" }));
    const retry = screen.getByRole("button", { name: "Retry saved request" });
    expect(retry).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Reason for retry"), { target: { value: "The host parser has been corrected." } });
    expect(retry).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: /Retry this saved request/ }));
    fireEvent.click(retry);
    expect(await screen.findByText("Network interrupted")).toBeVisible();
    fireEvent.click(retry);
    await waitFor(() => expect(fetcher.mock.calls.filter(([, options]) => options?.method === "POST")).toHaveLength(2));
    const writes = fetcher.mock.calls.filter(([, options]) => options?.method === "POST");
    expect(writes[0]![0]).toContain("/jobs/job-1/retry");
    expect(writes[0]![1].headers).toMatchObject({ "X-Demo-Run-ID": "run-1", "X-Demo-Actor-Session-ID": "actor-1", "X-Company-ID": "company-1", Authorization: "Bearer test-token" });
    expect(writes[0]![1].headers["Idempotency-Key"]).toBe(writes[1]![1].headers["Idempotency-Key"]);
    expect(JSON.parse(writes[0]![1].body)).toEqual({ reason: "The host parser has been corrected." });
  });

  it("preserves a successfully saved request when starting it fails", async () => {
    const reads = mockReads({ ...request, interpretation_job_state: null, interpretation_job: null });
    vi.stubGlobal("fetch", vi.fn().mockImplementation((input: string, options?: RequestInit) => {
      if (options?.method === "POST" && input.endsWith("/planning-requests")) return Promise.resolve(json({ request_id: "request-1" }));
      if (options?.method === "POST") return Promise.resolve(json({ detail: "Worker temporarily unavailable" }, 503));
      return reads(input, options);
    }));
    const onRequestChange = vi.fn();
    render(<PlanningConversation api={{ ...api, demoRunId: undefined, demoActorSessionId: undefined }} initialDraft="Prepare launch work." onRequestChange={onRequestChange} />);
    const prepare = await screen.findByRole("button", { name: "Prepare plan" });
    await waitFor(() => expect(prepare).toBeEnabled()); fireEvent.click(prepare);
    expect(await screen.findByRole("button", { name: "Start saved request" })).toBeVisible();
    expect(onRequestChange).toHaveBeenCalledWith("request-1");
    expect(screen.queryByRole("button", { name: "Prepare plan" })).not.toBeInTheDocument();
  });

  it("shows the exact proposal, independent evidence, separate approval decisions and explicit commit gate", async () => {
    const detail = { ...request, plan_id: "plan-1", interpretation_job_state: "succeeded", interpretation_job: null };
    const reads = mockReads(detail);
    const fetcher = vi.fn().mockImplementation((input: string, options?: RequestInit) => options?.method === "POST" ? Promise.resolve(json({})) : reads(input, options));
    vi.stubGlobal("fetch", fetcher);
    render(<PlanningConversation api={api} requestId="request-1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Review plan" }));
    const approve = await screen.findByRole("button", { name: "Approve this plan requirement" });
    await waitFor(() => expect(approve).toBeEnabled());
    expect(screen.getByRole("button", { name: "Approve this disclosure" })).toBeEnabled();
    expect(await screen.findByText("Iris")).toBeVisible();
    expect(screen.getByText("Reviewer: Maya")).toBeVisible();
    expect(screen.getByRole("button", { name: "Commit approved plan & assign work" })).toBeDisabled();
    fireEvent.click(approve);
    await waitFor(() => expect(fetcher.mock.calls.some(([, options]) => options?.method === "POST")).toBe(true));
    const write = fetcher.mock.calls.find(([, options]) => options?.method === "POST")!;
    expect(JSON.parse(write[1].body)).toMatchObject({ requirement_id: "approval-1", artifact_digest: "artifact-plan", binding: plan.binding });
    expect(fetcher.mock.calls.filter(([, options]) => options?.method === "POST")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Open task graph & rules" }));
    expect(window.location.hash).toBe("#/projects/project-1/graph?plan=plan-1&panel=rules");
  });

  it("never enables assignment for an unverified candidate, even if a stale plan claims it can commit", async () => {
    vi.stubGlobal("fetch", mockReads({ ...request, plan_id: "plan-1" }, { ...plan, can_commit: true }, { ...evidence, independent_validation: { ...evidence.independent_validation!, passed: false } }));
    render(<PlanningConversation api={api} planId="plan-1" />);
    const commit = await screen.findByRole("button", { name: "Commit approved plan & assign work" });
    fireEvent.click(screen.getByRole("checkbox", { name: /I have reviewed this exact schedule/ }));
    expect(commit).toBeDisabled();
    expect(screen.getByRole("button", { name: "Approve this disclosure" })).toBeDisabled();
  });

  it("removes cached plan and request content after a forbidden approval response", async () => {
    const reads = mockReads({ ...request, plan_id: "plan-1", interpretation_job_state: "succeeded", interpretation_job: null });
    const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => init?.method === "POST" ? Promise.resolve(json({ detail: "Your planning permission has changed." }, 403)) : reads(url, init));
    vi.stubGlobal("fetch", fetcher);
    render(<PlanningConversation api={api} requestId="request-1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Review plan" }));
    const approve = await screen.findByRole("button", { name: "Approve this plan requirement" });
    await waitFor(() => expect(approve).toBeEnabled());
    fireEvent.click(approve);
    await waitFor(() => expect(screen.queryByText(plan.request_summary)).not.toBeInTheDocument());
    expect(screen.queryByText(request.original_request!)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve this disclosure" })).not.toBeInTheDocument();
    expect(screen.getAllByText("Your planning permission has changed.").length).toBeGreaterThan(0);
  });

  it("drops the former actor's conversation immediately and ignores their late response", async () => {
    let finishOld: ((value: Response) => void) | undefined;
    const reads = mockReads();
    vi.stubGlobal("fetch", vi.fn().mockImplementation((input: string, options?: RequestInit) => {
      const actor = (options?.headers as Record<string, string>)["X-Demo-Actor-Session-ID"];
      if (input.endsWith("/planning-requests/request-1") && actor === "actor-1") return new Promise<Response>((resolve) => { finishOld = resolve; });
      if (input.endsWith("/planning-requests/request-1")) return Promise.resolve(json({ ...request, original_request: "Actor two visible request." }));
      return reads(input, options);
    }));
    const view = render(<PlanningConversation api={api} requestId="request-1" />);
    await waitFor(() => expect(finishOld).toBeDefined());
    view.rerender(<PlanningConversation api={{ ...api, demoActorSessionId: "actor-2" }} requestId="request-1" />);
    expect(await screen.findByText("Actor two visible request.")).toBeVisible();
    await act(async () => { finishOld?.(json({ ...request, original_request: "Old actor private request." })); });
    expect(screen.queryByText("Old actor private request.")).not.toBeInTheDocument();
  });

  it("uses Plan review as an inbox into the same Home conversation instead of another intake", async () => {
    vi.stubGlobal("fetch", mockReads());
    render(<PlanReviewWorkspace api={api} />);
    const item = await screen.findByRole("button", { name: /Prepare the authorised launch handoff/ });
    fireEvent.click(item);
    expect(window.location.hash).toBe("#/home?request=request-1");
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("requires deliberate approved-template selection for demo planning and uses the authoritative launch command", async () => {
    const approvedPrompt = "Prepare the approved Northstar launch using its typed authority.";
    const reads = mockReads({ ...request, original_request: approvedPrompt, intake_supported: true, interpretation_job_state: "queued", interpretation_job: { ...request.interpretation_job!, state: "queued", can_retry: false } });
    const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST" && url.endsWith("/demo/runs/run-1/launch-request")) return Promise.resolve(json({ request_id: "request-1" }));
      if (init?.method === "POST" && url.endsWith("/planning-requests/request-1/interpret")) return Promise.resolve(json({}));
      if (url.endsWith("/planning-context")) return Promise.resolve(json({ sources: [], requests: [], demo_intake: { kind: "northstar_launch", title: "Approved Northstar launch", original_request: approvedPrompt, description: "Only this typed launch request is supported in the demo." } }));
      return reads(url, init);
    });
    vi.stubGlobal("fetch", fetcher);
    render(<PlanningConversation api={api} initialDraft="Plan a different product launch." />);
    const useApproved = await screen.findByRole("button", { name: "Use approved Northstar request" });
    expect(screen.getByLabelText("What needs to happen?")).toHaveValue("Plan a different product launch.");
    expect(screen.getByRole("button", { name: "Prepare plan" })).toBeDisabled();
    fireEvent.click(useApproved);
    expect(screen.getByLabelText("What needs to happen?")).toHaveValue(approvedPrompt);
    expect(screen.queryByLabelText("Target deadline")).not.toBeInTheDocument();
    expect(fetcher.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Prepare plan" }));
    await waitFor(() => expect(fetcher.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(2));
    const writes = fetcher.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(writes[0]![0]).toContain("/demo/runs/run-1/launch-request");
    expect(writes[0]![1].body).toBe("{}");
    expect(writes[1]![0]).toContain("/planning-requests/request-1/interpret");
    expect(writes.every(([, init]) => init.headers["X-Demo-Actor-Session-ID"] === "actor-1")).toBe(true);
  });

  it.each(["unstarted", "failed", "questions"])("keeps legacy unsupported demo text readable without start, retry or approval controls (%s)", async (phase) => {
    const detail = { ...request, intake_supported: false, intake_limitation: "Only the approved Northstar launch has typed authority.", interpretation_job_state: phase === "unstarted" ? null : "review_required", clarifications: phase === "questions" ? [{ question_key: "owner", category: "authority", question: "Who owns this?", blocks_planning: true, status: "open" }] : [] };
    const fetcher = mockReads(detail); vi.stubGlobal("fetch", fetcher);
    render(<PlanningConversation api={api} requestId="request-1" />);
    expect(await screen.findByText("This request is not supported by the demo")).toBeVisible();
    expect(screen.getByText(request.original_request!)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Start saved request" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Review retry options" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Answer and continue" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Review plan" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Go to Home — Prepare the Northstar launch plan" }));
    expect(window.location.hash).toBe("#/home");
    expect(fetcher.mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
  });
});
