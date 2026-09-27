import { useEffect } from "react";
import type { AuthorisedApiContext, PendingReview, PlanningContext } from "./api-client";
import { dateTime, humanize, navigate, useResource } from "./alto-state";
import { EmptyState, ErrorNotice, Icon, Loading } from "./alto-ui";
import "./planning-conversation.css";

interface PlanReviewWorkspaceProps {
  api?: AuthorisedApiContext;
  initialRequestId?: string | null;
  initialPlanId?: string | null;
}

function requestStatus(status: string): string {
  if (["review_required", "failed", "dead_letter"].includes(status)) return "Processing needs attention";
  if (status === "clarification_required") return "Answer a question to continue";
  if (["pending_interpretation", "interpreting", "materialized"].includes(status)) return "Open for current progress and next steps";
  return humanize(status);
}

export function PlanReviewWorkspace({ api, initialRequestId, initialPlanId }: PlanReviewWorkspaceProps) {
  const context = useResource<PlanningContext>(api, "/planning-context");
  const reviews = useResource<{ reviews: PendingReview[] }>(api, "/reviews/pending");
  const refreshContext = context.refresh;
  const refreshReviews = reviews.refresh;

  // Old notifications and bookmarks enter the same durable Home conversation.
  useEffect(() => {
    if (initialRequestId) navigate(`/home?request=${encodeURIComponent(initialRequestId)}`);
    else if (initialPlanId) navigate(`/home?plan=${encodeURIComponent(initialPlanId)}`);
  }, [initialRequestId, initialPlanId]);

  useEffect(() => {
    if (!api) return;
    const refresh = () => { refreshContext(); refreshReviews(); };
    window.addEventListener("focus", refresh);
    return () => window.removeEventListener("focus", refresh);
  }, [api, refreshContext, refreshReviews]);

  if (!api) return <EmptyState title="Sign in to review work">Your authorised requests and decisions will appear here.</EmptyState>;
  if (initialRequestId || initialPlanId) return <Loading label="Opening your saved conversation…" />;
  return <div className="alto-planning-inbox">
    <header><p>Continue a request or review submitted work. All planning happens in the same Home conversation.</p><button className="alto-secondary" onClick={() => { context.refresh(); reviews.refresh(); }}>Refresh</button></header>
    <ErrorNotice error={context.error} retry={context.refresh} />
    {context.loading && !context.data && <Loading label="Loading your requests…" />}
    <section aria-label="Planning requests"><h2>Your requests</h2>{context.data?.requests.map((request) => <button className="alto-project-row" key={request.request_id} onClick={() => navigate(`/home?request=${encodeURIComponent(request.request_id)}`)}><Icon name="document" /><div><strong>{request.original_request}</strong><p>{requestStatus(request.status)} · {dateTime(request.created_at)}</p><small>Open conversation and next action</small></div><Icon name="right" /></button>)}{!context.loading && !context.error && !context.data?.requests.length && <EmptyState title="No planning requests yet">Describe the work you want to coordinate from Home.<button className="alto-text-button" onClick={() => navigate("/home?compose=plan")}>Plan work from Home</button></EmptyState>}</section>
    <section aria-label="Submitted work awaiting review"><h2>Work awaiting your acceptance</h2><ErrorNotice error={reviews.error} retry={reviews.refresh} />{reviews.loading && !reviews.data && <Loading label="Loading work awaiting review…" />}{reviews.data?.reviews.map((review) => <button className="alto-project-row" key={review.submission_id} onClick={() => navigate(`/reviews/${encodeURIComponent(review.submission_id)}`)}><Icon name="check" /><div><strong>{review.task_title}</strong><p>{review.submitting_employee_name} · Submitted version {review.version}</p><small>Inspect the submitted work and evidence before accepting</small></div><Icon name="right" /></button>)}{!reviews.loading && !reviews.error && !reviews.data?.reviews.length && <p className="alto-muted">No submitted work needs your review.</p>}</section>
  </div>;
}
