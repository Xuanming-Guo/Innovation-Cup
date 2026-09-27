/** TEST ONLY. Loaded by the CDP capture runner, never imported by the application. */
import React from "react";
import { createRoot } from "react-dom/client";
import { AltoShell } from "../alto-shell";
import { defaultPreferences, type Project, type GraphNode } from "../alto-api";
import "../styles.css";
import "../alto.css";

const employee = new URLSearchParams(location.search).get("visual") === "employee";
const capture = new URLSearchParams(location.search).get("capture");
// The isolated capture profile needs real-shaped selectors for the shell's scope parser.
// These are fixture IDs only, never credentials or authority for a real API.
if (capture === "F02-plan-request-preview" || capture === "F03-stopped-planning-conversation" || capture === "F04-active-planning") {
  localStorage.setItem("alto.scope.fixture-user.fixture-company", JSON.stringify({ run: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", actor: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb" }));
}
const fixtureDate = "2026-09-28T09:00:00Z";
const demoIntake = {
  kind: "northstar_launch",
  title: "Approved Northstar launch",
  original_request: "Prepare our analytics product for launch this Friday at 10 a.m. Coordinate Engineering, Design, QA, Marketing and Customer Support. Propose the remaining tasks, owners, reviews and handoffs. Respect existing commitments and working hours, and bring the plan to me for approval.",
  description: "This demo supports only the approved Northstar launch request. Free-form demo planning does not have the required typed authority. Use 'Prepare the Northstar launch plan' from Home; Ask a question remains available.",
};
const project: Project = { id: "northstar", title: "Northstar analytics product launch", goal_label: "Launch ready for Friday", status: "committed", deadline: "2026-10-02T17:00:00Z", updated_at: fixtureDate, task_count: 17, completed_task_count: 2, plan_id: "plan-1", description: "A coordinated five-team product launch with exact readiness and acceptance gates." };
const completed: Project = { ...project, id: "accepted", title: "Analytics discovery", status: "completed", accepted_at: fixtureDate, accepted_by: "Maya" };
const nodeEntries = [
  ["E1", "Prepare analytics instrumentation", "Engineering", "Alex", "in_progress"],
  ["E2", "Integrate release build", "Engineering", "Alex", "assigned"],
  ["L1", "Publish approved launch", "Engineering", "Alex", "assigned"],
  ["D1", "Approve the launch design", "Design", "Iris", "accepted"],
  ["D2", "Review exact design package", "Design", "Maya", "assigned"],
  ["Q1", "Verify the launch build", "QA", "Priya", "assigned"],
  ["Q2", "Review readiness evidence", "QA", "Priya", "assigned"],
  ["Q3", "Post-release acceptance", "QA", "Priya", "assigned"],
  ["M1", "Prepare campaign assets", "Marketing", "Nora", "acknowledged"],
  ["M2", "Final launch visuals", "Marketing", "Iris", "assigned"],
  ["M3", "Accept messaging package", "Marketing", "Nora", "assigned"],
  ["S1", "Draft guide outline", "Support", "Sam", "accepted"],
  ["S2", "Finalise support guide", "Support", "Sam", "assigned"],
  ["S3", "Review exact support guide", "Support", "Priya", "assigned"],
  ["S4", "Prepare support coverage", "Support", "Sam", "submitted"],
  ["R1", "Launch readiness", "Readiness", "Maya", "assigned"],
  ["R2", "Final launch acceptance", "Readiness", "Maya", "assigned"],
];
const nodes: GraphNode[] = nodeEntries.map(([key, title, team, owner, status]) => ({ id: key!, task_key: key!, title: title!, team: team!, owner_name: owner!, owner_employee_id: key === "E1" ? "jordan" : "other", status: status!, start_at: "2026-09-28T10:00:00Z", finish_at: "2026-09-30T16:00:00Z", reviewer_name: "Priya", summary: "Review the approved brief and preserve the team's existing commitments.", is_mine: employee && key === "E1", can_work: employee && key === "E1", row_version: 1 }));
const task = { task_id: "E1", task_key: "E1", title: "Prepare analytics instrumentation", status: "in_progress", scheduling_kind: "active_work", active_minutes: 120, row_version: 2, start_at: "2026-09-28T10:00:00Z", finish_at: "2026-09-29T16:00:00Z", assigned_employee_id: "jordan", approved_brief: { content: { summary: "Instrument the approved analytics events for the Northstar launch. Preserve existing customer commitments and coordinate the exact release handoff with QA.", deliverables: ["Implement the agreed event schema", "Attach the event validation results", "Document the exact QA handoff"] }, version: 1 }, latest_submission: null };
const calendar = { timezone: "UTC", sources: [{ name: "Outlook calendar", status: "fixture" }], items: [
  { id: "c1", title: "Team check-in", start_at: "2026-09-28T09:00:00Z", end_at: "2026-09-28T09:45:00Z", kind: "meeting", source: "Outlook calendar", status: "confirmed", task_id: null, project_id: null, description: "External meeting. Not editable by ALTO.", owner_name: "Maya" },
  { id: "c2", title: "Analytics instrumentation", start_at: "2026-09-28T10:00:00Z", end_at: "2026-09-28T12:00:00Z", kind: "work", source: "ALTO", status: "in_progress", task_id: "E1", project_id: "northstar", description: "Approved active-work reservation", owner_name: "Alex" },
  { id: "c3", title: "Protected customer commitment", start_at: "2026-09-29T13:00:00Z", end_at: "2026-09-29T15:00:00Z", kind: "protected", source: "Existing commitment", status: "protected", task_id: null, project_id: null, description: "Cannot be displaced by a launch proposal.", owner_name: null },
  { id: "c4", title: "QA handoff", start_at: "2026-09-30T11:00:00Z", end_at: "2026-09-30T12:00:00Z", kind: "meeting", source: "Outlook calendar", status: "confirmed", task_id: "Q1", project_id: "northstar", description: "Named reviewer handoff", owner_name: "Priya" },
  { id: "c5", title: "Launch deadline", start_at: "2026-10-02T17:00:00Z", end_at: "2026-10-02T17:00:00Z", kind: "deadline", source: "ALTO", status: "planned", task_id: "R2", project_id: "northstar", description: "Deadline marker, not a meeting.", owner_name: "Maya" },
] };
const privatePreference = { id: "pref-1", text: "I work best with uninterrupted morning focus time. Could future planning keep meetings later where possible?", status: "draft", row_version: 1, manager_id: "maya", manager_name: "Maya", shared_at: null };
const people = { id: "jordan", timezone: "UTC", display_name: "Alex", job_title: "Integration Engineer", operating_group: "Northstar", function: "Engineering", profile_depth: "accepted_history", row_version: 1, skills: [{ name: "TypeScript", provenance: "self_declared" }, { name: "Analytics", provenance: "accepted_work" }, { name: "API integration", provenance: "self_declared" }], past_projects: [completed], ongoing_projects: [project], availability: calendar.items.filter((item) => item.kind !== "deadline").map((item) => ({ ...item, title: "Busy", description: "", kind: "busy" })), shared_preferences: [] };
let preferences = { ...defaultPreferences };
let messages: { id: string; role: string; content: string; created_at: string; citations: { label: string; target_path: string }[] }[] = [];
const verificationSummary = {
  proposal_id: "fixture-p1-proposal", author_kind: "authored_replay", product_status: "CHECKED", native_status: "sat", z3_version: "4.13.4",
  compiler_version: "alto-fixed-candidate-compiler.v1", verifier_version: "alto-fixed-candidate-verifier.v3", duration_ms: 218,
  required_rule_count: 12, covered_rule_count: 12, unverified_rule_count: 0,
  candidate_digest: "sha256:7bd5c497f71380f591697570abc123cdb8e623a20b8022f3a8f32c8d768531f5",
  snapshot_digest: "sha256:341c1556af816258da55cc39abc123b5527ca70fb5c4fc5c75560f986444bc2e",
  digests_match: true, independent_validation_passed: true, validator_version: "alto-fixed-candidate-validator.v1", approval_status: "committed",
};
const verificationRules = [
  ["81000000-0000-4000-8000-000000000001", "owner", "Owner", "Owner binding", "Every task is fixed to one admitted owner.", "owner(Q1) = Priya", { task: "Q1", owner: "Priya" }],
  ["81000000-0000-4000-8000-000000000002", "working_hours", "Working hours", "Working-hours boundary", "The fixed interval stays inside Priya's recorded working hours.", "work_start <= start(Q1) < finish(Q1) <= work_finish", { task: "Q1", working_hours: "Tuesday 09:00–17:00" }],
  ["81000000-0000-4000-8000-000000000003", "busy_time", "Busy time", "Busy-time exclusion", "The fixed interval does not overlap imported busy time.", "active(Q1) ∩ busy(Priya) = ∅", { task: "Q1", imported_busy_intervals: "0 overlaps" }],
  ["81000000-0000-4000-8000-000000000004", "effort", "Effort", "Effort equality", "The fixed active block accounts for the admitted effort.", "active_minutes(Q1) = admitted_effort(Q1)", { task: "Q1", active_minutes: 120, admitted_minutes: 120 }],
  ["81000000-0000-4000-8000-000000000005", "eligibility", "Eligibility", "Eligibility domain", "Priya is in the admitted owner domain for QA review.", "owner(Q1) ∈ eligible(Q1)", { task: "Q1", owner: "Priya", eligibility: "QA reviewer" }],
  ["81000000-0000-4000-8000-000000000006", "dependencies", "Dependencies", "Dependency order", "The release build finishes before Q1 begins.", "finish(E2) <= start(Q1)", { predecessor: "E2", successor: "Q1" }],
  ["81000000-0000-4000-8000-000000000007", "participants", "Participants", "Participant reservation", "Every required participant is reserved for the fixed interval.", "participants(Q1) = reserved(Q1)", { task: "Q1", participants: ["Priya"] }],
  ["81000000-0000-4000-8000-000000000008", "handoffs", "Handoffs", "Handoff gate", "The named QA handoff follows the completed release build.", "handoff(Q1).start >= finish(E2)", { handoff: "Release build → QA", owner: "Priya" }],
  ["81000000-0000-4000-8000-000000000009", "protected_time", "Protected time", "Protected capacity · Q1", "Q1 ends exactly when Priya's protected interval begins. Half-open intervals do not overlap.", "[09:00, 11:00) ∩ [11:00, 12:00) = ∅", { task: "Q1", fixed_interval: "Tuesday 09:00–11:00", owner: "Priya", protected_interval: "Tuesday 11:00–12:00", interval_semantics: "Half-open [start, finish)" }],
  ["81000000-0000-4000-8000-000000000010", "reviews", "Reviews", "Required review", "The fixed plan includes the named independent review.", "reviewer(Q1) = Priya ∧ reviewer(Q1) ≠ owner(E2)", { review: "Q1", reviewer: "Priya" }],
  ["81000000-0000-4000-8000-000000000011", "deadlines", "Deadlines", "Launch deadline", "The fixed plan completes before the admitted launch deadline.", "finish(R2) <= launch_deadline", { gate: "R2", deadline: "Friday 17:00" }],
  ["81000000-0000-4000-8000-000000000012", "authorised_scope", "Authorised scope", "Authorised movement", "Every fixed change remains inside the recorded planning authority.", "changed_task ⊆ authorised_scope", { scope: "Northstar launch", unauthorised_changes: 0 }],
].map(([id, category_key, category_title, title, description, formula, candidate_values]) => ({
  id, rule_id: `${category_key}.fixture`, category_key, category_title, title, description, formula, candidate_values,
  status: "passed", source_label: category_key === "protected_time" ? "Working hours and protected capacity" : "Northstar admitted snapshot",
  source_version: category_key === "protected_time" ? "capacity-v3" : "snapshot-v1", encoding_version: "alto-fixed-candidate-compiler.v1", technical_expression_available: true,
}));
const originalFetch = window.fetch.bind(window);
window.fetch = async (input, options) => {
  const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, location.origin);
  if (!url.pathname.startsWith("/v1/companies/fixture-company/")) return originalFetch(input, options);
  const path = url.pathname.replace("/v1/companies/fixture-company", "");
  const body = options?.body ? JSON.parse(String(options.body)) as Record<string, unknown> : {};
  let result: unknown;
  if (path === "/workspace") result = { company: { id: "fixture-company", name: "Northstar", is_demo: true }, viewer: { user_id: "fixture-user", employee_id: employee ? "jordan" : "maya", display_name: employee ? "Alex" : "Maya", role: employee ? "employee" : "manager", job_title: employee ? "Integration Engineer" : "Software Delivery Director" }, demo_run: { id: "fixture-run", mode: "authored_replay", clock_at: fixtureDate, actor_name: employee ? "Alex" : "Maya", row_version: 1, clock_version: 0 }, capabilities: [] };
  else if (path === "/me/preferences") { if (options?.method === "PATCH") preferences = { ...preferences, ...body }; result = preferences; }
  else if (path === "/home") result = { recent_projects: [project], completed_projects: [completed], actions: [{ id: "a1", title: "Review launch proposal", kind: "planning", status: "approval_required", target_path: "/projects/northstar/graph" }], tasks: [task, { ...task, task_id: "S4", title: "Support coverage evidence", status: "submitted" }] };
  else if (path === "/projects") result = { projects: [project, completed] };
  else if (path === "/demo/runs") result = { can_create: true, runs: [{ id: "fixture-run", name: "Northstar visual example", mode: "authored_replay", status: "active", clock_at: fixtureDate, clock_version: 1, row_version: 1, protected: false }], actors: [{ id: "maya", display_name: "Maya", job_title: "Delivery Director", role: "manager" }, { id: "iris", display_name: "Iris", job_title: "Designer", role: "employee" }] };
  else if (path === "/planning-context") result = { demo_intake: demoIntake, sources: [{ source_id: "brief", title: "Approved product and release brief", classification: "internal", source_kind: "fixture" }, { source_id: "handoff", title: "Directors’ launch handoff", classification: "internal", source_kind: "fixture" }, { source_id: "capacity", title: "Working hours and protected capacity", classification: "internal", source_kind: "fixture" }], requests: [{ request_id: "visual-failed", original_request: demoIntake.original_request, status: "interpreting", created_at: fixtureDate }] };
  else if (path === "/planning-requests/visual-failed") result = { request_id: "visual-failed", original_request: demoIntake.original_request, project_id: "northstar", intake_supported: true, intake_limitation: null, status: "interpreting", request_version: 1, latest_outcome: null, candidate_digest: null, candidate_contract_id: null, snapshot_id: null, plan_id: null, interpretation_job_state: "review_required", materialization_job_state: null, planning_job_state: null, interpretation_job: { job_id: "visual-stage-only", state: "review_required", attempt_count: 1, max_attempts: 6, last_error_code: "model_invalid_output", can_retry: true }, materialization_job: null, planning_job: null, clarifications: [] };
  else if (path === "/planning-requests/visual-active") result = { request_id: "visual-active", original_request: demoIntake.original_request, project_id: "northstar", intake_supported: true, intake_limitation: null, status: "interpreted", request_version: 1, latest_outcome: "admitted", candidate_digest: "fixture-digest", candidate_contract_id: "fixture-candidate", snapshot_id: null, plan_id: null, interpretation_job_state: "succeeded", materialization_job_state: "leased", planning_job_state: null, interpretation_job: { job_id: "visual-interpretation-only", state: "succeeded", attempt_count: 1, max_attempts: 6, last_error_code: null, can_retry: false }, materialization_job: { job_id: "visual-materialization-only", state: "leased", attempt_count: 1, max_attempts: 6, last_error_code: null, can_retry: false }, planning_job: null, clarifications: [] };
  else if (path === "/reviews/pending") result = { reviews: [] };
  else if (path.startsWith("/projects/northstar/graph/rules/")) {
    const ruleId = path.split("/").at(-1) ?? "";
    const rule = verificationRules.find((item) => item.id === ruleId);
    result = { rule_id: rule?.rule_id ?? ruleId, encoding_version: "alto-fixed-candidate-compiler.v1", technical_expression: ruleId.endsWith("000009") ? "(and (<= 1 1) (<= 1 1) (<= 1 1) (<= 1 1))" : `(and (= 1 1))` };
  }
  else if (path.endsWith("/graph")) result = { project, nodes, edges: [{ id: "dep1", from: "E1", to: "E2", kind: "dependency", label: "Finish before start" }, { id: "dep2", from: "E2", to: "Q1", kind: "review", label: "QA handoff" }, { id: "dep3", from: "D1", to: "M1", kind: "handoff", label: "Approved design" }, { id: "dep4", from: "S4", to: "R2", kind: "acceptance", label: "Exact submitted coverage" }], rules: verificationRules, verification_summary: verificationSummary, plan_id: "plan-1", can_approve: false, check_status: "committed", approval_disabled_reason: "This fixture plan is already committed.", timezone: "UTC" };
  else if (path === "/calendar") result = calendar;
  else if (path.startsWith("/people/")) result = people;
  else if (path === "/people") result = { people: [people] };
  else if (path === "/me/employee-preferences") result = { preferences: [privatePreference] };
  else if (path === "/me/feedback") result = { id: "feedback-1" };
  else if (path === "/tasks/E1") result = { task, project, owner_name: "Alex", reviewer_name: "Priya", approver_name: "Maya", timezone: "UTC", timeline: [{ id: "tl1", title: "Instrumentation work", start_at: "2026-09-28T10:00:00Z", end_at: "2026-09-28T12:00:00Z", kind: "active_work" }, { id: "tl2", title: "Review handoff", start_at: "2026-09-29T15:00:00Z", end_at: "2026-09-29T16:00:00Z", kind: "review" }], protected_commitments: ["Tuesday 13:00–15:00 — protected existing commitment"], attachments: [], can_work: employee, can_give_feedback: false, draft: null, gate: null };
  else if (path === "/connections") result = { connections: [{ id: "outlook", name: "Outlook calendar", provider: "microsoft", direction: "read", description: "Authorised calendar availability and confirmed events", scope: "Calendar.Read", status: "fixture", timezone: "UTC", imports: ["Calendar availability", "Confirmed events"], last_synced_at: fixtureDate, can_revoke: false, row_version: 1 }, { id: "documents", name: "Shared documents", provider: "sharepoint", direction: "read", description: "Approved project source versions", scope: "Selected project folder", status: "fixture", timezone: null, imports: ["Project brief", "Source excerpts"], last_synced_at: fixtureDate, can_revoke: false, row_version: 1 }, { id: "publish", name: "Task publication", provider: "alto", direction: "write", description: "Approved task and brief audience publication", scope: "Exact approved plan", status: "fixture", timezone: null, imports: ["Approved tasks"], last_synced_at: fixtureDate, can_revoke: false, row_version: 1 }] };
  else if (path === "/me/notifications") result = { notifications: [{ notification_id: "n1", message_key: "employee_preference_shared", subject_type: "employee_preference", subject_id: "pref-1", created_at: fixtureDate, seen_at: null }, { notification_id: "n2", message_key: "submission_ready_for_review", subject_type: "submission", subject_id: "submission-1", created_at: fixtureDate, seen_at: null }] };
  else if (path === "/assistant/threads") result = { id: "thread-1", messages, status: "idle", stage: null, error: null };
  else if (path.endsWith("/messages")) { messages = [...messages, { id: "msg-1", role: "user", content: String(body.content), created_at: fixtureDate, citations: [] }, { id: "msg-2", role: "assistant", content: "The launch has five coordinated teams. The current approved schedule preserves the existing customer commitment, and final acceptance remains an explicit decision after the required evidence is reviewed. This is a browser-test fixture, not a live model answer.", created_at: fixtureDate, citations: [{ label: "Launch project", target_path: "/projects/northstar/graph" }] }]; result = { id: "thread-1", messages, status: "succeeded", stage: null, error: null }; }
  else return new Response(JSON.stringify({ detail: `No visual-test fixture for ${path}` }), { status: 404, headers: { "Content-Type": "application/json" } });
  return new Response(JSON.stringify(result), { status: 200, headers: { "Content-Type": "application/json" } });
};
createRoot(document.getElementById("root")!).render(<React.StrictMode><div style={{ position: "fixed", bottom: 0, right: 0, zIndex: 99999, fontSize: 10, color: "#665216", background: "#fff2c5", padding: "3px 9px" }}>BROWSER VISUAL TEST · FIXTURE DATA · NOT LIVE</div><AltoShell config={{ apiMode: "static", apiOrigin: location.origin, productName: "ALTO", supabaseConfigured: false, supabaseUrl: null, supabasePublishableKey: null, defaultCompanyId: "fixture-company", hackathonDemo: false }} session={{ status: "connected", userId: "fixture-user", unreadNotifications: 2, administrativeRole: employee ? "member" : "company_admin", employeeId: employee ? "jordan" : "maya", api: { apiOrigin: location.origin, companyId: "fixture-company", accessToken: "visual-fixture-not-a-credential" } }} service={{ state: "reachable", detail: "Visual fixture" }} onSignOut={async () => {}} saveDeployment={() => {}} resetDeployment={() => {}} authController={{ current: null }}/></React.StrictMode>);
