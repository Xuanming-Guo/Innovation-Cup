import { useState } from "react";
import { altoRequest, type AltoApiContext, type TaskDetail } from "./alto-api";
import { downloadPrivateFile, uploadPrivateFile } from "./alto-storage";
import { PrivateFeedback } from "./alto-private-feedback";
import { Badge, EmptyState, ErrorNotice, Icon, Loading, Modal, PageHeading } from "./alto-ui";
import { dateTime, humanize, navigate, useCommand, useResource } from "./alto-state";
function briefSummary(detail: TaskDetail): string {
    const brief = detail.task.approved_brief?.content;
    if (!brief)
        return "The employee brief has not been disclosed. Only approved context will appear here.";
    return typeof brief.summary === "string" ? brief.summary : typeof brief.objective === "string" ? brief.objective : "The exact approved brief is available below.";
}
function briefDeliverables(detail: TaskDetail): string[] {
    const values = detail.task.approved_brief?.content.deliverables;
    return Array.isArray(values) ? values.filter((value): value is string => typeof value === "string") : [];
}
function GateDecision({ api, detail, onSaved }: { api: AltoApiContext; detail: TaskDetail; onSaved: () => void }) {
    const [confirmed, setConfirmed] = useState(false);
    const command = useCommand();
    const gate = detail.gate;
    if (!gate) return null;
    return <section className="alto-gate-decision">
      <h2>{gate.kind === "readiness" ? "Readiness gate" : "Final project acceptance"}</h2>
      <p>{gate.kind === "readiness" ? "The current accepted readiness prerequisites must all be satisfied. This is an explicit gate decision, not a work submission." : "Final acceptance is bound to the exact submitted support-coverage evidence and accepted release QA. Time passing never accepts the project."}</p>
      {gate.required_submission && <><Badge>Evidence version {gate.required_submission.version}</Badge><p className="alto-review-narrative">{gate.required_submission.narrative}</p><button className="alto-text-button" onClick={() => navigate(`/tasks/${detail.task.task_id}/reviews/${gate.required_submission?.id}`)}>Inspect exact evidence</button></>}
      <label className="alto-checkbox"><input type="checkbox" checked={confirmed} disabled={!detail.can_work} onChange={(event) => setConfirmed(event.target.checked)}/>I have reviewed the prerequisites{gate.required_submission ? " and this exact evidence version" : ""}.</label>
      <button className="alto-primary" disabled={command.busy || !detail.can_work || !confirmed || (gate.kind === "milestone" && !gate.required_submission)} onClick={() => void command.run(async () => { await altoRequest(api, `/tasks/${detail.task.task_id}/approve-gate`, { method: "POST", body: { expected_row_version: detail.task.row_version, required_submission_id: gate.required_submission?.id ?? null, required_submission_digest: gate.required_submission?.digest ?? null } }); setConfirmed(false); onSaved(); })}>{gate.kind === "readiness" ? "Approve readiness" : "Accept exact launch evidence"}</button>
      {!detail.can_work && <p className="alto-caption">Only the named, currently authorised gate owner can approve.</p>}<ErrorNotice error={command.error}/>
    </section>;
}
function TaskFacts({ detail, api }: {
    detail: TaskDetail;
    api: AltoApiContext;
}) {
    const command = useCommand();
    return <aside className="alto-task-facts">
<dl>
<dt>Project</dt>
<dd>{detail.project ? <button className="alto-text-button" onClick={() => navigate(`/projects/${detail.project?.id}/graph`)}>{detail.project.title}</button> : "No project linked"}</dd>
<dt>Owner</dt>
<dd>{detail.owner_name ?? "Not disclosed"}</dd>
<dt>Reviewer</dt>
<dd>{detail.reviewer_name ?? "No reviewer recorded"}</dd>
<dt>Approver</dt>
<dd>{detail.approver_name ?? "Not disclosed"}</dd>
</dl>
<section>
<h3>Attachments</h3>{detail.attachments.length ? detail.attachments.map((file) => <button className="alto-attachment" disabled={command.busy || file.state !== "available"} title={file.state !== "available" ? `Download unavailable: ${humanize(file.state)}` : undefined} key={file.id} onClick={() => void command.run(() => downloadPrivateFile(api, file.id))}>
<Icon name="document"/>
<span>{file.filename} · v{file.version}<small>{humanize(file.state)}</small>
</span>
</button>) : <p className="alto-muted">No disclosed attachments.</p>}</section>
<section>
<h3>Due</h3>
<p>{dateTime(detail.task.finish_at, detail.timezone)}</p>
<small>{detail.timezone} · {humanize(detail.task.scheduling_kind)}</small>
</section>
<ErrorNotice error={command.error}/>
</aside>;
}
export function TaskBrief({ api, taskId }: {
    api?: AltoApiContext;
    taskId: string;
}) {
    const resource = useResource<TaskDetail>(api, `/tasks/${encodeURIComponent(taskId)}`);
    const command = useCommand();
    const [action, setAction] = useState<"block" | "flag_estimate" | null>(null);
    const [reason, setReason] = useState("");
    const [minutes, setMinutes] = useState("");
    const [work, setWork] = useState(false);
    const detail = resource.data;
    async function transition(kind: string) {
        if (!api || !detail)
            return;
        await altoRequest(api, `/tasks/${taskId}/events`, { method: "POST", body: { command: kind, expected_task_version: detail.task.row_version, correlation_id: crypto.randomUUID(), payload: kind === "block" ? { reason: reason.trim() } : kind === "flag_estimate" ? { reason: reason.trim(), proposed_active_minutes: Number(minutes) } : {} } });
        setAction(null);
        setReason("");
        resource.refresh();
    }
    if (resource.loading && !detail)
        return <Loading />;
    if (resource.error)
        return <ErrorNotice error={resource.error} retry={resource.refresh}/>;
    if (!detail || !api)
        return <EmptyState title="Task unavailable">Sign in to read your authorised brief.</EmptyState>;
    return <div>
<div className="alto-breadcrumb">
<button onClick={() => navigate("/projects")}>Projects</button> / Approved task brief</div>
<div className="alto-brief-layout">
<section>
<PageHeading title={detail.task.title}/>
<Badge>{detail.task.approved_brief ? `Approved disclosure · v${detail.task.approved_brief.version}` : "Awaiting brief disclosure"}</Badge>
<p className="alto-brief-summary">{briefSummary(detail)}</p>{briefDeliverables(detail).length > 0 && <ul className="alto-deliverables">{briefDeliverables(detail).map((value) => <li key={value}>{value}</li>)}</ul>}<h2>Your task timeline <small>({detail.timezone})</small>
</h2>
<ol className="alto-timeline">{detail.timeline.map((item) => <li key={item.id} className={item.kind}>
<span className="alto-timeline-dot"/>
<strong>{dateTime(item.start_at, detail.timezone)}{item.end_at ? ` – ${dateTime(item.end_at, detail.timezone)}` : ""}</strong>
<p>{item.title}</p>
<small>{humanize(item.kind)}</small>
</li>)}</ol>{!detail.timeline.length && <p className="alto-muted">No additional timeline events have been disclosed.</p>}{detail.protected_commitments.map((commitment) => <div key={commitment} className="alto-protected-banner">
<Icon name="calendar"/>{commitment}</div>)}<div className="alto-button-row">{detail.can_work && detail.task.status === "assigned" && <button className="alto-primary" disabled={command.busy} onClick={() => void command.run(() => transition("acknowledge"))}>Acknowledge</button>}{detail.can_work && detail.task.status === "acknowledged" && <button className="alto-primary" disabled={command.busy} onClick={() => void command.run(() => transition("start"))}>Start work</button>}{detail.can_work && detail.task.status === "blocked" && <button className="alto-primary" disabled={command.busy} onClick={() => void command.run(() => transition("unblock"))}>Resume work</button>}<button className="alto-secondary" disabled={!detail.can_work || command.busy || ["accepted", "submitted"].includes(detail.task.status)} onClick={() => setAction("block")}>Flag blocker</button>
<button className="alto-secondary" disabled={!detail.can_work || command.busy} onClick={() => setAction("flag_estimate")}>Correct estimate</button>
<button className="alto-secondary" onClick={() => setWork(true)}>{detail.can_work ? "Open work" : "Inspect work"}</button>
</div>
<ErrorNotice error={command.error}/>
<p className="alto-caption">Acknowledgement records receipt only. A correction requests review; it does not change the committed schedule.</p>
</section>
<TaskFacts detail={detail} api={api}/>
</div>
{detail.gate && <GateDecision api={api} detail={detail} onSaved={resource.refresh}/>}
{detail.can_give_feedback && <details className="alto-private-details"><summary>Private feedback on this task</summary><PrivateFeedback api={api} taskId={taskId}/></details>}
    {action && <Modal title={action === "block" ? "Flag a blocker" : "Propose an estimate correction"} onClose={() => setAction(null)}>
<label className="alto-field">Reason and required input or access<textarea rows={4} value={reason} maxLength={4000} onChange={(event) => setReason(event.target.value)}/>
</label>{action === "flag_estimate" && <label className="alto-field">Proposed active effort (minutes)<input type="number" min="1" max="100000" value={minutes} onChange={(event) => setMinutes(event.target.value)}/>
</label>}<button className="alto-primary" disabled={command.busy || !reason.trim() || (action === "flag_estimate" && (!Number.isInteger(Number(minutes)) || Number(minutes) <= 0))} onClick={() => void command.run(() => transition(action))}>Submit for review</button>
<ErrorNotice error={command.error}/>
</Modal>}
    {work && <TaskWorkModal api={api} taskId={taskId} onClose={() => setWork(false)} onSaved={resource.refresh}/>}
  </div>;
}
export function TaskWorkModal({ api, taskId, onClose, onSaved }: {
    api: AltoApiContext;
    taskId: string;
    onClose: () => void;
    onSaved: () => void;
}) {
    const resource = useResource<TaskDetail>(api, `/tasks/${encodeURIComponent(taskId)}`);
    const command = useCommand();
    const [editedText, setEditedText] = useState<string | null>(null);
    const [files, setFiles] = useState<{
        file_id: string;
        state: string;
        name: string;
    }[]>([]);
    const [confirmClose, setConfirmClose] = useState(false);
    const detail = resource.data;
    const text = editedText ?? detail?.draft?.text ?? "";
    const editable = detail?.can_work && !detail.gate && ["in_progress", "revision_requested"].includes(detail.task.status);
    function close() { if (editedText !== null && editedText !== (detail?.draft?.text ?? ""))
        setConfirmClose(true);
    else
        onClose(); }
    return <Modal title={detail ? `${detail.task.title} · ${detail.task.task_key}` : "Task work"} onClose={close} wide>{resource.loading && <Loading />}<ErrorNotice error={resource.error ?? command.error} retry={resource.refresh}/>{detail && <>
<div className="alto-work-modal-layout">
<section>
<Badge tone="mint">{humanize(detail.task.status)}</Badge>
<h3>Task summary</h3>
<p className="alto-work-summary">{briefSummary(detail)}</p>
<label className="alto-field">Work in progress<textarea rows={11} value={text} maxLength={12000} disabled={!editable || command.busy} onChange={(event) => setEditedText(event.target.value)} placeholder={detail.can_work ? "Record your deliverable and exact evidence for review…" : "This task is read-only for your current actor."}/>
</label>
<label className="alto-file-input">Attach a private artifact<input type="file" accept=".pdf,.docx,.csv,.txt,.png,.jpg,.jpeg" disabled={!editable || command.busy} onChange={(event) => { const file = event.target.files?.[0]; if (!file)
        return; void command.run(async () => { const uploaded = await uploadPrivateFile(api, file, file.name, "submission", { taskId }); setFiles((current) => [...current, { ...uploaded, name: file.name }]); }); event.target.value = ""; }}/>
</label>{files.map((file) => <p className="alto-caption" key={file.file_id}>{file.name} · {humanize(file.state)}. Files must pass the server scan before submission.</p>)}</section>
<TaskFacts detail={detail} api={api}/>
</div>
<footer className="alto-modal-actions">
<span className="alto-muted">{detail.reviewer_name ? `${detail.reviewer_name} reviews this exact version.` : "The server rechecks the current review policy."}</span>
<button className="alto-secondary" disabled={command.busy || !editable || editedText === null} onClick={() => void command.run(async () => { await altoRequest(api, `/tasks/${taskId}/draft`, { method: "PATCH", body: { text, expected_row_version: detail.draft?.row_version ?? 0 } }); setEditedText(null); resource.refresh(); onSaved(); })}>Save draft</button>
<button className="alto-primary" disabled={command.busy || !editable || !text.trim()} onClick={() => void command.run(async () => { await altoRequest(api, `/tasks/${taskId}/submissions`, { method: "POST", body: { narrative: text.trim(), file_ids: files.map((file) => file.file_id), external_evidence_refs: [], reported_active_minutes: null, expected_task_version: detail.task.row_version, correlation_id: crypto.randomUUID() } }); setEditedText(null); onSaved(); onClose(); })}>Submit for review</button>
</footer>{!editable && <p className="alto-caption">{detail.can_work ? "Acknowledge and start the task before editing, or wait for its current review." : "Only the assigned employee or an authorised, labelled demo actor can save or submit this work."}</p>}</>}{confirmClose && <div className="alto-unsaved-warning" role="alert">
<p>You have unsaved work. Discard it?</p>
<button className="alto-secondary" onClick={() => setConfirmClose(false)}>Keep editing</button>
<button className="alto-primary" onClick={onClose}>Discard unsaved changes</button>
</div>}</Modal>;
}
