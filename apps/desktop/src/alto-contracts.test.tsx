import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { altoRequest, safeTarget, type AltoApiContext, type EmployeePreference } from "./alto-api";
import { NotificationsView, PreferenceConsentCard } from "./alto-pages";
import { SharedPreference } from "./alto-evidence";
import { useResource } from "./alto-state";
import { ProjectGraph } from "./alto-graph";
import { CalendarView } from "./alto-calendar-profile";

const api: AltoApiContext = { apiOrigin: "https://api.example.invalid", companyId: "company-1", accessToken: "private-token", demoRunId: "run-1", demoActorSessionId: "actor-1" };
const preference: EmployeePreference = { id: "preference-1", text: "Prefer uninterrupted morning focus time.", status: "draft", row_version: 3, manager_id: "maya-employee-id", manager_name: "Maya", shared_at: null };
afterEach(() => { cleanup(); vi.unstubAllGlobals(); window.location.hash = "/home"; });

describe("ALTO authenticated route contracts", () => {
  it("preserves checked selectors and the exact mutation version without leaking tokens into the URL", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response("{}")); vi.stubGlobal("fetch", fetcher);
    await altoRequest(api, "/tasks/task-1/approve-gate", { method: "POST", idempotencyKey: "receipt-1", body: { expected_row_version: 7, required_submission_id: "s4", required_submission_digest: "exact-digest" } });
    expect(fetcher).toHaveBeenCalledWith("https://api.example.invalid/v1/companies/company-1/tasks/task-1/approve-gate", expect.objectContaining({ headers: { Authorization: "Bearer private-token", "X-Company-ID": "company-1", "X-Demo-Run-ID": "run-1", "X-Demo-Actor-Session-ID": "actor-1", "Content-Type": "application/json", "Idempotency-Key": "receipt-1" }, body: JSON.stringify({ expected_row_version: 7, required_submission_id: "s4", required_submission_digest: "exact-digest" }) }));
    expect(safeTarget("https://example.org/exfiltrate", "/notifications")).toBe("/notifications");
    expect(safeTarget("//example.org", "/notifications")).toBe("/notifications");
    expect(safeTarget("/sources/source-1")).toBe("/sources/source-1");
  });

  it("omits archived run and actor selectors for a control-plane retry", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response("{}")); vi.stubGlobal("fetch", fetcher);
    await altoRequest({ ...api, demoRunId: undefined, demoActorSessionId: undefined }, "/demo/runs/run-1/archive-reset", { method: "POST", idempotencyKey: "reset-receipt", body: { expected_row_version: 2 } });
    const options = fetcher.mock.calls[0]?.[1] as RequestInit;
    expect(options.headers).not.toHaveProperty("X-Demo-Run-ID"); expect(options.headers).not.toHaveProperty("X-Demo-Actor-Session-ID");
    expect(options.headers).toHaveProperty("Authorization", "Bearer private-token");
  });

  it("loads exact historical candidate evidence and never presents a failed check as an approved schedule", async () => {
    const graph = { project: { id: "p1", title: "Recorded candidate", status: "planning", deadline: null }, nodes: [], edges: [], rules: [], plan_id: null, can_approve: false, check_status: "failed", approval_disabled_reason: "The exact candidate failed verification.", timezone: "UTC", candidate_history: [{ proposal_id: "d0-id", version: 1, author_kind: "authored_check", product_status: "failed", independent_validation_passed: false, candidate_digest: "immutable-d0-digest", created_at: "2026-09-21T00:00:00Z" }] };
    const fetcher = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(graph))).mockResolvedValueOnce(new Response(JSON.stringify({ ...graph, is_candidate_preview: true, selected_proposal_id: "d0-id" })));
    vi.stubGlobal("fetch", fetcher);
    render(<ProjectGraph api={api} projectId="p1"/>);
    const history = await screen.findByRole("combobox", { name: "Proposal history" });
    expect(screen.getByRole("option", { name: /authored check/i })).toBeInTheDocument();
    fireEvent.change(history, { target: { value: "d0-id" } });
    expect(await screen.findByText("immutable-d0-digest")).toBeVisible();
    expect(fetcher).toHaveBeenLastCalledWith(expect.stringContaining("/projects/p1/graph?proposal_id=d0-id"), expect.anything());
    expect(screen.getByRole("button", { name: "Approve plan" })).toBeDisabled();
    expect(screen.queryByText("Schedule checked")).not.toBeInTheDocument();
  });

  it("renders a strict checked summary, all canonical categories, and lazily loads raw Z3 evidence", async () => {
    const categories = [
      ["owner", "Owner"], ["working_hours", "Working hours"], ["busy_time", "Busy time"],
      ["effort", "Effort"], ["eligibility", "Eligibility"], ["dependencies", "Dependencies"],
      ["participants", "Participants"], ["handoffs", "Handoffs"], ["protected_time", "Protected time"],
      ["reviews", "Reviews"], ["deadlines", "Deadlines"], ["authorised_scope", "Authorised scope"],
    ];
    const rules = categories.map(([categoryKey, categoryTitle], index) => ({
      id: `result-${index + 1}`,
      rule_id: categoryKey === "protected_time" ? "protected.priya.tuesday" : `recorded.${categoryKey}`,
      title: categoryKey === "protected_time" ? "protected.priya.tuesday" : `recorded.${categoryKey}`,
      status: "pass",
      description: categoryKey === "protected_time" ? "Q1 ends exactly when Priya's protected interval begins." : `${categoryTitle} passed.`,
      formula: categoryKey === "protected_time" ? "[09:00, 11:00) does not overlap [11:00, 12:00)" : "recorded fixed values satisfy the admitted rule",
      source_label: "Northstar authored replay",
      source_version: "LAUNCH-07 · v1",
      candidate_values: categoryKey === "protected_time" ? {
        task: { task_key: "Q1", start_at: "2026-09-29T09:00:00-07:00", end_at: "2026-09-29T11:00:00-07:00" },
        protected_interval: { start_at: "2026-09-29T11:00:00-07:00", end_at: "2026-09-29T12:00:00-07:00", interval_semantics: "half-open" },
        overlap: false,
      } : null,
      category_key: categoryKey,
      category_title: categoryTitle,
      category_keys: [categoryKey],
      category_titles: [categoryTitle],
      encoding_version: "alto-fixed-candidate-compiler.v1",
      technical_expression_available: categoryKey === "protected_time",
    }));
    const graph = {
      project: { id: "northstar", title: "Northstar launch", status: "planning", deadline: null },
      nodes: [], edges: [], rules, plan_id: "plan-p1", can_approve: true, check_status: "CHECKED",
      approval_disabled_reason: null, timezone: "America/Los_Angeles", selected_proposal_id: "proposal-p1", is_candidate_preview: true,
      verification_summary: {
        proposal_id: "proposal-p1", author_kind: "authored_replay", product_status: "CHECKED", native_status: "sat",
        z3_version: "4.13.4", compiler_version: "alto-fixed-candidate-compiler.v1", verifier_version: "alto-fixed-candidate-verifier.v3",
        duration_ms: 12, required_rule_count: 12, covered_rule_count: 12, unverified_rule_count: 0,
        candidate_digest: "a".repeat(64), snapshot_digest: "b".repeat(64), digests_match: true,
        independent_validation_passed: true, validator_version: "alto-fixed-candidate-validator.v1", approval_status: "pending",
      },
    };
    const fetcher = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(graph)))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        rule_id: "protected.priya.tuesday",
        encoding_version: "alto-fixed-candidate-compiler.v1",
        technical_expression: "(and (<= 1 1) (<= 0 1))",
      })));
    vi.stubGlobal("fetch", fetcher);

    render(<ProjectGraph api={api} projectId="northstar" initialPanel="rules"/>);

    expect(await screen.findByText("SAT · CHECKED")).toBeVisible();
    expect(screen.getByText("12 / 12")).toBeVisible();
    expect(screen.getByText("Verification applies to this exact encoded snapshot. Independent validation and manager approval are separate.")).toBeVisible();
    for (const [, title] of categories) {
      expect(screen.getByRole("button", { name: `${title} check category, Passed` })).toBeVisible();
    }
    expect(fetcher).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Protected time check category, Passed" }));
    fireEvent.click(screen.getByRole("button", { name: "protected.priya.tuesday" }));
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    expect(fetcher).toHaveBeenLastCalledWith(
      expect.stringContaining("/projects/northstar/graph/rules/result-9?proposal_id=proposal-p1"),
      expect.anything(),
    );
    fireEvent.click(screen.getByText("Raw Z3 assertion"));
    expect(await screen.findByText("(and (<= 1 1) (<= 0 1))")).toBeVisible();
    expect(screen.getByText("[09:00, 11:00) does not overlap [11:00, 12:00)")).toBeVisible();
  });

  it("never labels stale digests or failed independent validation as checked", async () => {
    const graph = {
      project: { id: "northstar", title: "Northstar launch", status: "planning", deadline: null },
      nodes: [], edges: [], rules: [], plan_id: "plan-p1", can_approve: false, check_status: "CHECKED",
      approval_disabled_reason: "Evidence identity changed.", timezone: "UTC",
      verification_summary: {
        proposal_id: "proposal-p1", author_kind: "authored_replay", product_status: "CHECKED", native_status: "sat",
        z3_version: "4.13.4", compiler_version: "compiler", verifier_version: "verifier", duration_ms: 1,
        required_rule_count: 1, covered_rule_count: 1, unverified_rule_count: 0,
        candidate_digest: "a".repeat(64), snapshot_digest: "b".repeat(64), digests_match: false,
        independent_validation_passed: false, validator_version: "validator", approval_status: "pending",
      },
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(graph))));

    render(<ProjectGraph api={api} projectId="northstar" initialPanel="rules"/>);

    expect(await screen.findByText("SAT · DIGEST MISMATCH")).toBeVisible();
    expect(screen.queryByText("Schedule checked")).not.toBeInTheDocument();
    expect(screen.getByText("This proposal did not pass every recorded check")).toBeVisible();
  });

  it("keeps fallback provenance out of the locked judge presentation", async () => {
    const graph = { project: { id: "p1", title: "Recorded candidate", status: "planning", deadline: null }, nodes: [], edges: [], rules: [], plan_id: null, can_approve: false, check_status: "failed", approval_disabled_reason: "The exact candidate failed verification.", timezone: "UTC", candidate_history: [{ proposal_id: "p1-id", version: 2, author_kind: "authored_replay", product_status: "checked", independent_validation_passed: true, candidate_digest: "verified-p1-digest", created_at: "2026-09-21T00:00:00Z" }] };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(graph))));

    render(<ProjectGraph api={api} projectId="p1" locked/>);

    await screen.findByRole("combobox", { name: "Proposal history" });
    expect(screen.getByRole("option", { name: "v2 · checked" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /authored replay/i })).not.toBeInTheDocument();
  });

  it("shows exact recorded violations without chat and binds chat to that proposal", async () => {
    const graph = {
      project: { id: "project-with-violations", title: "Northstar launch", status: "planning", deadline: null },
      nodes: [], edges: [], plan_id: null, can_approve: false, check_status: "VIOLATIONS_FOUND",
      approval_disabled_reason: "The exact candidate failed verification.", timezone: "America/Los_Angeles",
      is_candidate_preview: true, selected_proposal_id: "proposal-with-violations",
      rules: [
        { id: "rule-1", title: "protected.priya.tuesday", status: "violation", description: "Priya's protected capacity overlaps the proposed QA work.", formula: "active + protected <= capacity", source_label: "Working hours and protected capacity", source_version: "fixture-1", candidate_values: null },
        { id: "rule-2", title: "deadline", status: "pass", description: "The deadline is met.", formula: "finish <= deadline", source_label: "Approved release brief", source_version: "fixture-1", candidate_values: null },
      ],
    };
    const thread = { id: "thread-1", messages: [], status: "completed", stage: null, error: null };
    const fetcher = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(graph)))
      .mockResolvedValueOnce(new Response(JSON.stringify(thread)))
      .mockResolvedValueOnce(new Response(JSON.stringify(thread)));
    vi.stubGlobal("fetch", fetcher);

    render(<ProjectGraph api={api} projectId="project-with-violations"/>);

    expect(await screen.findByText("1 recorded rule violation")).toBeVisible();
    expect(screen.getByText("Priya's protected capacity overlaps the proposed QA work.", { exact: false })).toBeVisible();
    expect(screen.getByText("Working hours and protected capacity", { exact: false })).toBeVisible();
    expect(screen.getByRole("button", { name: "Approve plan" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Review all recorded checks" }));
    expect(screen.getByRole("heading", { name: "Planning rules" })).toBeVisible();
    expect(screen.getByText("deterministic checks recorded for this exact proposal", { exact: false })).toBeVisible();

    fireEvent.change(screen.getByPlaceholderText("Ask ALTO about this plan…"), { target: { value: "What violations were found?" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(3));
    const createOptions = fetcher.mock.calls[1]?.[1] as RequestInit;
    expect(createOptions.body).toBe(JSON.stringify({ context: { kind: "project", id: "project-with-violations", proposal_id: "proposal-with-violations", label: "Northstar launch" } }));
  });

  it("does not open nonexistent task records from an uncommitted proposal preview", async () => {
    const graph = {
      project: { id: "p1", title: "Northstar launch", status: "planning", deadline: null },
      nodes: [{ id: "proposal-task-1", task_key: "Q2", title: "Accept readiness evidence", team: "qa", owner_name: "Priya", owner_employee_id: "priya-1", status: "proposed", start_at: "2026-09-29T17:00:00Z", finish_at: "2026-09-29T17:30:00Z", reviewer_name: null, summary: "Accept readiness evidence.", is_mine: false, can_work: false, row_version: 0 }],
      edges: [], rules: [], plan_id: "plan-1", can_approve: true, check_status: "CHECKED", approval_disabled_reason: null, timezone: "America/Los_Angeles", is_candidate_preview: true, selected_proposal_id: "proposal-1",
    };
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(graph))); vi.stubGlobal("fetch", fetcher);
    render(<ProjectGraph api={api} projectId="p1"/>);
    fireEvent.click(await screen.findByRole("button", { name: /Q2: Accept readiness evidence/ }));

    expect(screen.getByRole("status")).toHaveTextContent("approved and committed");
    expect(screen.getByRole("button", { name: "Brief available after commit" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Work available after commit" })).toBeDisabled();
  });

  it("keeps approved brief and task work actions available for committed records", async () => {
    const graph = {
      project: { id: "p1", title: "Northstar launch", status: "active", deadline: null },
      nodes: [{ id: "committed-task-1", task_key: "Q2", title: "Accept readiness evidence", team: "qa", owner_name: "Priya", owner_employee_id: "priya-1", status: "assigned", start_at: "2026-09-29T17:00:00Z", finish_at: "2026-09-29T17:30:00Z", reviewer_name: null, summary: "Accept readiness evidence.", is_mine: false, can_work: false, row_version: 1 }],
      edges: [], rules: [], plan_id: "plan-1", can_approve: false, check_status: "committed", approval_disabled_reason: "Approval is already recorded.", timezone: "America/Los_Angeles", is_candidate_preview: false,
    };
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(graph))); vi.stubGlobal("fetch", fetcher);
    render(<ProjectGraph api={api} projectId="p1"/>);
    fireEvent.click(await screen.findByRole("button", { name: /Q2: Accept readiness evidence/ }));

    const brief = screen.getByRole("button", { name: "Open approved brief" });
    const work = screen.getByRole("button", { name: "Inspect task work" });
    expect(brief).toBeEnabled(); expect(work).toBeEnabled();
    fireEvent.click(brief);
    expect(window.location.hash).toBe("#/tasks/committed-task-1");
  });

  it("uses the scenario week when workspace bootstrap arrives after the calendar first renders", async () => {
    const fetcher = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ timezone: "UTC", sources: [], items: [] }))));
    vi.stubGlobal("fetch", fetcher);
    const view = render(<CalendarView api={api}/>);
    await waitFor(() => expect(fetcher).toHaveBeenCalled());
    view.rerender(<CalendarView api={api} scenarioNow="2026-09-28T09:00:00Z"/>);
    await waitFor(() => expect(fetcher).toHaveBeenLastCalledWith(expect.stringContaining("start=2026-09-27T00%3A00%3A00Z"), expect.anything()));
    expect(screen.getByRole("button", { name: /Mon.*28/ })).toBeVisible();
  });

  it("removes a previous actor's private projection immediately and ignores a late reply", async () => {
    let finishOld: ((response: Response) => void) | undefined;
    const fetcher = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ text: "Actor one private content" }))).mockImplementationOnce(() => new Promise<Response>((resolve) => { finishOld = resolve; })).mockResolvedValueOnce(new Response(JSON.stringify({ text: "Actor two projection" })));
    vi.stubGlobal("fetch", fetcher);
    const { result, rerender } = renderHook(({ context }) => useResource<{ text: string }>(context, "/me/employee-preferences"), { initialProps: { context: api } });
    await waitFor(() => expect(result.current.data?.text).toBe("Actor one private content"));
    act(() => result.current.refresh()); await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    rerender({ context: { ...api, demoActorSessionId: "actor-2" } });
    expect(result.current.data).toBeNull();
    await waitFor(() => expect(result.current.data?.text).toBe("Actor two projection"));
    await act(async () => { finishOld?.(new Response(JSON.stringify({ text: "Late actor one content" }))); });
    expect(result.current.data?.text).toBe("Actor two projection");
    const oldOptions = fetcher.mock.calls[1]?.[1] as RequestInit; expect(oldOptions.signal?.aborted).toBe(true);
  });
});

describe("explicit preference consent", () => {
  it("closing a private suggestion never sends a share or any other mutation", () => {
    const fetcher = vi.fn(); vi.stubGlobal("fetch", fetcher); const onClose = vi.fn();
    render(<PreferenceConsentCard api={api} preference={preference} onClose={onClose} onSaved={vi.fn()}/>);
    fireEvent.click(screen.getByRole("button", { name: "Close without sharing" }));
    expect(onClose).toHaveBeenCalledOnce(); expect(fetcher).not.toHaveBeenCalled();
  });
  it("shares only the exact version and explicitly named audience", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response("{}")); vi.stubGlobal("fetch", fetcher); const onSaved = vi.fn();
    render(<PreferenceConsentCard api={api} preference={preference} onClose={vi.fn()} onSaved={onSaved}/>);
    fireEvent.click(screen.getByRole("button", { name: "Share with Maya" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
    expect(fetcher).toHaveBeenCalledWith(expect.stringContaining("/me/employee-preferences/preference-1/share"), expect.objectContaining({ body: JSON.stringify({ expected_row_version: 3, manager_id: "maya-employee-id" }) }));
  });
  it("keeps private without manufacturing an audience and retains a stale draft on conflict", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Preference changed. Reload the exact version." }), { status: 409 })); vi.stubGlobal("fetch", fetcher); const onClose = vi.fn();
    render(<PreferenceConsentCard api={api} preference={preference} onClose={onClose} onSaved={vi.fn()}/>);
    fireEvent.click(screen.getByRole("button", { name: "Keep private" }));
    expect(await screen.findByText("Preference changed. Reload the exact version.")).toBeVisible();
    expect(fetcher).toHaveBeenCalledWith(expect.stringContaining("/keep-private"), expect.objectContaining({ body: JSON.stringify({ expected_row_version: 3 }) }));
    expect(onClose).not.toHaveBeenCalled(); expect(screen.getByText(preference.text)).toBeVisible();
  });
  it("opens id-only notification evidence and respects revoked consent rather than caching the private text", async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ notifications: [{ notification_id: "n1", message_key: "employee_preference_shared", subject_type: "employee_preference", subject_id: "preference-1", created_at: "2026-09-25T12:00:00Z", seen_at: null }] }))).mockResolvedValueOnce(new Response(JSON.stringify({ detail: "This preference is no longer shared with you." }), { status: 403 }));
    vi.stubGlobal("fetch", fetcher);
    const notifications = render(<NotificationsView api={api}/>);
    fireEvent.click(await screen.findByRole("button", { name: "View details" }));
    expect(window.location.hash).toBe("#/preferences/preference-1"); notifications.unmount();
    render(<SharedPreference api={api} preferenceId="preference-1"/>);
    expect(await screen.findByText("This preference is no longer shared with you.")).toBeVisible();
    expect(screen.queryByText(preference.text)).not.toBeInTheDocument();
  });
});
