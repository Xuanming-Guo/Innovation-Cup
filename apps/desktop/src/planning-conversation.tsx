import { useEffect, useRef, useState } from "react";
import {
  answerPlanningClarifications, approveRequirement, commitPlan, createPlanningRequest, createNorthstarPlanningRequest,
  PlanningStartError, retryPlanningJob, startPlanningInterpretation,
  type AuthorisedApiContext, type PlanEvidence, type PlanningContext,
  type PlanningRequestDetail, type PlanningStageJob, type PlanReview,
} from "./api-client";
import { type Project, type ProjectGraphData } from "./alto-api";
import { dateTime, humanize, navigate, useResource } from "./alto-state";
import { AltoLogo, Badge, ErrorNotice, Loading } from "./alto-ui";
import "./planning-conversation.css";

export interface PlanningConversationProps {
  api?: AuthorisedApiContext;
  requestId?: string | null;
  planId?: string | null;
  initialDraft?: string;
  lockedDemo?: boolean;
  onRequestChange?: (requestId: string) => void;
  onClose?: () => void;
}

const TERMINAL = ["review_required", "dead_letter", "cancelled"];
const RUNNING = ["queued", "leased", "running", "retry_scheduled"];
const POLICY_STOPS = ["requester_authority_revoked", "demo_run_archived"];
const FAILURE_TEXT: Record<string, string> = {
  model_invalid_output: "The AI response did not pass the required format or validation checks.",
  model_output_truncated: "The AI response stopped before it finished. No complete plan was produced.",
  model_empty_output: "The AI returned no usable response. No plan was produced.",
  model_incomplete_output: "The AI response was incomplete. No complete plan was produced.",
  interpretation_contract_rejected: "The AI output still did not match the approved task requirements. Check the recorded cause before starting a corrected request.",
  interpretation_repair_budget_exhausted: "ALTO reached this request's automatic attempt limit. No further AI call will run for this interpretation.",
  interpretation_authority_unavailable: "The approved sources or planning authority could not be verified. Check workspace access and source versions before continuing.",
  fixed_plan_not_verified: "ALTO did not produce a schedule that passed every required check. No work has been assigned.",
  fixed_planning_state_conflict: "The saved planning state no longer matched the inputs needed to continue safely. Ask your host operator to check the recorded conflict before another attempt.",
  planning_cancelled_fenced_or_ambiguous: "ALTO could not safely confirm the result of this planning attempt. It stopped to avoid repeating work. Ask your host operator to check the saved run.",
  model_refusal: "The AI declined this request. Review the request and its permitted sources before trying again.",
  requester_authority_revoked: "The authority needed to process this request is no longer available. Ask your workspace administrator to review access.",
  demo_run_archived: "This demo run was archived. Open an active run to continue working.",
  authored_materialization_rejected: "ALTO could not verify the planning inputs for this request. The host operator needs to check the recorded cause before another attempt.",
  candidate_materialization_rejected: "ALTO could not verify the planning inputs for this request. The host operator needs to check the recorded cause before another attempt.",
};

const MODEL_ATTEMPT_FAILURE_TEXT: Record<string, string> = {
  model_output_truncated: "The latest AI attempt was cut off before it finished. That attempt did not produce a complete proposal.",
  model_empty_output: "The latest AI attempt returned no usable response.",
  model_incomplete_output: "The latest AI attempt returned an incomplete proposal.",
  model_invalid_output: "The latest AI attempt did not pass the required response format checks.",
  model_refusal: "The provider declined the latest AI attempt.",
  model_timeout: "The latest AI attempt timed out. Its provider result could not be confirmed.",
  model_throttled: "The provider rate-limited the latest AI attempt.",
  model_transient_error: "The provider was temporarily unavailable for the latest AI attempt.",
  model_permanent_error: "The provider rejected the latest AI attempt. Ask the host operator to check the provider configuration.",
  model_bad_request: "The provider rejected the latest request configuration. Ask the host operator to check it before another attempt.",
  model_auth_rejected: "The provider rejected the credential used for the latest AI attempt. Check the bound credential in Settings.",
  model_forbidden: "The bound credential did not have permission for the latest AI attempt. Check its provider permissions.",
  model_not_found: "The selected model was unavailable for the latest AI attempt. Ask the host operator to check the configured model.",
  prior_work_version_changed: "The latest AI proposal did not match the recorded version of existing work. ALTO rejected it to protect that work.",
  admitted_task_facts_changed: "The latest AI proposal changed approved task details, so ALTO rejected it.",
  unchanged_candidate: "The latest AI attempt repeated a proposal without resolving its recorded issues.",
  revision_outside_violation_scope: "The latest AI revision changed work outside the permitted repair scope, so ALTO rejected it.",
  revision_changed_admitted_work: "The latest AI revision changed approved work rather than only its permitted schedule details, so ALTO rejected it.",
};

function failureText(job: PlanningStageJob | undefined | null): string {
  if (job?.state === "cancelled") return "Processing was cancelled. There is no plan to approve from this stage.";
  return FAILURE_TEXT[job?.last_error_code ?? ""] ?? "Processing stopped before a reviewable plan was ready. The details below identify the stopped stage.";
}

function stageText(state: string | null | undefined): string {
  if (!state) return "Not started";
  if (TERMINAL.includes(state)) return state === "cancelled" ? "Cancelled" : "Stopped — needs attention";
  return ({ succeeded: "Complete", queued: "Waiting to start", leased: "Working", running: "Working", retry_scheduled: "Waiting for a scheduled retry" } as Record<string, string>)[state] ?? humanize(state);
}

function activeStageSummary(label: string, state: string | null | undefined): string {
  if (state === "queued") return `${label} is queued and waiting to start.`;
  if (state === "retry_scheduled") return `${label} is waiting for its recorded retry.`;
  if (label === "Understanding your request") return "ALTO is checking the request's goal, deadline and permitted planning scope.";
  if (label === "Checking sources and constraints") return "ALTO is checking the authorised sources, people, commitments and constraints needed for the plan.";
  return "ALTO is building the proposed schedule and checking it against the recorded constraints.";
}

function defaultDeadline(): string {
  const value = new Date();
  value.setDate(value.getDate() + 7);
  value.setHours(17, 0, 0, 0);
  return new Date(value.getTime() - value.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

// Remount on an authority boundary, before a previous actor's response can render.
export function PlanningConversation(props: PlanningConversationProps) {
  const api = props.api;
  const scope = JSON.stringify([api?.apiOrigin, api?.companyId, api?.authUserId ?? api?.accessToken, api?.demoRunId, api?.demoActorSessionId, props.requestId, props.planId, props.lockedDemo]);
  return <Conversation key={scope} {...props} />;
}

function Conversation({ api, requestId, planId, initialDraft = "", lockedDemo = false, onRequestChange, onClose }: PlanningConversationProps) {
  const [currentId, setCurrentId] = useState(requestId ?? null);
  const [draft, setDraft] = useState(initialDraft);
  const [deadline, setDeadline] = useState(defaultDeadline);
  const [sourceChoice, setSourceChoice] = useState<string[] | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [commandBusy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reviewing, setReviewing] = useState(Boolean(planId));
  const [retryOpen, setRetryOpen] = useState(false);
  const [retryReason, setRetryReason] = useState("");
  const [retryConfirmed, setRetryConfirmed] = useState(false);
  const operation = useRef(false);
  const submissionKey = useRef<{ payload: string; key: string } | null>(null);
  const recoveryKey = useRef<{ payload: string; key: string } | null>(null);
  const successorKey = useRef<{ requestId: string; key: string } | null>(null);
  const clarificationKey = useRef<{ payload: string; key: string } | null>(null);
  const context = useResource<PlanningContext>(api, "/planning-context");
  const isDemo = Boolean(api?.demoRunId);
  const demoIntake = context.data?.demo_intake;
  const supportedDraft = !isDemo || Boolean(demoIntake && draft.trim() === demoIntake.original_request);
  const requestResource = useResource<PlanningRequestDetail>(api, currentId ? `/planning-requests/${encodeURIComponent(currentId)}` : null);
  const request = requestResource.data;
  const unsupportedRequest = Boolean(request && (request.intake_supported === false || (isDemo && demoIntake && request.original_request?.trim() !== demoIntake.original_request)));
  const selectedPlanId = planId ?? request?.plan_id;
  const planResource = useResource<PlanReview>(api, selectedPlanId ? `/plans/${encodeURIComponent(selectedPlanId)}` : null);
  const plan = planResource.data;
  const evidence = useResource<PlanEvidence>(api, reviewing && selectedPlanId ? `/plans/${encodeURIComponent(selectedPlanId)}/evidence` : null);
  const sources = sourceChoice ?? context.data?.sources.map((source) => source.source_id) ?? [];
  const summary = request?.original_request ?? context.data?.requests.find((item) => item.request_id === currentId)?.original_request ?? plan?.request_summary;
  const stages = request ? [
    { label: "Understanding your request", state: request.interpretation_job_state, job: request.interpretation_job },
    { label: "Checking sources and constraints", state: request.materialization_job_state, job: request.materialization_job },
    { label: "Checking the proposed schedule", state: request.planning_job_state, job: request.planning_job },
  ] : [];
  const failedStage = stages.find((stage) => TERMINAL.includes(stage.state ?? ""));
  const failedJob = failedStage?.job;
  const latestModelFailure = MODEL_ATTEMPT_FAILURE_TEXT[failedJob?.latest_model_error_code ?? ""];
  const policyStop = POLICY_STOPS.includes(failedJob?.last_error_code ?? "");
  const guaranteedNorthstarRecovery = Boolean(
    lockedDemo
    && isDemo
    && failedStage?.label === "Checking the proposed schedule"
    && !policyStop
  );
  const retryAllowed = !unsupportedRequest && !policyStop && failedJob?.can_retry === true && ["review_required", "dead_letter"].includes(failedJob.state) && failedJob.attempt_count < 20;
  const requestUnavailable = requestResource.isStale || Boolean(requestResource.error);
  const busy = commandBusy || requestUnavailable || (!currentId && !planId && context.isStale) || planResource.isStale || evidence.isStale;
  const questions = request?.clarifications.filter((item) => item.status === "open" && item.blocks_planning) ?? [];
  const canProgress = Boolean(request && !unsupportedRequest && !request.plan_id && !planId && !failedStage && questions.length === 0);
  const runningStage = canProgress ? stages.find((stage) => RUNNING.includes(stage.state ?? "")) : undefined;
  const finishedWithoutPlan = canProgress && request?.planning_job_state === "succeeded";
  // Stage jobs are persisted separately. Keep read-only polling across a successful
  // handoff even if the next job has not appeared yet; never enqueue work here.
  const awaitingNextStage = canProgress && !finishedWithoutPlan && !runningStage && !["failed", "clarification_required", "cancelled"].includes(request?.status ?? "") && stages.some((stage) => stage.state === "succeeded");
  const shouldPoll = Boolean(runningStage || awaitingNextStage);
  const active = Boolean(runningStage && !requestResource.error);
  const completedStages = stages.filter((stage) => stage.state === "succeeded").map((stage) => stage.label);
  const progressNow = unsupportedRequest
    ? "This request is preserved, but it is outside the demo's recorded planning authority."
    : requestResource.error
      ? "The request is saved, but its latest processing state is temporarily unavailable."
      : plan
        ? plan.status === "committed"
          ? "The exact approved plan is committed and its work has been assigned."
          : "The automated checks produced a proposal that is ready for your review."
        : questions.length
          ? "Processing is paused because ALTO needs a recorded decision from you."
          : failedStage
            ? `${failedStage.label} stopped before a reviewable plan was ready.`
            : active && runningStage
              ? activeStageSummary(runningStage.label, runningStage.state)
              : awaitingNextStage
                ? "The latest recorded stage is complete. ALTO is waiting for the next durable planning stage."
                : finishedWithoutPlan
                  ? "The recorded stages finished, but no reviewable plan is linked to this request."
                  : !request?.interpretation_job_state
                    ? "Your request is saved, but processing has not started."
                    : "The latest saved planning state is shown below.";
  const progressNext = unsupportedRequest
    ? "Return Home and choose the approved Northstar planning request."
    : requestResource.error
      ? "Reconnect and refresh the saved request to confirm its latest state."
      : plan
        ? plan.status === "committed"
          ? "Open the assigned work or calendar when you are ready."
          : "Review the exact tasks, schedule, checks and approval requirements."
        : questions.length
          ? "Answer the recorded question below so planning can continue."
          : failedStage
            ? policyStop
              ? "Ask your workspace administrator to review the required access."
              : guaranteedNorthstarRecovery
                ? "Prepare a new Northstar plan below. This failed request will remain in its history."
              : retryAllowed
                ? "Review the recorded cause and retry options below."
                : "Ask your host operator to investigate this saved request."
            : active || awaitingNextStage
              ? "No action is needed while this runs. You can leave and return to the same saved request."
              : finishedWithoutPlan
                ? "Refresh once, then ask your host operator to inspect the saved request if no plan appears."
                : !request?.interpretation_job_state
                  ? "Start the saved request when you are ready for Live processing."
                  : "Refresh the saved request to confirm its next recorded step.";

  useEffect(() => {
    if (!shouldPoll) return;
    const timer = window.setInterval(requestResource.refresh, 2500);
    return () => window.clearInterval(timer);
  }, [shouldPoll, requestResource.refresh]);

  async function command(action: () => Promise<void>) {
    if (operation.current) return;
    operation.current = true;
    setBusy(true);
    setError(null);
    try { await action(); }
    catch (value) {
      if (value instanceof PlanningStartError) {
        setCurrentId(value.requestId);
        onRequestChange?.(value.requestId);
      }
      setError(value instanceof Error ? value.message : "This action could not be completed.");
    } finally { operation.current = false; setBusy(false); }
  }

  function selectRequest(id: string) {
    setCurrentId(id);
    setAnswers({});
    setReviewing(false);
    onRequestChange?.(id);
  }

  async function create() {
    if (!api || !draft.trim() || !supportedDraft || (!isDemo && (!sources.length || !deadline)) || context.isStale || context.error) return;
    const payload = JSON.stringify([draft.trim(), sources, deadline]);
    if (submissionKey.current?.payload !== payload) submissionKey.current = { payload, key: `planning-request:${crypto.randomUUID()}` };
    const created = isDemo
      ? await createNorthstarPlanningRequest(api, submissionKey.current.key)
      : await createPlanningRequest(api, { originalRequest: draft.trim(), sourceIds: sources, requestedDeadline: deadline, requestedPriorityKey: "", idempotencyKey: submissionKey.current.key });
    selectRequest(created.request_id);
  }

  async function retry() {
    if (!api || !failedJob || !retryAllowed || requestUnavailable || !retryReason.trim() || !retryConfirmed) return;
    const payload = JSON.stringify([failedJob.job_id, retryReason.trim()]);
    if (recoveryKey.current?.payload !== payload) recoveryKey.current = { payload, key: `planning-retry:${crypto.randomUUID()}` };
    await retryPlanningJob(api, failedJob.job_id, retryReason, recoveryKey.current.key);
    recoveryKey.current = null;
    setRetryOpen(false);
    setRetryConfirmed(false);
    requestResource.refresh();
  }

  async function prepareNorthstarSuccessor() {
    if (!api || !currentId || !guaranteedNorthstarRecovery || requestUnavailable) return;
    if (successorKey.current?.requestId !== currentId) {
      successorKey.current = { requestId: currentId, key: `planning-successor:${crypto.randomUUID()}` };
    }
    const created = await createNorthstarPlanningRequest(api, successorKey.current.key);
    successorKey.current = null;
    selectRequest(created.request_id);
  }

  if (!api) return <p className="alto-info-banner">Sign in to prepare and review an authorised plan.</p>;

  return <section className="alto-planning-conversation" aria-label="Planning conversation">
    <header className="alto-planning-header"><div><AltoLogo compact /><h2>{currentId || planId ? "Your planning request" : "Plan work with ALTO"}</h2></div><div>{(currentId || planId) && <button className="alto-text-button" onClick={() => { requestResource.refresh(); planResource.refresh(); }}>Refresh</button>}{onClose && <button className="alto-text-button" onClick={onClose}>Back to Home</button>}</div></header>
    <ErrorNotice error={error} />
    {request && requestResource.error ? <p className="alto-planning-connection" role="status">Planning status could not refresh. Last saved progress is shown.<button className="alto-text-button" onClick={requestResource.refresh}>Retry status</button></p> : <ErrorNotice error={requestResource.error} retry={requestResource.refresh} />}
    <ErrorNotice error={planResource.error} retry={planResource.refresh} />
    {!currentId && !planId ? <form className="alto-plan-intake" onSubmit={(event) => { event.preventDefault(); void command(create); }}>
      <p>Describe the outcome you need. ALTO will prepare a proposal; nothing is assigned until you review and commit it.</p>
      {isDemo && <div className="alto-info-banner alto-demo-intake"><strong>This demo supports the approved Northstar launch only.</strong><p>{demoIntake?.description ?? "Free-form demo planning is not supported. Ask a question remains available for other requests."}</p>{demoIntake && <button type="button" className="alto-secondary" onClick={() => setDraft(demoIntake.original_request)}>Use approved Northstar request</button>}{!supportedDraft && <p>Your draft has not been changed or sent. Choose the approved request to prepare a supported demo plan.</p>}</div>}
      <label className="alto-field">What needs to happen?<textarea rows={4} maxLength={8000} value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Prepare the launch handoff and keep existing commitments." required /></label>
      {!isDemo && <>
      <label className="alto-field">Target deadline<input type="datetime-local" value={deadline} onChange={(event) => setDeadline(event.target.value)} required /></label>
      <p className="alto-caption">Your time zone: {Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"}. A requested deadline is not a promise.</p>
      <details className="alto-plan-sources"><summary>Sources for this request · {sources.length} selected</summary><p>Only the authorised source versions below will be used.</p>{context.data?.sources.map((source) => <label className="alto-checkbox" key={source.source_id}><input type="checkbox" checked={sources.includes(source.source_id)} onChange={(event) => setSourceChoice(event.target.checked ? [...sources, source.source_id] : sources.filter((id) => id !== source.source_id))} /><span>{source.title}<small>{humanize(source.classification)} · {humanize(source.source_kind)}</small></span></label>)}</details>
      </>}
      {isDemo && <p className="alto-caption">The approved Northstar source set, project and scenario deadline are selected by the server. A different goal or deadline needs additional typed planning authority, not a retry.</p>}
      {context.loading && <Loading label="Loading permitted sources…" />}<ErrorNotice error={context.error} retry={context.refresh} />
      {!isDemo && !context.loading && !context.error && !sources.length && <p className="alto-info-banner">Select at least one authorised source before preparing a plan.</p>}
      <p className="alto-caption">In Live mode, ALTO uses your bound AI provider and automatically retries correctable output errors within a fixed attempt limit. These calls may incur charges. Nothing is assigned without your approval.{!lockedDemo && " Authored replay remains labelled as demo content."}</p>
      <button className="alto-primary" disabled={busy || !draft.trim() || !supportedDraft || (!isDemo && (!deadline || !sources.length)) || context.loading || Boolean(context.error)}>{busy ? "Saving your request…" : "Prepare plan"}</button>
    </form> : <>
      {summary && <article className="alto-planning-message request"><span>You requested</span><p>{summary}</p></article>}
      {(requestResource.loading && !request || planResource.loading && !plan) && <Loading label="Restoring your saved request…" />}
      {finishedWithoutPlan && <p className="alto-info-banner" role="status">Processing finished without a reviewable plan. No work has been assigned.</p>}
      {request && <article className="alto-planning-message response"><span>ALTO</span>{active && <span className="alto-planning-running" role="status" aria-label="Planning in progress" aria-live="polite"><span className="alto-planning-spinner" aria-hidden="true" /><span className="alto-planning-sr-only">{runningStage?.label}: {stageText(runningStage?.state)}.</span></span>}
        <p>{unsupportedRequest ? "This saved request is outside the demo’s supported planning authority. Its original text and history have been preserved." : plan ? plan.status === "committed" ? "Your approved plan has been committed. Assigned people can now find their work." : "A proposal is ready. Review its tasks, schedule and disclosure requirements before approval." : questions.length ? "I need your decision before I can continue." : failedStage ? "I couldn’t finish preparing this plan." : requestResource.error ? "Your request is saved. Reconnect to check its latest progress." : active ? "I’m preparing your proposal from its authorised sources. You can leave this page and return to the same request." : awaitingNextStage ? "The previous step is complete. Waiting for the next planning stage." : "Your request is saved. Its current progress is shown below."}</p>
        <section className="alto-planning-summary" aria-label="ALTO progress summary" aria-live={active ? "polite" : "off"}>
          <strong>Progress summary</strong>
          <p><span>Now</span>{progressNow}</p>
          <p><span>Completed</span>{completedStages.length ? completedStages.join(" · ") : "No stages recorded complete yet."}</p>
          <p><span>Next</span>{progressNext}</p>
        </section>
        <ol className="alto-planning-stages" aria-label="Planning progress">{stages.map((stage) => <li key={stage.label} className={TERMINAL.includes(stage.state ?? "") ? "stopped" : stage.state === "succeeded" ? "complete" : ""}><strong>{stage.label}</strong><span>{stageText(stage.state)}</span></li>)}</ol>
      </article>}
      {unsupportedRequest && <section className="alto-planning-stopped" role="alert"><h3>This request is not supported by the demo</h3><p>{request?.intake_limitation ?? "Only the approved Northstar launch request has typed planning authority in this demo. Free-form planning cannot continue here."}</p><p>Retrying will not fix this limitation. Further processing and approval are unavailable here; the saved original has not been rewritten.</p><button className="alto-primary" onClick={() => navigate("/home")}>Go to Home — Prepare the Northstar launch plan</button></section>}
      {failedStage && !unsupportedRequest && <section className="alto-planning-stopped" role="alert"><h3>{policyStop ? "Planning needs an access change" : "Planning stopped — not awaiting your approval"}</h3><p>{failureText(failedJob)}</p>{latestModelFailure && <p>{latestModelFailure}</p>}{!policyStop && !guaranteedNorthstarRecovery && <p>No plan is ready to approve. Check the cause before retrying; another Live attempt may incur provider charges.</p>}<details><summary>Processing details</summary><p>Stage: {failedStage.label}</p><p>Error: <code>{failedJob?.last_error_code ?? "No error code recorded"}</code></p>{failedJob && <><p>Worker attempts: {failedJob.attempt_count} · Stage reference: <code>{failedJob.job_id}</code></p>{failedJob.model_call_count != null && <><p>AI attempts recorded: {failedJob.model_call_count}</p><p className="alto-caption">Recorded attempts are separate from worker retries and are not a provider billing count.</p></>}{latestModelFailure && <p>Latest AI error: <code>{failedJob.latest_model_error_code}</code></p>}</>}</details>
        {guaranteedNorthstarRecovery ? <button className="alto-primary" disabled={busy} onClick={() => void command(prepareNorthstarSuccessor)}>Prepare a new Northstar plan</button> : retryAllowed ? <><button className="alto-secondary" disabled={busy} onClick={() => setRetryOpen(!retryOpen)}>Review retry options</button>{retryOpen && <form className="alto-plan-retry" onSubmit={(event) => { event.preventDefault(); void command(retry); }}><label className="alto-field">Reason for retry<textarea value={retryReason} onChange={(event) => setRetryReason(event.target.value)} maxLength={500} rows={2} placeholder="Describe what was corrected or why another attempt is appropriate." required /></label><label className="alto-checkbox"><input type="checkbox" checked={retryConfirmed} onChange={(event) => setRetryConfirmed(event.target.checked)} />Retry this saved request. Live processing may make further provider calls and incur charges.</label><button className="alto-primary" disabled={busy || !retryConfirmed || !retryReason.trim()}>Retry saved request</button></form>}</> : !policyStop && <p className="alto-caption">No authorised retry is currently available here. Keep this request and ask your host operator to investigate the recorded error; do not create duplicate requests.</p>}
        <button className="alto-text-button" onClick={requestResource.refresh}>Refresh status</button>
      </section>}
      {!unsupportedRequest && questions.length > 0 && <form className="alto-plan-questions" onSubmit={(event) => { event.preventDefault(); void command(async () => { if (!request) return; const submittedAnswers = Object.fromEntries(questions.map((item) => [item.question_key, answers[item.question_key]?.trim() ?? ""])); const payload = JSON.stringify([request.request_id, request.request_version, request.candidate_contract_id, submittedAnswers]); if (clarificationKey.current?.payload !== payload) clarificationKey.current = { payload, key: `clarification-answers:${crypto.randomUUID()}` }; const result = await answerPlanningClarifications(api, request, submittedAnswers, clarificationKey.current.key); selectRequest(result.request_id); }); }}><h3>A decision from you</h3>{questions.map((question) => <label className="alto-field" key={question.question_key}>{question.question}<textarea value={answers[question.question_key] ?? ""} onChange={(event) => setAnswers({ ...answers, [question.question_key]: event.target.value })} rows={2} maxLength={4000} required /></label>)}<p className="alto-caption">Your answers are recorded against this exact request. Continuing may call the provider in Live mode.</p><button className="alto-primary" disabled={busy || questions.some((item) => !answers[item.question_key]?.trim())}>Answer and continue</button></form>}
      {request && !unsupportedRequest && !request.interpretation_job_state && !request.plan_id && !questions.length && <div className="alto-info-banner"><p>The request is saved, but processing has not started. In Live mode, starting it may incur provider charges.</p><button className="alto-primary" disabled={busy} onClick={() => void command(async () => { await startPlanningInterpretation(api, request.request_id); requestResource.refresh(); })}>Start saved request</button></div>}
      {plan && !unsupportedRequest && !reviewing && <button className="alto-primary" onClick={() => setReviewing(true)}>{plan.status === "committed" ? "View committed plan" : "Review plan"}</button>}
      {plan && !unsupportedRequest && reviewing && <ExactPlanReview key={`${plan.plan_id}:${plan.binding.proposal_digest}`} api={api} plan={plan} evidence={evidence.data} evidenceError={evidence.error} projectId={request?.project_id} busy={busy} run={command} refresh={() => { planResource.refresh(); requestResource.refresh(); evidence.refresh(); }} />}
      {currentId && <p className="alto-caption alto-request-reference">Saved request · <code>{currentId}</code> <button className="alto-text-button" onClick={() => navigate("/plan-review")}>All requests</button></p>}
    </>}
  </section>;
}

function ExactPlanReview({ api, plan, evidence, evidenceError, projectId, busy, run, refresh }: {
  api: AuthorisedApiContext;
  plan: PlanReview;
  evidence: PlanEvidence | null;
  evidenceError: string | null;
  projectId?: string | null;
  busy: boolean;
  run: (action: () => Promise<void>) => Promise<void>;
  refresh: () => void;
}) {
  const [confirmed, setConfirmed] = useState(false);
  const projects = useResource<{ projects: Project[] }>(api, projectId ? null : "/projects");
  const linkedProjectId = projectId ?? projects.data?.projects.find((project) => project.plan_id === plan.plan_id)?.id;
  const graph = useResource<ProjectGraphData>(api, linkedProjectId ? `/projects/${encodeURIComponent(linkedProjectId)}/graph?plan_id=${encodeURIComponent(plan.plan_id)}` : null);
  const exactGraph = graph.data?.plan_id === plan.plan_id ? graph.data : null;
  const committed = plan.status === "committed";
  const checked = evidence?.fixed_verification ? evidence.fixed_verification.product_status === "CHECKED" && evidence.independent_validation?.passed === true : evidence?.solver?.raw_status === "sat" && Boolean(evidence.solver.validator_version);
  return <section className="alto-plan-review-card" aria-label="Exact plan review"><header><div><Badge tone={committed ? "mint" : "pending"}>{committed ? "Committed" : "Proposal — not yet assigned"}</Badge><h3>{plan.request_summary}</h3></div>{linkedProjectId && <button className="alto-secondary" onClick={() => navigate(`/projects/${encodeURIComponent(linkedProjectId)}/graph?plan=${encodeURIComponent(plan.plan_id)}&panel=rules`)}>Open task graph & rules</button>}</header>
    <p>Review who does what and when. Approval does not assign work; committing the exact approved plan does.</p>
    <div className="alto-plan-schedule"><table><caption>Exact proposed schedule · times shown in {Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"}</caption><thead><tr><th>Task</th><th>Start</th><th>Finish</th><th>Assigned to</th></tr></thead><tbody>{plan.tasks.map((task) => { const node = exactGraph?.nodes.find((item) => item.id === task.task_id); return <tr key={task.task_id}><td><strong>{task.title}</strong><small>{task.task_key}</small></td><td>{dateTime(task.start_at)}</td><td>{dateTime(task.finish_at)}</td><td>{node?.owner_name ?? (task.owner_resource_id ? graph.loading ? "Loading person…" : "Assigned resource" : "Not assigned")}{node?.reviewer_name && <small>Reviewer: {node.reviewer_name}</small>}{!node?.owner_name && task.owner_resource_id && <small>{task.owner_resource_id}</small>}</td></tr>; })}</tbody></table></div>
    <ErrorNotice error={graph.error} retry={graph.refresh} />
    <ErrorNotice error={evidenceError} retry={refresh} />
    <details className="alto-plan-evidence"><summary>Schedule checks and evidence · {checked ? "verified" : evidence ? "not verified" : "loading"}</summary>{evidence ? <><p>{evidence.fixed_verification ? `${humanize(evidence.fixed_verification.product_status)} · ${evidence.fixed_verification.covered_rule_ids.length}/${evidence.fixed_verification.required_rule_ids.length} required rules covered` : `Solver: ${evidence.solver?.raw_status ?? "not recorded"}`}</p><p>Independent validation: {evidence.independent_validation ? evidence.independent_validation.passed ? "passed" : "did not pass" : "see recorded solver evidence"}</p><ul>{evidence.constraints.map((constraint) => <li key={constraint.constraint_key}>{humanize(constraint.family)} · {humanize(constraint.strength)} <small>{constraint.constraint_key}</small></li>)}</ul>{evidence.assumptions.length > 0 && <><h4>Assumptions to review</h4><ul>{evidence.assumptions.map((assumption, index) => <li key={index}>{assumption}</li>)}</ul></>}</> : !evidenceError && <Loading label="Loading verification evidence…" />}</details>
    {Boolean(exactGraph?.rules.length) && <details><summary>Planning rules · {exactGraph?.rules.length} recorded checks</summary>{exactGraph?.rules.map((rule) => <details key={rule.id}><summary>{rule.title} · {humanize(rule.status)}</summary><p>{rule.description}</p>{rule.source_label && <p>Source: {rule.source_label}{rule.source_version ? ` · ${rule.source_version}` : ""}</p>}{rule.formula && <pre>{rule.formula}</pre>}{rule.candidate_values !== null && <p>Fixed values: {typeof rule.candidate_values === "string" ? rule.candidate_values : JSON.stringify(rule.candidate_values)}</p>}</details>)}</details>}
    {plan.changes.length > 0 && <details><summary>Changes to existing work · {plan.changes.length}</summary><ul>{plan.changes.map((change) => <li key={change.change_id}>{change.summary}</li>)}</ul></details>}
    <details><summary>Exact version being reviewed</summary><p>Proposal: <code>{plan.binding.proposal_digest}</code></p><p>Company revision: {plan.binding.base_company_revision} · Policy: {plan.binding.policy_version}</p></details>
    <h4>Approval decisions</h4><p>Plan approval and permission to disclose employee briefs are separate decisions.</p>
    {plan.requirements.map((requirement) => <div className="alto-plan-requirement" key={requirement.requirement_id}><div><strong>{requirement.domain === "disclosure" ? "Employee brief disclosure" : "Plan approval"}</strong><p>{requirement.reason}</p><small>{humanize(requirement.authority_kind)} · {humanize(requirement.status)}</small></div><button className="alto-secondary" disabled={busy || committed || !checked || requirement.status !== "pending"} onClick={() => void run(async () => { await approveRequirement(api, plan, requirement); refresh(); })}>{requirement.status === "pending" ? requirement.domain === "disclosure" ? "Approve this disclosure" : "Approve this plan requirement" : humanize(requirement.status)}</button></div>)}
    {!committed ? <footer><label className="alto-checkbox"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />I have reviewed this exact schedule and its approved audience.</label><p className="alto-caption">{!checked ? "A verified schedule is required before approval or assignment." : !plan.can_commit ? "Every required approval and the current revision checks must pass before work can be assigned." : "Committing assigns this exact approved work to its named people."}</p><button className="alto-primary" disabled={busy || !checked || !confirmed || !plan.can_commit} onClick={() => void run(async () => { await commitPlan(api, plan); refresh(); })}>Commit approved plan & assign work</button></footer> : <div className="alto-button-row"><button className="alto-primary" onClick={() => navigate(linkedProjectId ? `/projects/${encodeURIComponent(linkedProjectId)}/graph` : "/projects")}>View assigned work</button><button className="alto-secondary" onClick={() => navigate("/calendar")}>Open calendar</button></div>}
  </section>;
}
