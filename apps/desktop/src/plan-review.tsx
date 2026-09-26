import { useCallback, useEffect, useMemo, useState } from "react";

import {
  approveRequirement,
  commitPlan,
  createPlanningRequest,
  getPlan,
  getPlanEvidence,
  getPendingReviews,
  getPlanningContext,
  getPlanningRequest,
  reviewSubmission,
  type AuthorisedApiContext,
  type PlanEvidence,
  type PlanningContext,
  type PlanningRequestDetail,
  type PlanReview,
  type PendingReview,
} from "./api-client";

interface PlanReviewWorkspaceProps {
  api?: AuthorisedApiContext;
}

const DEFAULT_REQUEST =
  "Coordinate the approved software release and internal onboarding work. Use the shared " +
  "technical specialist without exposing either team's private context, and preserve a " +
  "reviewable handoff.";

function displayTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function pipelineStages(request: PlanningRequestDetail | null) {
  return [
    ["Interpretation", request?.interpretation_job_state ?? "waiting"],
    ["Trusted constraints", request?.materialization_job_state ?? "waiting"],
    ["Z3 + validation", request?.planning_job_state ?? "waiting"],
    ["Human approval", request?.plan_id ? "ready" : "waiting"],
  ] as const;
}

export function PlanReviewWorkspace({ api }: PlanReviewWorkspaceProps) {
  const [planningContext, setPlanningContext] = useState<PlanningContext | null>(null);
  const [request, setRequest] = useState<PlanningRequestDetail | null>(null);
  const [plan, setPlan] = useState<PlanReview | null>(null);
  const [evidence, setEvidence] = useState<PlanEvidence | null>(null);
  const [pendingReviews, setPendingReviews] = useState<PendingReview[]>([]);
  const [prompt, setPrompt] = useState(DEFAULT_REQUEST);
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadPlan = useCallback(async (context: AuthorisedApiContext, planId: string) => {
    const [nextPlan, nextEvidence] = await Promise.all([
      getPlan(context, planId),
      getPlanEvidence(context, planId),
    ]);
    setPlan(nextPlan);
    setEvidence(nextEvidence);
  }, []);

  const loadRequest = useCallback(
    async (context: AuthorisedApiContext, requestId: string) => {
      const value = await getPlanningRequest(context, requestId);
      setRequest(value);
      if (value.plan_id) await loadPlan(context, value.plan_id);
      return value;
    },
    [loadPlan],
  );

  useEffect(() => {
    if (!api) return;
    let active = true;
    void getPlanningContext(api)
      .then(async (value) => {
        if (!active) return;
        setPlanningContext(value);
        setSelectedSources(value.sources.map((source) => source.source_id));
        const latest = value.requests[0];
        if (latest) await loadRequest(api, latest.request_id);
      })
      .catch((value: unknown) => {
        if (active) setError(value instanceof Error ? value.message : "Planning state failed");
      });
    return () => { active = false; };
  }, [api, loadRequest]);

  useEffect(() => {
    if (!api) return;
    let active = true;
    const refresh = () => {
      void getPendingReviews(api)
        .then((value) => { if (active) setPendingReviews(value); })
        .catch(() => undefined);
    };
    refresh();
    const timer = window.setInterval(refresh, 5_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [api]);

  useEffect(() => {
    if (!api || !request || request.plan_id) return;
    const states = [
      request.interpretation_job_state,
      request.materialization_job_state,
      request.planning_job_state,
    ];
    if (states.some((state) => ["dead_letter", "review_required", "cancelled"].includes(state ?? ""))) return;
    const timer = window.setInterval(() => {
      void loadRequest(api, request.request_id).catch((value: unknown) => {
        setError(value instanceof Error ? value.message : "Pipeline refresh failed");
      });
    }, 1_500);
    return () => window.clearInterval(timer);
  }, [api, loadRequest, request]);

  const allSourcesSelected = useMemo(
    () => planningContext?.sources.length === selectedSources.length,
    [planningContext, selectedSources],
  );

  async function submitRequest() {
    if (!api || !prompt.trim() || selectedSources.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const created = await createPlanningRequest(api, {
        originalRequest: prompt.trim(),
        sourceIds: selectedSources,
        requestedDeadline: "",
        requestedPriorityKey: "high",
      });
      setPlan(null);
      setEvidence(null);
      await loadRequest(api, created.request_id);
    } catch (value) {
      setError(value instanceof Error ? value.message : "Planning request failed");
    } finally {
      setBusy(false);
    }
  }

  async function approveAll() {
    if (!api || !plan) return;
    setBusy(true);
    setError(null);
    try {
      for (const requirement of plan.requirements.filter((item) => item.status === "pending")) {
        await approveRequirement(api, plan, requirement);
      }
      await loadPlan(api, plan.plan_id);
    } catch (value) {
      setError(value instanceof Error ? value.message : "Approval failed");
    } finally {
      setBusy(false);
    }
  }

  async function applyPlan() {
    if (!api || !plan) return;
    setBusy(true);
    setError(null);
    try {
      await commitPlan(api, plan);
      await loadPlan(api, plan.plan_id);
    } catch (value) {
      setError(value instanceof Error ? value.message : "Commit failed");
    } finally {
      setBusy(false);
    }
  }

  async function decideSubmission(
    item: PendingReview,
    decision: "accepted" | "revision_requested",
  ) {
    if (!api) return;
    setBusy(true);
    setError(null);
    try {
      await reviewSubmission(api, item, decision);
      setPendingReviews(await getPendingReviews(api));
    } catch (value) {
      setError(value instanceof Error ? value.message : "Submission review failed");
    } finally {
      setBusy(false);
    }
  }

  if (!api) {
    return (
      <section className="empty-workspace">
        <span className="eyebrow">Authorised connection required</span>
        <h2>Sign in to create and review a real plan.</h2>
        <p>The manager surface loads no fixture records into the UI. Configure Supabase, select the demo company and authenticate to use the connected workflow.</p>
      </section>
    );
  }

  return (
    <>
      <section className="intake-panel" aria-labelledby="planning-intake-title">
        <div>
          <span className="eyebrow">Authorised change intake</span>
          <h2 id="planning-intake-title">Turn a decision into a checked plan.</h2>
          <p>Selected sources are pinned by exact version. Fixture mode replaces only Gemini; every later boundary remains production code.</p>
        </div>
        <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={4} aria-label="Planning request" />
        <fieldset className="source-selector">
          <legend>Authoritative source versions</legend>
          {planningContext?.sources.map((source) => (
            <label key={source.source_id}>
              <input
                type="checkbox"
                checked={selectedSources.includes(source.source_id)}
                onChange={(event) => setSelectedSources((current) =>
                  event.target.checked
                    ? [...current, source.source_id]
                    : current.filter((id) => id !== source.source_id))}
              />
              <span><strong>{source.title}</strong><small>{source.classification} · {source.source_kind}</small></span>
            </label>
          ))}
        </fieldset>
        <button className="primary-action" disabled={busy || !allSourcesSelected || !prompt.trim()} onClick={() => void submitRequest()}>
          {busy ? "Working…" : "Create checked plan"}
        </button>
        {error && <p className="inline-error" role="alert">{error}</p>}
      </section>

      {request && (
        <section className="pipeline-panel" aria-label="Planning pipeline">
          {pipelineStages(request).map(([label, state], index) => (
            <div key={label} className={`pipeline-stage ${state}`}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <strong>{label}</strong>
              <small>{state}</small>
            </div>
          ))}
          {request.clarifications.map((item) => (
            <p className="inline-error" key={item.question_key}>{item.question}</p>
          ))}
        </section>
      )}

      {plan && (
        <section className="live-plan" aria-labelledby="live-plan-title">
          <header className="plan-heading">
            <div>
              <span className="eyebrow">Exact proposal · {plan.classification}</span>
              <h2 id="live-plan-title">{plan.request_summary}</h2>
            </div>
            <span className={`plan-status ${plan.status}`}>{plan.status}</span>
          </header>
          <div className="schedule-table" role="table" aria-label="Proposed schedule">
            {plan.tasks.map((task) => (
              <div className="schedule-row" role="row" key={task.task_id}>
                <span role="cell"><strong>{task.title}</strong><small>{task.task_key}</small></span>
                <span role="cell">{displayTime(task.start_at)}</span>
                <span role="cell">{displayTime(task.finish_at)}</span>
                <span role="cell">{task.owner_resource_id?.slice(0, 8) ?? "Unassigned"}</span>
              </div>
            ))}
          </div>
          <div className="evidence-grid">
            <article><span className="eyebrow">Independent solver evidence</span><strong>{evidence?.solver.classification}</strong><p>{evidence?.solver.raw_status} · {evidence?.solver.termination} · {evidence?.solver.runtime_ms} ms</p></article>
            <article><span className="eyebrow">Validated constraints</span><strong>{evidence?.constraints.length ?? 0} admitted</strong><p>Unknown families and unconfirmed evidence fail before compilation.</p></article>
            <article><span className="eyebrow">Exact approval binding</span><strong>{plan.requirements.filter((item) => item.status === "approved").length}/{plan.requirements.length} approved</strong><p>Planning and employee disclosure are separate requirements.</p></article>
          </div>
          <div className="requirement-list">
            {plan.requirements.map((requirement) => (
              <div key={requirement.requirement_id}>
                <span className={`requirement-state ${requirement.status}`}>{requirement.status}</span>
                <strong>{requirement.kind.replaceAll("_", " ")}</strong>
                <p>{requirement.reason}</p>
              </div>
            ))}
          </div>
          <footer className="plan-actions">
            <button className="secondary-action" disabled={busy || plan.status === "committed" || plan.requirements.every((item) => item.status === "approved")} onClick={() => void approveAll()}>Approve exact plan & disclosure</button>
            <button className="primary-action" disabled={busy || !plan.can_commit || plan.status === "committed"} onClick={() => void applyPlan()}>{plan.status === "committed" ? "Committed" : "Commit approved plan"}</button>
          </footer>
        </section>
      )}

      {pendingReviews.length > 0 && (
        <section className="review-queue" aria-labelledby="review-queue-title">
          <header><span className="eyebrow">Accountable work acceptance</span><h2 id="review-queue-title">Pending exact-version reviews</h2></header>
          {pendingReviews.map((item) => (
            <article key={item.submission_id}>
              <div><strong>{item.task_title}</strong><small>{item.submitting_employee_name} · version {item.version}</small></div>
              <p>{item.narrative}</p>
              <div className="review-actions">
                <button className="secondary-action" disabled={busy} onClick={() => void decideSubmission(item, "revision_requested")}>Request revision</button>
                <button className="primary-action" disabled={busy} onClick={() => void decideSubmission(item, "accepted")}>Accept exact version</button>
              </div>
            </article>
          ))}
        </section>
      )}
    </>
  );
}
