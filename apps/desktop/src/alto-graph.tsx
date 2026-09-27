import { useMemo, useRef, useState, type PointerEvent } from "react";
import { approveRequirement, commitPlan, type PlanReview } from "./api-client";
import { type AltoApiContext, type CandidateValue, type GraphNode, type ProjectGraphData, type RuleResult, type RuleTechnicalDetail, type VerificationSummary } from "./alto-api";
import { Assistant } from "./alto-assistant";
import { TaskWorkModal } from "./alto-task";
import { Badge, EmptyState, ErrorNotice, Icon, IconButton, Loading, Modal, PageHeading, type IconName } from "./alto-ui";
import { dateTime, humanize, navigate, useCommand, useResource } from "./alto-state";
const TEAMS = ["Engineering", "Design", "QA", "Marketing", "Support"];
const TEAM_ICONS: IconName[] = ["settings", "document", "check", "flag", "people"];
const TEAM_POSITIONS = [{ x: 300, y: 185 }, { x: 785, y: 185 }, { x: 830, y: 425 }, { x: 550, y: 545 }, { x: 255, y: 440 }];
const isGoalGate = (node: GraphNode) => node.task_key === "R1" || node.task_key === "R2";
const isPassingRule = (rule: RuleResult) => ["pass", "passed"].includes(rule.status.toLowerCase());
const isViolation = (rule: RuleResult) => rule.status.toLowerCase() === "violation";
const RULE_CATEGORIES = [
    ["owner", "Owner"],
    ["working_hours", "Working hours"],
    ["busy_time", "Busy time"],
    ["effort", "Effort"],
    ["eligibility", "Eligibility"],
    ["dependencies", "Dependencies"],
    ["participants", "Participants"],
    ["handoffs", "Handoffs"],
    ["protected_time", "Protected time"],
    ["reviews", "Reviews"],
    ["deadlines", "Deadlines"],
    ["authorised_scope", "Authorised scope"],
] as const;
const originFor = (team: number) => TEAM_POSITIONS[team] ?? { x: 550, y: 340 };
function teamIndex(team: string): number { const index = TEAMS.findIndex((value) => team.toLowerCase().includes(value.toLowerCase())); return index === -1 ? 0 : index; }
function statusStep(status: string): number { return status === "accepted" ? 4 : status === "submitted" ? 3 : ["in_progress", "revision_requested", "blocked"].includes(status) ? 2 : status === "acknowledged" ? 1 : 0; }
function labelize(value: string): string { const text = humanize(value); return text ? `${text[0]?.toUpperCase()}${text.slice(1)}` : text; }
function shortDigest(value: string | null): string { return value ? value.length > 18 ? `${value.slice(0, 10)}…${value.slice(-6)}` : value : "Not recorded"; }
function isCheckedSummary(summary: VerificationSummary | null | undefined): boolean {
    return Boolean(summary
        && summary.native_status.toLowerCase() === "sat"
        && summary.product_status.toLowerCase() === "checked"
        && summary.required_rule_count > 0
        && summary.covered_rule_count === summary.required_rule_count
        && summary.unverified_rule_count === 0
        && summary.digests_match
        && summary.independent_validation_passed
        && summary.candidate_digest
        && summary.snapshot_digest);
}
function verificationLabel(summary: VerificationSummary): string {
    const native = summary.native_status.toUpperCase();
    if (isCheckedSummary(summary)) return `${native} · CHECKED`;
    if (summary.native_status.toLowerCase() === "unsat") return "UNSAT · VIOLATIONS FOUND";
    if (summary.native_status.toLowerCase() === "unknown") return "UNKNOWN · UNABLE TO VERIFY";
    if (summary.covered_rule_count !== summary.required_rule_count || summary.unverified_rule_count > 0) return `${native} · INCOMPLETE`;
    if (!summary.digests_match || !summary.candidate_digest || !summary.snapshot_digest) return `${native} · DIGEST MISMATCH`;
    if (!summary.independent_validation_passed) return `${native} · VALIDATION FAILED`;
    return `${native} · ${humanize(summary.product_status).toUpperCase()}`;
}
function parsedCandidateValue(value: CandidateValue | null): CandidateValue | null {
    if (typeof value !== "string") return value;
    try { return JSON.parse(value) as CandidateValue; } catch { return value; }
}
function bindingRows(value: CandidateValue | null, prefix = ""): { label: string; value: string }[] {
    const parsed = parsedCandidateValue(value);
    if (parsed === null) return [];
    if (typeof parsed !== "object") return [{ label: prefix || "Fixed candidate", value: typeof parsed === "boolean" ? parsed ? "Yes" : "No" : String(parsed) }];
    if (Array.isArray(parsed)) {
        return parsed.flatMap((entry, index) => bindingRows(entry, prefix || `Value ${index + 1}`));
    }
    const labelled = parsed as { label?: CandidateValue; value?: CandidateValue };
    if (typeof labelled.label === "string" && labelled.value !== undefined) return bindingRows(labelled.value, labelled.label);
    return Object.entries(parsed).flatMap(([key, entry]) => {
        const label = prefix ? `${prefix} · ${labelize(key)}` : labelize(key);
        return bindingRows(entry, label);
    });
}
function categoryResult(rules: RuleResult[]): "passed" | "violation" | "unable" | "unavailable" {
    if (!rules.length) return "unavailable";
    if (rules.some(isViolation)) return "violation";
    return rules.every(isPassingRule) ? "passed" : "unable";
}
function ruleCategoryKeys(rule: RuleResult): string[] {
    if (rule.category_keys?.length) return rule.category_keys;
    return rule.category_key ? [rule.category_key] : [];
}
function ruleCategoryTitle(rule: RuleResult, categoryKey: string): string | null {
    const index = rule.category_keys?.indexOf(categoryKey) ?? -1;
    if (index >= 0 && rule.category_titles?.[index]) return rule.category_titles[index] ?? null;
    return rule.category_key === categoryKey ? rule.category_title ?? null : null;
}
interface PositionedNode {
    node: GraphNode;
    x: number;
    y: number;
    team: number;
}
function ExactApproval({ api, planId, onClose, onSaved }: {
    api: AltoApiContext;
    planId: string;
    onClose: () => void;
    onSaved: () => void;
}) {
    const plan = useResource<PlanReview>(api, `/plans/${planId}`);
    const command = useCommand();
    const [confirmed, setConfirmed] = useState(false);
    return <Modal title="Review the exact plan" onClose={onClose} wide>
<p>Schedule verification, plan approval and employee-brief disclosure are separate decisions. Review each requirement before committing.</p>{plan.loading && <Loading />}<ErrorNotice error={plan.error ?? command.error} retry={plan.refresh}/>{plan.data && <>
<div className="alto-approval-binding">
<strong>Immutable proposal</strong>
<code>{plan.data.binding.proposal_digest}</code>
<small>Revision {plan.data.binding.base_company_revision} · {humanize(plan.data.status)}</small>
</div>
<div className="alto-compact-table">{plan.data.tasks.map((task) => <div key={task.task_id}>
<strong>{task.task_key} · {task.title}</strong>
<span>{dateTime(task.start_at)} – {dateTime(task.finish_at)}</span>
</div>)}</div>{plan.data.requirements.map((requirement) => <div className="alto-approval-requirement" key={requirement.requirement_id}>
<div>
<Badge>{requirement.domain === "disclosure" ? "Brief audience approval" : "Plan approval"}</Badge>
<p>{requirement.reason}</p>
<small>{requirement.authority_kind} · {humanize(requirement.status)}</small>
</div>
<button className="alto-secondary" disabled={command.busy || requirement.status !== "pending"} onClick={() => void command.run(async () => { if (!plan.data)
        return; await approveRequirement(api, plan.data, requirement); plan.refresh(); onSaved(); })}>{requirement.status === "pending" ? "Approve exact requirement" : humanize(requirement.status)}</button>
</div>)}<label className="alto-checkbox">
<input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)}/>I have reviewed this exact schedule and its approved audience.</label>
<button className="alto-primary" disabled={command.busy || !plan.data.can_commit || !confirmed} title={!plan.data.can_commit ? "All current requirements and revision checks must pass before commit" : undefined} onClick={() => void command.run(async () => { if (!plan.data)
        return; await commitPlan(api, plan.data); onSaved(); onClose(); })}>Commit approved plan</button>
</>}</Modal>;
}
function CandidateBindings({ value }: { value: CandidateValue | null }) {
    const rows = bindingRows(value);
    if (!rows.length) return null;
    return <div className="alto-rule-bindings">
<strong>Fixed candidate values</strong>
<dl>{rows.map((row, index) => <div key={`${row.label}:${index}`}><dt>{row.label}</dt><dd>{row.value}</dd></div>)}</dl>
</div>;
}
function RuleEvidence({ api, projectId, proposalId, rule, canLoadTechnical, preZ3Rejected }: {
    api?: AltoApiContext;
    projectId: string;
    proposalId: string;
    rule: RuleResult;
    canLoadTechnical: boolean;
    preZ3Rejected?: boolean;
}) {
    const detailPath = rule.technical_expression_available === true && canLoadTechnical
        ? `/projects/${encodeURIComponent(projectId)}/graph/rules/${encodeURIComponent(rule.id)}${proposalId ? `?proposal_id=${encodeURIComponent(proposalId)}` : ""}`
        : null;
    const detail = useResource<RuleTechnicalDetail>(api, detailPath);
    const unavailable = rule.technical_expression_available !== true;
    return <div className="alto-rule-evidence">
<div className="alto-rule-evidence-heading"><Badge tone={isPassingRule(rule) ? "mint" : "pending"}>{humanize(rule.status)}</Badge>{rule.encoding_version && <small>Encoding {rule.encoding_version}</small>}</div>
<p>{rule.description}</p>
{rule.source_label && <p><strong>Source</strong><br/>{rule.source_label}{rule.source_version ? ` · ${rule.source_version}` : ""}</p>}
{rule.formula && <div className="alto-human-formula"><strong>Human-readable rule</strong><code>{rule.formula}</code></div>}
<CandidateBindings value={rule.candidate_values}/>
<details className="alto-raw-assertion">
<summary>Raw Z3 assertion</summary>
<div>{unavailable ? <p>{preZ3Rejected ? "This candidate was rejected before Z3 assertions were executed. No raw assertion exists for this run." : "Raw assertion was not recorded for this run."}</p>
    : !canLoadTechnical ? <p>Raw assertions are available only in the manager verification view.</p>
        : detail.loading ? <p>Loading the recorded assertion…</p>
            : detail.error ? <p>Raw assertion is unavailable for this recorded run.</p>
                : detail.data?.technical_expression ? <><small>Encoding {detail.data.encoding_version ?? rule.encoding_version ?? "not recorded"}</small><pre>{detail.data.technical_expression}</pre></>
                    : <p>Raw assertion was not recorded for this run.</p>}</div>
</details>
</div>;
}
function VerificationCard({ summary }: { summary: VerificationSummary }) {
    const checked = isCheckedSummary(summary);
    return <section className={`alto-verification-card ${checked ? "checked" : "attention"}`} aria-label="Z3 verification summary">
<div className="alto-verification-title">
<div><small>Fixed-candidate verification</small><strong>{verificationLabel(summary)}</strong></div>
<span className={`alto-verification-signal ${checked ? "checked" : "attention"}`}><Icon name={checked ? "check" : "info"} size={17}/></span>
</div>
<div className="alto-verification-metrics">
<div><strong>{summary.covered_rule_count} / {summary.required_rule_count}</strong><span>Required rules covered</span></div>
<div><strong>{summary.unverified_rule_count}</strong><span>Unverified</span></div>
<div><strong>{summary.digests_match ? "Matched" : "Mismatch"}</strong><span>Digest identity</span></div>
<div><strong>{summary.independent_validation_passed ? "Passed" : "Not passed"}</strong><span>Independent validator</span></div>
</div>
<div className="alto-verification-versions">
<span>Z3 {summary.z3_version ?? "not recorded"}</span><span>Compiler {summary.compiler_version ?? "not recorded"}</span><span>Verifier {summary.verifier_version ?? "not recorded"}</span><span>Validator {summary.validator_version ?? "not recorded"}</span><span>{summary.duration_ms === null ? "Runtime not recorded" : `${summary.duration_ms} ms`}</span>
</div>
<dl className="alto-verification-digests"><div><dt>Candidate</dt><dd><code title={summary.candidate_digest ?? undefined}>{shortDigest(summary.candidate_digest)}</code></dd></div><div><dt>Snapshot</dt><dd><code title={summary.snapshot_digest ?? undefined}>{shortDigest(summary.snapshot_digest)}</code></dd></div></dl>
<div className="alto-verification-provenance"><Badge>{labelize(summary.author_kind)}</Badge><Badge tone={["approved", "committed"].includes(summary.approval_status.toLowerCase()) ? "mint" : "pending"}>Approval · {humanize(summary.approval_status)}</Badge></div>
<p className="alto-verification-limitation">Verification applies to this exact encoded snapshot. Independent validation and manager approval are separate.</p>
</section>;
}
function LegacyRuleList({ api, projectId, proposalId, rules, canLoadTechnical }: {
    api?: AltoApiContext;
    projectId: string;
    proposalId: string;
    rules: RuleResult[];
    canLoadTechnical: boolean;
}) {
    const [selectedRuleId, setSelectedRuleId] = useState<string | null>(rules.find(isViolation)?.id ?? null);
    return <div className="alto-rule-list">{[...rules].sort((left, right) => Number(isViolation(right)) - Number(isViolation(left))).map((rule, index) => <details key={rule.id} open={selectedRuleId === rule.id} onToggle={(event) => { if (event.currentTarget.open) setSelectedRuleId(rule.id); else if (selectedRuleId === rule.id) setSelectedRuleId(null); }}>
<summary>
<span className={`alto-rule-result ${rule.status}`}>{isPassingRule(rule) ? <Icon name="check" size={14}/> : <Icon name="info" size={14}/>}</span>
<small>{String(index + 1).padStart(2, "0")}</small>
<span>{rule.title}</span>
<Icon name="right" size={16}/>
</summary>
{selectedRuleId === rule.id && <RuleEvidence api={api} projectId={projectId} proposalId={proposalId} rule={rule} canLoadTechnical={canLoadTechnical}/>}</details>)}</div>;
}
function CategorisedRules({ api, projectId, proposalId, rules, canLoadTechnical, preZ3Rejected }: {
    api?: AltoApiContext;
    projectId: string;
    proposalId: string;
    rules: RuleResult[];
    canLoadTechnical: boolean;
    preZ3Rejected?: boolean;
}) {
    const known = new Set(RULE_CATEGORIES.map(([key]) => key));
    const categories: { key: string; title: string; rules: RuleResult[] }[] = RULE_CATEGORIES.map(([key, title]) => {
        const supportingRules = rules.filter((rule) => ruleCategoryKeys(rule).includes(key));
        return { key, title: supportingRules.map((rule) => ruleCategoryTitle(rule, key)).find(Boolean) || title, rules: supportingRules };
    });
    const otherRules = rules.filter((rule) => {
        const keys = ruleCategoryKeys(rule);
        return !keys.length || keys.every((key) => !known.has(key as typeof RULE_CATEGORIES[number][0]));
    });
    if (otherRules.length) categories.push({ key: "recorded_checks", title: "Other recorded checks", rules: otherRules });
    const initialCategory = categories.find((category) => category.rules.some(isViolation))?.key ?? null;
    const [openCategory, setOpenCategory] = useState<string | null>(initialCategory);
    const [selectedRuleId, setSelectedRuleId] = useState<string | null>(() => categories.find((category) => category.key === initialCategory)?.rules.find(isViolation)?.id ?? null);
    const activeCategory = categories.find((category) => category.key === openCategory);
    const selectedRule = activeCategory?.rules.find((rule) => rule.id === selectedRuleId) ?? null;
    return <div className="alto-rule-categories">
<div className="alto-rule-category-grid">{categories.map((category) => {
        const result = categoryResult(category.rules);
        const active = openCategory === category.key;
        return <button type="button" key={category.key} data-rule-category={category.key} className={`alto-rule-category ${result} ${active ? "selected" : ""}`} aria-expanded={active} aria-label={`${category.title} check category, ${labelize(result)}`} onClick={() => {
            if (active) { setOpenCategory(null); setSelectedRuleId(null); return; }
            setOpenCategory(category.key); setSelectedRuleId(category.rules.find(isViolation)?.id ?? null);
        }}>
<span className={`alto-rule-result ${result}`}>{result === "passed" ? <Icon name="check" size={13}/> : <Icon name="info" size={13}/>}</span>
<span><strong>{category.title}</strong><small>{category.rules.length ? `${category.rules.length} recorded` : "No recorded result"}</small></span>
</button>;
    })}</div>
{activeCategory && <section className="alto-rule-category-detail" aria-label={`${activeCategory.title} check details`}>
<header><div><small>Check category</small><h3>{activeCategory.title}</h3></div><Badge tone={categoryResult(activeCategory.rules) === "passed" ? "mint" : "pending"}>{labelize(categoryResult(activeCategory.rules))}</Badge></header>
{activeCategory.rules.length ? <>
<div className="alto-rule-instance-tabs">{activeCategory.rules.map((rule) => <button type="button" key={rule.id} data-rule-id={rule.id} className={rule.id === selectedRule?.id ? "selected" : ""} onClick={() => setSelectedRuleId(rule.id)}>{rule.title}</button>)}</div>
{selectedRule && <RuleEvidence api={api} projectId={projectId} proposalId={proposalId} rule={selectedRule} canLoadTechnical={canLoadTechnical} preZ3Rejected={preZ3Rejected}/>}</>
    : <p className="alto-muted">No rule result was recorded in this category for the selected verification run.</p>}
</section>}
</div>;
}
function RulesDrawer({ api, projectId, proposalId, rules, verificationSummary, canLoadTechnical, onClose }: {
    api?: AltoApiContext;
    projectId: string;
    proposalId: string;
    rules: RuleResult[];
    verificationSummary?: VerificationSummary | null;
    canLoadTechnical: boolean;
    onClose: () => void;
}) {
    const preZ3Rejected = Boolean(verificationSummary
        && verificationSummary.native_status.toLowerCase() === "invalid"
        && verificationSummary.covered_rule_count === 0);
    return <aside className="alto-graph-drawer">
<header>
<div><small className="alto-eyebrow">Z3 checker</small><h2>Planning rules</h2></div>
<IconButton icon="close" label="Close planning rules" onClick={onClose}/>
</header>
{verificationSummary ? <VerificationCard summary={verificationSummary}/> : <p className="alto-muted">{rules.length} deterministic checks recorded for this exact proposal. Violations are opened first; these are verifier results, not hidden AI reasoning.</p>}
{preZ3Rejected && <p className="alto-info-banner"><strong>No Z3 assertion ran for this candidate.</strong><br/>It was rejected during fixed-candidate admission before the solver stage. Select a checked authored-replay proposal from Proposal history, or create a new authored-replay run.</p>}
{rules.length || verificationSummary ? verificationSummary
    ? <CategorisedRules api={api} projectId={projectId} proposalId={proposalId} rules={rules} canLoadTechnical={canLoadTechnical} preZ3Rejected={preZ3Rejected}/>
    : <LegacyRuleList api={api} projectId={projectId} proposalId={proposalId} rules={rules} canLoadTechnical={canLoadTechnical}/>
    : <EmptyState title="No verification recorded">Rules appear after an exact candidate has been checked.</EmptyState>}</aside>;
}
export function ProjectGraph({ api, projectId, taskId, initialPanel, initialPlanId, employee = false, breathing = true, locked = false }: {
    api?: AltoApiContext;
    projectId: string;
    taskId?: string | null;
    initialPanel?: string | null;
    initialPlanId?: string | null;
    employee?: boolean;
    breathing?: boolean;
    locked?: boolean;
}) {
    const [proposalId, setProposalId] = useState("");
    const selector = proposalId ? `?proposal_id=${encodeURIComponent(proposalId)}` : initialPlanId ? `?plan_id=${encodeURIComponent(initialPlanId)}` : "";
    const resource = useResource<ProjectGraphData>(api, `/projects/${encodeURIComponent(projectId)}/graph${selector}`);
    const [selectedId, setSelectedId] = useState<string | null>(taskId ?? null);
    const [panel, setPanel] = useState(initialPanel === "rules" ? "rules" : "task");
    const [listView, setListView] = useState(false);
    const [mine, setMine] = useState(employee);
    const [search, setSearch] = useState("");
    const [expandedTeams, setExpandedTeams] = useState<number[]>([]);
    const [zoom, setZoom] = useState(1);
    const [pan, setPan] = useState({ x: 0, y: 0 });
    const [approval, setApproval] = useState(false);
    const [work, setWork] = useState(false);
    const container = useRef<HTMLDivElement>(null);
    const drag = useRef<{
        x: number;
        y: number;
        startX: number;
        startY: number;
    } | null>(null);
    const data = resource.data;
    const selected = data?.nodes.find((node) => node.id === selectedId) ?? null;
    const positions = useMemo(() => {
        if (!data)
            return [];
        const result: PositionedNode[] = [];
        for (let team = 0; team < TEAMS.length; team++) {
            const nodes = data.nodes.filter((node) => !isGoalGate(node) && teamIndex(node.team) === team).sort((a, b) => a.task_key.localeCompare(b.task_key, undefined, { numeric: true }));
            const centre = originFor(team);
            nodes.forEach((node, index) => {
                // Stable outward fans reserve label space instead of letting radial
                // labels overlap the hub or disappear beyond the SVG viewport.
                const bottom = team === 3;
                const x = bottom ? 190 + index * Math.min(235, 720 / Math.max(1, nodes.length - 1)) : team === 0 || team === 4 ? 30 : 900;
                const y = bottom ? 650 : centre.y + (index - (nodes.length - 1) / 2) * Math.min(66, 250 / Math.max(1, nodes.length - 1));
                result.push({ node, team, x, y });
            });
        }
        for (const node of data.nodes.filter(isGoalGate)) result.push({ node, team: 5, x: 550, y: node.task_key === "R1" ? 102 : 448 });
        return result;
    }, [data]);
    function select(node: GraphNode) { setSelectedId(node.id); setPanel("task"); }
    function dragStart(event: PointerEvent<SVGSVGElement>) { if ((event.target as Element).closest("[data-node]"))
        return; drag.current = { x: event.clientX, y: event.clientY, startX: pan.x, startY: pan.y }; event.currentTarget.setPointerCapture(event.pointerId); }
    function dragMove(event: PointerEvent<SVGSVGElement>) { if (!drag.current)
        return; const rect = event.currentTarget.getBoundingClientRect(); setPan({ x: drag.current.startX + (event.clientX - drag.current.x) * 1100 / rect.width, y: drag.current.startY + (event.clientY - drag.current.y) * 690 / rect.height }); }
    if (resource.loading && !data)
        return <Loading label="Loading the authorised project graph…"/>;
    if (resource.error && !data)
        return <ErrorNotice error={resource.error} retry={resource.refresh}/>;
    if (!data)
        return <EmptyState title="Project unavailable">Sign in to open the authorised project.</EmptyState>;
    const violations = data.rules.filter(isViolation);
    const unresolved = data.rules.filter((rule) => !isPassingRule(rule) && !isViolation(rule));
    const scheduleChecked = data.verification_summary ? isCheckedSummary(data.verification_summary) : ["passed", "checked", "committed"].includes(data.check_status.toLowerCase());
    const hasFailedCheck = violations.length > 0 || unresolved.length > 0 || ["violations_found", "failed"].includes(data.check_status.toLowerCase()) || Boolean(data.verification_summary && !scheduleChecked);
    const assistantContext = data.is_candidate_preview && data.selected_proposal_id
        ? { kind: "project" as const, id: projectId, proposal_id: data.selected_proposal_id, label: selected ? `${selected.task_key} · ${selected.title}` : data.project.title }
        : selected ? { kind: "task" as const, id: selected.id, label: `${selected.task_key} · ${selected.title}` }
            : { kind: "project" as const, id: projectId, label: data.project.title };
    const visible = positions.filter(({ node, team }) => (isGoalGate(node) || expandedTeams.includes(team) || node.status !== "accepted" || node.id === selectedId) && (!mine || node.is_mine) && `${node.task_key} ${node.title} ${node.owner_name ?? ""}`.toLowerCase().includes(search.toLowerCase()));
    return <div ref={container} className={`alto-graph-page ${breathing ? "breathing" : ""} ${panel === "rules" || selected ? "with-inspector" : ""}`}>
    <ErrorNotice error={resource.error} retry={resource.refresh}/>
    <PageHeading eyebrow={<>
<button className="alto-text-button" onClick={() => navigate("/projects")}>{employee ? "My projects" : "Projects"}</button>
<span> / {data.project.title}</span>
</>} title={data.project.title} subtitle={employee ? "Your work is highlighted" : `${humanize(data.project.status)}${data.project.deadline ? ` · Requested ${dateTime(data.project.deadline, data.timezone)}` : ""}`} actions={!employee && <>
<Badge tone={scheduleChecked ? "mint" : "neutral"}>{scheduleChecked ? "Schedule checked" : humanize(data.check_status)}</Badge>
<button className="alto-secondary" onClick={() => setPanel(panel === "rules" ? "task" : "rules")}>Rules</button>
<button className="alto-primary" disabled={!data.can_approve || !data.plan_id || !api} title={data.approval_disabled_reason ?? undefined} onClick={() => setApproval(true)}>Approve plan</button>
</>}/>
    {hasFailedCheck && <section className="alto-violation-summary" aria-label="Recorded planning violations">
<div>
<strong>{violations.length ? `${violations.length} recorded rule ${violations.length === 1 ? "violation" : "violations"}` : "This proposal did not pass every recorded check"}</strong>
<p>These are deterministic checks against the exact proposal shown here. No work has been assigned.</p>
</div>
{violations.length > 0 && <ul>{violations.slice(0, 3).map((rule) => <li key={rule.id}><strong>{humanize(rule.title)}</strong><span>{rule.description}{rule.source_label ? ` Source: ${rule.source_label}${rule.source_version ? ` · ${rule.source_version}` : ""}.` : ""}</span></li>)}</ul>}
{unresolved.length > 0 && <p>{unresolved.length} additional check {unresolved.length === 1 ? "needs" : "need"} review because the verifier could not produce a pass or violation.</p>}
<button className="alto-secondary" onClick={() => setPanel("rules")}>Review all recorded checks</button>
    </section>}
    <div className="alto-graph-toolbar">
{Boolean(data.candidate_history?.length) && <label className="alto-candidate-select">Proposal history<select aria-label="Proposal history" value={proposalId} onChange={(event) => { setProposalId(event.target.value); setSelectedId(null); setPanel("rules"); setApproval(false); setWork(false); }}><option value="">Current project view</option>{data.candidate_history?.map((candidate) => <option key={candidate.proposal_id} value={candidate.proposal_id}>v{candidate.version}{locked ? "" : ` · ${humanize(candidate.author_kind)}`} · {humanize(candidate.product_status)}{candidate.independent_validation_passed === false ? " · validation failed" : ""}</option>)}</select></label>}
<div className="alto-segmented">
<button className={mine ? "selected" : ""} onClick={() => setMine(true)}>My tasks</button>
<button className={!mine ? "selected" : ""} onClick={() => setMine(false)}>All permitted tasks</button>
</div>
    {data.is_candidate_preview && <p className="alto-caption">Exact recorded candidate preview. This does not change the committed schedule. Selected evidence: <code>{data.candidate_history?.find((candidate) => candidate.proposal_id === data.selected_proposal_id)?.candidate_digest ?? data.selected_proposal_id}</code></p>}
<label className="alto-search">
<Icon name="search" size={18}/>
<input aria-label="Search graph tasks" placeholder="Search tasks…" value={search} onChange={(event) => setSearch(event.target.value)}/>
</label>
<button className="alto-text-button" onClick={() => setListView(!listView)}>{listView ? "Graph view" : "Accessible list"}</button>
</div>
    <div className={`alto-graph-layout ${panel === "rules" || selected ? "with-drawer" : ""}`}>
<div className="alto-graph-main">
      {listView ? <div className="alto-task-table">
<table>
<thead>
<tr>
<th>Task</th>
<th>Owner</th>
<th>Status</th>
<th>Window</th>
<th>Dependencies</th>
</tr>
</thead>
<tbody>{positions.filter(({ node }) => (!mine || node.is_mine) && `${node.task_key} ${node.title}`.toLowerCase().includes(search.toLowerCase())).map(({ node }) => <tr key={node.id}>
<td>
<button className="alto-text-button" onClick={() => select(node)}>{node.task_key} · {node.title}</button>
</td>
<td>{node.owner_name ?? "Unassigned"}</td>
<td>{humanize(node.status)}</td>
<td>{dateTime(node.start_at, data.timezone)} – {dateTime(node.finish_at, data.timezone)}</td>
<td>{data.edges.filter((edge) => edge.to === node.id).map((edge) => `${data.nodes.find((source) => source.id === edge.from)?.task_key ?? "Permitted predecessor"} (${edge.kind})`).join(", ") || "None recorded"}</td>
</tr>)}</tbody>
</table>
</div> : <svg className="alto-graph-svg" viewBox="0 0 1140 690" role="group" aria-label="Goal-centred project graph. Use Accessible list for tabular details." onPointerDown={dragStart} onPointerMove={dragMove} onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }} onWheel={(event) => { if (event.ctrlKey || event.metaKey)
            setZoom((value) => Math.min(2, Math.max(0.55, value - event.deltaY * 0.002))); }}>
        <defs>
<marker id="alto-edge-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto">
<path d="M0 0 6 3 0 6" fill="none" stroke="#7e9dc3"/>
</marker>
</defs>
        <g transform={`translate(${pan.x + 550 * (1 - zoom)} ${pan.y + 340 * (1 - zoom)}) scale(${zoom})`}>
          {TEAM_POSITIONS.map((position, index) => <path key={`hub:${index}`} className="alto-structure-edge" d={`M550 340 Q${550 + (position.x - 550) * 0.4} ${position.y} ${position.x} ${position.y}`}/>)}
          {visible.map(({ node, x, y, team }) => <path key={`stem:${node.id}`} className="alto-structure-edge" d={`M${originFor(team).x} ${originFor(team).y} Q${x - (x - originFor(team).x) * 0.45} ${originFor(team).y} ${x} ${y}`}/>)}
          {data.edges.filter((edge) => edge.kind !== "dependency" || selectedId === edge.from || selectedId === edge.to).map((edge) => { const from = visible.find(({ node }) => node.id === edge.from), to = visible.find(({ node }) => node.id === edge.to); return from && to ? <g key={edge.id}>
<path className={`alto-dependency-edge ${edge.kind}`} d={`M${from.x} ${from.y} Q${(from.x + to.x) / 2} ${Math.min(from.y, to.y) - 50} ${to.x} ${to.y}`} markerEnd="url(#alto-edge-arrow)"/>
<title>{edge.label || edge.kind}</title>
</g> : null; })}
          <g className="alto-goal">
<circle cx="550" cy="340" r="89"/>
<circle cx="550" cy="340" r="81"/>
{goalLines(data.project.goal_label || data.project.title).map((line, index) => <text key={index} x="550" y={(data.project.goal_label ? 335 : 319) + index * 24} textAnchor="middle">{line}</text>)}
{!data.project.goal_label && <text x="550" y="371" textAnchor="middle">{data.project.deadline ? formatGoalDay(data.project.deadline, data.timezone) : "Project goal"}</text>}{data.project.status === "completed" && <text x="550" y="396" textAnchor="middle">✓ Accepted</text>}</g>
          {TEAM_POSITIONS.map((position, index) => { const teamNodes = data.nodes.filter((node) => !isGoalGate(node) && teamIndex(node.team) === index), accepted = teamNodes.filter((node) => node.status === "accepted").length; return <g key={TEAMS[index]} className={`alto-hub team-${index}`} role="button" tabIndex={0} aria-label={`${TEAMS[index]}: ${accepted} of ${teamNodes.length} accepted. Toggle completed tasks.`} data-node="hub" onClick={() => setExpandedTeams((current) => current.includes(index) ? current.filter((value) => value !== index) : [...current, index])} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            setExpandedTeams((current) => current.includes(index) ? current.filter((value) => value !== index) : [...current, index]);
        } }}>
<circle cx={position.x} cy={position.y} r="43"/>
<foreignObject x={position.x - 18} y={position.y - 18} width="36" height="36"><Icon name={TEAM_ICONS[index] ?? "projects"} size={36}/></foreignObject>
<text className="alto-hub-label" x={position.x} y={position.y + 65} textAnchor="middle">{TEAMS[index]}</text><text className="alto-aggregate-label" x={position.x} y={position.y + 84} textAnchor="middle">{accepted > 0 ? `${accepted}/${teamNodes.length} accepted · ${expandedTeams.includes(index) ? "collapse" : "expand"}` : `${teamNodes.length} tasks`}</text></g>; })}
          {visible.map(({ node, x, y, team }) => { return <g key={node.id} className={`alto-graph-node team-${team} ${selectedId === node.id ? "selected" : ""} ${node.is_mine ? "mine" : ""}`} role="button" tabIndex={0} aria-label={`${node.task_key}: ${node.title}. ${humanize(node.status)}. ${node.owner_name ?? "Unassigned"}`} data-node={node.id} onClick={() => select(node)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            select(node);
        } }}>
<circle className="alto-node-fill" cx={x} cy={y} r="15"/>
<circle className="alto-node-progress" cx={x} cy={y} r="18" strokeDasharray={`${(4 - statusStep(node.status)) * 28.27} 113.1`} transform={`rotate(-90 ${x} ${y})`}/>{node.status === "accepted" && <text x={x} y={y + 5} textAnchor="middle">✓</text>}<text x={x + 27} y={y - 2}>{node.task_key} · {node.title.length > 19 ? `${node.title.slice(0, 17)}…` : node.title}</text>
<text className="alto-node-owner" x={x + 27} y={y + 18}>{node.owner_name ?? "Unassigned"}</text>
</g>; })}
        </g>
      </svg>}
      <div className="alto-graph-bottom">
<div className="alto-zoom">
<IconButton icon="minus" label="Zoom out" onClick={() => setZoom((value) => Math.max(0.55, value - 0.1))}/>
<span>{Math.round(zoom * 100)}%</span>
<IconButton icon="plus" label="Zoom in" onClick={() => setZoom((value) => Math.min(2, value + 0.1))}/>
<IconButton icon="fit" label="Fit graph" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }}/>
<button className="alto-text-button" onClick={() => { if (document.fullscreenElement)
        void document.exitFullscreen().catch(() => undefined);
    else
        void container.current?.requestFullscreen().catch(() => undefined); }}>Full screen</button>
</div>
<div className="alto-legend">{TEAMS.map((team, index) => <span key={team}>
<i className={`team-${index}`}/>{team}</span>)}</div>
</div>
      <Assistant key={`${selected?.id ?? projectId}:${data.selected_proposal_id ?? "committed"}`} api={api} context={assistantContext} placeholder={selected ? "Ask about this task…" : "Ask ALTO about this plan…"}/>
    </div>
    {panel === "rules" ? <RulesDrawer key={data.selected_proposal_id ?? "current"} api={api} projectId={projectId} proposalId={data.verification_summary?.proposal_id ?? data.selected_proposal_id ?? proposalId} rules={data.rules} verificationSummary={data.verification_summary} canLoadTechnical={!employee} onClose={() => setPanel("task")}/> : selected && <aside className="alto-graph-drawer alto-task-inspector">
<header>
<h2>{selected.task_key} · {selected.title}</h2>
<IconButton icon="close" label="Close task inspector" onClick={() => setSelectedId(null)}/>
</header>
<p>
<span className={`alto-status-dot team-${teamIndex(selected.team)}`}/>{selected.owner_name ?? "Unassigned"} · {selected.team}</p>
<dl>
<dt>When</dt>
<dd>
<Icon name="calendar"/>{dateTime(selected.start_at, data.timezone)} – {dateTime(selected.finish_at, data.timezone)}<small>{data.timezone}</small>
</dd>
<dt>Reviewer</dt>
<dd>{selected.reviewer_name ?? "No reviewer recorded"}</dd>
<dt>Status</dt>
<dd>
<Badge>{humanize(selected.status)}</Badge>
</dd>
</dl>
<p>{selected.summary || "No additional disclosed brief."}</p>
<h3>Depends on</h3>{data.edges.filter((edge) => edge.to === selected.id).map((edge) => <button className="alto-dependency-link" key={edge.id} onClick={() => { const predecessor = data.nodes.find((node) => node.id === edge.from); if (predecessor)
        select(predecessor); }}>{data.nodes.find((node) => node.id === edge.from)?.title ?? "Permitted predecessor"}<small>{humanize(edge.kind)}</small>
</button>)}{data.is_candidate_preview && <p className="alto-caption" role="status">This is a proposed task preview. Its approved brief and work record become available after the exact plan is approved and committed.</p>}<div className="alto-button-stack">
<button className="alto-secondary" disabled={data.is_candidate_preview} title={data.is_candidate_preview ? "Available after this plan is committed" : undefined} onClick={() => navigate(`/tasks/${selected.id}`)}>{data.is_candidate_preview ? "Brief available after commit" : "Open approved brief"}</button>
<button className="alto-primary" disabled={data.is_candidate_preview} title={data.is_candidate_preview ? "Available after this plan is committed" : undefined} onClick={() => setWork(true)}>{data.is_candidate_preview ? "Work available after commit" : selected.can_work ? "Open work and submission" : "Inspect task work"}</button>
</div>
</aside>}
    </div>{approval && api && data.plan_id && <ExactApproval api={api} planId={data.plan_id} onClose={() => setApproval(false)} onSaved={resource.refresh}/>}{work && api && selected && <TaskWorkModal api={api} taskId={selected.id} onClose={() => setWork(false)} onSaved={resource.refresh}/>}
  </div>;
}
function formatGoalDay(value: string, timezone: string) { return new Intl.DateTimeFormat(undefined, { weekday: "long", timeZone: timezone }).format(new Date(value)); }
function goalLines(title: string): string[] {
    const words = title.split(/\s+/), lines = [""];
    for (const word of words) { const last = lines.length - 1; if (`${lines[last]} ${word}`.trim().length > 18 && lines[last]) lines.push(word); else lines[last] = `${lines[last]} ${word}`.trim(); }
    return lines.slice(0, 2).map((line, index) => index === 1 && lines.length > 2 ? `${line.slice(0, 16)}…` : line.slice(0, 18));
}
