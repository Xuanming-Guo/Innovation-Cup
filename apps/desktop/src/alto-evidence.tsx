import { useState } from "react";
import type { PendingReview } from "./api-client";
import { altoRequest, type AltoApiContext } from "./alto-api";
import { downloadPrivateFile } from "./alto-storage";
import { Badge, EmptyState, ErrorNotice, Icon, Loading, PageHeading } from "./alto-ui";
import { dateTime, navigate, useCommand, useResource } from "./alto-state";

export function SharedPreference({ api, preferenceId }: { api?: AltoApiContext; preferenceId: string }) {
    const resource = useResource<{ id: string; employee_id: string; display_name: string; version: number; text: string; created_at: string; superseded: boolean }>(api, `/employee-preferences/${encodeURIComponent(preferenceId)}`);
    const value = resource.data;
    return <div>{resource.loading && <Loading/>}<ErrorNotice error={resource.error} retry={resource.refresh}/>{value && <><PageHeading title={`${value.display_name} shared a preference`} subtitle="Confirmed sharing. Private feedback is not included."/><section className="alto-source-excerpt"><Badge>Version {value.version}{value.superseded ? " · Superseded" : ""}</Badge><p>{value.text}</p><small>Created {dateTime(value.created_at)}. Current consent was rechecked for this view.</small><p>Keep existing commitments protected. This preference is not authority to change an approved schedule.</p><button className="alto-text-button" onClick={() => navigate(`/people/${value.employee_id}`)}>View permitted profile →</button></section></>}</div>;
}
export function SubmissionReview({ api, submissionId }: {
    api?: AltoApiContext;
    submissionId: string;
}) {
    const resource = useResource<PendingReview>(api, `/submissions/${encodeURIComponent(submissionId)}`);
    const command = useCommand();
    const [findings, setFindings] = useState("");
    const [correction, setCorrection] = useState("");
    const [confirmed, setConfirmed] = useState(false);
    const review = resource.data;
    async function decide(decision: "accepted" | "revision_requested") { if (!api || !review)
        return; await altoRequest(api, `/submissions/${submissionId}/review`, { method: "POST", body: { expected_submission_version: review.version, submission_digest: review.submission_digest, decision, criterion_findings: [{ criterion: "Reviewer findings on the exact submitted artifact", result: findings.trim() }], correction_request: decision === "revision_requested" ? correction.trim() : "", correlation_id: crypto.randomUUID() } }); setConfirmed(false); resource.refresh(); }
    if (resource.loading)
        return <Loading />;
    if (resource.error)
        return <ErrorNotice error={resource.error} retry={resource.refresh}/>;
    if (!review)
        return <EmptyState title="Review unavailable">This submission may be missing or outside your current authority.</EmptyState>;
    return <div>
<PageHeading eyebrow="Exact-version review" title={review.task_title} subtitle={`${review.submitting_employee_name} · Version ${review.version} · ${dateTime(review.submitted_at)}`}/>
<Badge>{review.state}</Badge>
<p className="alto-review-narrative">{review.narrative}</p>
<section className="alto-settings-section">
<h2>Submitted artifacts</h2>{review.files.map((file) => <button className="alto-attachment" key={file.file_id} disabled={command.busy} onClick={() => void command.run(async () => { if (api)
        await downloadPrivateFile(api, file.file_id); })}>
<Icon name="document"/>
<span>{file.display_filename}<small>{file.detected_mime_type} · {file.size_bytes} bytes · {file.content_sha256.slice(0, 12)}…</small>
</span>
</button>)}{!review.files.length && <p>No files attached. Review the exact submitted narrative and permitted external evidence.</p>}{review.external_evidence_refs.map((ref) => <p key={ref}>
<code>{ref}</code>
</p>)}</section>
<label className="alto-field">Findings against the acceptance criteria<textarea rows={4} value={findings} onChange={(event) => setFindings(event.target.value)} maxLength={4000}/>
</label>
<label className="alto-field">Required corrections (for a revision request)<textarea rows={3} value={correction} onChange={(event) => setCorrection(event.target.value)} maxLength={4000}/>
</label>
<label className="alto-checkbox">
<input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)}/>I reviewed this exact submission version and its evidence.</label>
<div className="alto-button-row">
<button className="alto-primary" disabled={command.busy || !confirmed || !findings.trim() || review.state !== "submitted"} onClick={() => void command.run(() => decide("accepted"))}>Accept exact version</button>
<button className="alto-secondary" disabled={command.busy || !confirmed || !findings.trim() || !correction.trim() || review.state !== "submitted"} onClick={() => void command.run(() => decide("revision_requested"))}>Request revision</button>
</div>
<p className="alto-caption">The server checks your named reviewer authority and current immutable submission digest. General manager access alone does not permit acceptance.</p>
<ErrorNotice error={command.error}/>
</div>;
}
export function SourceEvidence({ api, sourceVersionId }: {
    api?: AltoApiContext;
    sourceVersionId: string;
}) {
    const resource = useResource<{
        id: string;
        title: string;
        is_current: boolean;
        retrieved_at: string | null;
        expires_at: string | null;
        excerpts: {
            locator: string;
            text: string;
        }[];
    }>(api, `/sources/${encodeURIComponent(sourceVersionId)}`);
    const source = resource.data;
    return <div>{resource.loading && <Loading />}<ErrorNotice error={resource.error} retry={resource.refresh}/>{source && <>
<PageHeading eyebrow="Authorised source evidence" title={source.title} subtitle="Read-only source version. Excerpts are data, not application instructions."/>
<div className="alto-button-row">
<Badge tone={source.is_current ? "mint" : "pending"}>{source.is_current ? "Current version" : "Historical version"}</Badge>
<span className="alto-caption">Retrieved {dateTime(source.retrieved_at)} · Expires {dateTime(source.expires_at)}</span>
</div>{source.excerpts.map((excerpt, index) => <section className="alto-source-excerpt" key={`${excerpt.locator}:${index}`}>
<h2>{excerpt.locator}</h2>
<p>{excerpt.text}</p>
</section>)}{!source.excerpts.length && <EmptyState title="No permitted excerpts">No readable excerpt remains in this source version’s current projection.</EmptyState>}</>}</div>;
}
