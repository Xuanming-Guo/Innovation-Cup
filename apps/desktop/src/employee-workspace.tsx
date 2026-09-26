import { useMemo, useState } from "react";

const workViews = ["Today", "Upcoming", "Blocked", "Submitted"] as const;
type WorkView = (typeof workViews)[number];
type LifecycleState = "complete" | "current" | "pending" | "attention";

interface PreviewTask {
  id: string;
  view: WorkView;
  title: string;
  projectLabel: string;
  status: string;
  statusTone: "teal" | "rust" | "moss";
  timing: string;
  purpose: string;
  deliverable: string;
  approvedBrief: string;
  briefVersion: string;
  approvedInputs: readonly string[];
  effort: string;
  workWindow: string;
  deadline: string;
  reviewer: string;
  dependencies: string;
  permissionBoundary: string;
  assignmentRationale: string;
  nextAction: string;
  primaryAction: string;
  lifecycle: readonly {
    label: "Acknowledgement" | "Progress" | "Submission" | "Review";
    detail: string;
    state: LifecycleState;
  }[];
}

// Deliberately local preview content. It demonstrates the permission-safe employee
// projection without pretending an authenticated API response has been loaded.
const previewTasks = [
  {
    id: "preview-inputs",
    view: "Today",
    title: "Confirm the approved handoff inputs",
    projectLabel: "Customer demonstration",
    status: "Acknowledgement needed",
    statusTone: "rust",
    timing: "Due today, 12:00 JST",
    purpose: "Make sure the operating-guide author has the approved material needed to begin.",
    deliverable: "A confirmed list of usable inputs, with any missing item flagged for the reviewer.",
    approvedBrief: "Prepare a clear, reviewed operating guide for the customer demonstration. Use only the material approved for this team and raise missing context before drafting.",
    briefVersion: "Disclosure v3 - approved for assigned employees",
    approvedInputs: ["Customer-safe demonstration outline", "Approved onboarding checklist v4"],
    effort: "45 minutes active effort",
    workWindow: "Today, 09:00-12:00 JST",
    deadline: "Today, 12:00 JST",
    reviewer: "Aiko Tanaka - Operations reviewer",
    dependencies: "None. The guide draft waits for this confirmation.",
    permissionBoundary: "Use the two approved inputs listed here. Restricted planning notes and other teams' work are not available in this view.",
    assignmentRationale: "You own the current approved checklist and have capacity inside this work window.",
    nextAction: "Acknowledge the assignment, then confirm or flag the inputs.",
    primaryAction: "Acknowledge task",
    lifecycle: [
      { label: "Acknowledgement", detail: "Action needed", state: "current" },
      { label: "Progress", detail: "Not started", state: "pending" },
      { label: "Submission", detail: "Not submitted", state: "pending" },
      { label: "Review", detail: "Not reviewed", state: "pending" },
    ],
  },
  {
    id: "preview-notes",
    view: "Today",
    title: "Draft the environment setup notes",
    projectLabel: "Technical orientation",
    status: "In progress",
    statusTone: "teal",
    timing: "Work window closes 16:30 JST",
    purpose: "Give the new joiner a tested path through the local development setup.",
    deliverable: "A concise setup note covering prerequisites, first run and a safe rollback step.",
    approvedBrief: "Create an internal orientation note from the approved engineering handbook. Do not include customer credentials, private incident notes or unapproved infrastructure details.",
    briefVersion: "Disclosure v2 - approved for the orientation team",
    approvedInputs: ["Engineering handbook: local setup", "Approved toolchain matrix"],
    effort: "90 minutes active effort",
    workWindow: "Today, 13:30-16:30 JST",
    deadline: "Tomorrow, 10:00 JST",
    reviewer: "Ken Mori - Engineering reviewer",
    dependencies: "Handoff inputs acknowledged.",
    permissionBoundary: "Use only the approved handbook sections. Credentials and incident records remain outside this task.",
    assignmentRationale: "You recently completed the same documented setup; familiarity is a setup-cost signal, not a qualification score.",
    nextAction: "Continue the draft and submit the exact version you want reviewed.",
    primaryAction: "Submit work",
    lifecycle: [
      { label: "Acknowledgement", detail: "Acknowledged", state: "complete" },
      { label: "Progress", detail: "In progress", state: "current" },
      { label: "Submission", detail: "Not submitted", state: "pending" },
      { label: "Review", detail: "Not reviewed", state: "pending" },
    ],
  },
  {
    id: "preview-orientation",
    view: "Upcoming",
    title: "Run the technical orientation session",
    projectLabel: "Technical orientation",
    status: "Assigned",
    statusTone: "teal",
    timing: "Tomorrow, 14:00 JST",
    purpose: "Walk the new joiner through the approved development workflow.",
    deliverable: "A completed orientation session and a list of authorised follow-up questions.",
    approvedBrief: "Use the reviewed setup notes to run the scheduled orientation. Questions requiring restricted context must be routed to the named reviewer.",
    briefVersion: "Disclosure v2 - approved for the orientation team",
    approvedInputs: ["Accepted environment setup notes", "Orientation agenda"],
    effort: "60 minutes active effort",
    workWindow: "Tomorrow, 14:00-15:00 JST",
    deadline: "Tomorrow, 15:00 JST",
    reviewer: "Ken Mori - Engineering reviewer",
    dependencies: "Environment setup notes must be accepted.",
    permissionBoundary: "The session covers the approved development workflow only.",
    assignmentRationale: "You are the accountable facilitator for this scheduled session.",
    nextAction: "Review the brief now; acknowledgement opens when the prerequisite is accepted.",
    primaryAction: "Acknowledge task",
    lifecycle: [
      { label: "Acknowledgement", detail: "Waiting for prerequisite", state: "pending" },
      { label: "Progress", detail: "Not started", state: "pending" },
      { label: "Submission", detail: "Not submitted", state: "pending" },
      { label: "Review", detail: "Not reviewed", state: "pending" },
    ],
  },
  {
    id: "preview-access",
    view: "Blocked",
    title: "Verify demonstration access",
    projectLabel: "Customer demonstration",
    status: "Blocked",
    statusTone: "rust",
    timing: "Blocked since 10:20 JST",
    purpose: "Confirm that the demonstration account can reach the approved environment.",
    deliverable: "A pass/fail access result with the authorised evidence reference.",
    approvedBrief: "Verify access without copying credentials or restricted environment details into the result.",
    briefVersion: "Disclosure v1 - approved for assigned employees",
    approvedInputs: ["Demonstration access runbook"],
    effort: "30 minutes active effort",
    workWindow: "Today, 10:00-15:00 JST",
    deadline: "Today, 15:00 JST",
    reviewer: "Aiko Tanaka - Operations reviewer",
    dependencies: "Waiting for the approved access ticket. The private ticket reason is not disclosed here.",
    permissionBoundary: "Do not request or share raw credentials. Resume only after the approved ticket is available.",
    assignmentRationale: "You are assigned to validate the customer-safe demonstration path.",
    nextAction: "The blocker is recorded. Request clarification if the approved ticket does not arrive.",
    primaryAction: "Request clarification",
    lifecycle: [
      { label: "Acknowledgement", detail: "Acknowledged", state: "complete" },
      { label: "Progress", detail: "Blocked - input missing", state: "attention" },
      { label: "Submission", detail: "Not submitted", state: "pending" },
      { label: "Review", detail: "Not reviewed", state: "pending" },
    ],
  },
  {
    id: "preview-guide",
    view: "Submitted",
    title: "Prepare the reviewed operating guide",
    projectLabel: "Customer demonstration",
    status: "Submitted - review pending",
    statusTone: "moss",
    timing: "Submitted version 2 at 11:42 JST",
    purpose: "Give the demonstration team one accepted operating reference.",
    deliverable: "A reviewed operating guide that meets the approved acceptance criteria.",
    approvedBrief: "Prepare a clear operating guide from the approved customer-safe inputs. Acceptance belongs to the assigned reviewer and applies only to the submitted version.",
    briefVersion: "Disclosure v3 - approved for assigned employees",
    approvedInputs: ["Confirmed handoff inputs", "Customer-safe demonstration outline"],
    effort: "120 minutes active effort",
    workWindow: "Today, 09:30-14:30 JST",
    deadline: "Today, 15:00 JST",
    reviewer: "Aiko Tanaka - Operations reviewer",
    dependencies: "Approved handoff inputs received.",
    permissionBoundary: "Only the submitted version and approved inputs are visible to the reviewer.",
    assignmentRationale: "You own the guide deliverable; acceptance remains a separate reviewer decision.",
    nextAction: "Wait for the named reviewer. A later upload creates a new version and requires a new review.",
    primaryAction: "Upload new version",
    lifecycle: [
      { label: "Acknowledgement", detail: "Acknowledged", state: "complete" },
      { label: "Progress", detail: "Work completed", state: "complete" },
      { label: "Submission", detail: "Version 2 submitted", state: "complete" },
      { label: "Review", detail: "Pending with Aiko Tanaka", state: "current" },
    ],
  },
  {
    id: "preview-checklist",
    view: "Submitted",
    title: "Complete the access validation checklist",
    projectLabel: "Customer demonstration",
    status: "Revision requested",
    statusTone: "rust",
    timing: "Review of version 1 completed",
    purpose: "Record a reproducible, customer-safe access check.",
    deliverable: "A checklist with the missing rollback verification added.",
    approvedBrief: "Complete the approved checklist without exposing credentials or restricted environment details.",
    briefVersion: "Disclosure v1 - approved for assigned employees",
    approvedInputs: ["Demonstration access runbook", "Reviewer correction request"],
    effort: "20 minutes remaining estimate",
    workWindow: "Today, 13:00-16:00 JST",
    deadline: "Today, 16:00 JST",
    reviewer: "Aiko Tanaka - Operations reviewer",
    dependencies: "Access ticket is now available.",
    permissionBoundary: "Address only the authorised correction. The reviewed version remains preserved in history.",
    assignmentRationale: "You submitted version 1 and remain accountable for the requested correction.",
    nextAction: "Add the rollback verification and submit version 2 for a new exact-version review.",
    primaryAction: "Submit revision",
    lifecycle: [
      { label: "Acknowledgement", detail: "Acknowledged", state: "complete" },
      { label: "Progress", detail: "Revision in progress", state: "current" },
      { label: "Submission", detail: "Version 1 preserved", state: "complete" },
      { label: "Review", detail: "Revision requested", state: "attention" },
    ],
  },
] as const satisfies readonly PreviewTask[];

const viewDescriptions: Record<WorkView, string> = {
  Today: "Assigned work whose approved window includes today.",
  Upcoming: "Authorised work that is not ready to start yet.",
  Blocked: "Work paused for an input, decision or permission.",
  Submitted: "Exact submission versions awaiting review or revision.",
};

function TaskDetail({ task }: { task: PreviewTask }) {
  return (
    <section className="task-detail" aria-labelledby="task-detail-title">
      <div className="task-detail-heading">
        <div>
          <span className="eyebrow">Authorised task facts</span>
          <h2 id="task-detail-title">{task.title}</h2>
          <p>{task.purpose}</p>
        </div>
        <span className={`task-state ${task.statusTone}`}>{task.status}</span>
      </div>

      <ol className="task-lifecycle" aria-label="Task lifecycle">
        {task.lifecycle.map((stage, index) => (
          <li className={stage.state} key={stage.label}>
            <span className="lifecycle-index">{String(index + 1).padStart(2, "0")}</span>
            <strong>{stage.label}</strong>
            <span>{stage.detail}</span>
          </li>
        ))}
      </ol>

      <article className="approved-brief" aria-labelledby="approved-brief-heading">
        <div>
          <span className="eyebrow">Approved employee brief</span>
          <strong id="approved-brief-heading">Shareable context only</strong>
        </div>
        <span className="brief-version">{task.briefVersion}</span>
        <p>{task.approvedBrief}</p>
      </article>

      <div className="task-facts">
        <article><span className="eyebrow">Deliverable</span><p>{task.deliverable}</p></article>
        <article>
          <span className="eyebrow">Approved inputs</span>
          <ul>{task.approvedInputs.map((input) => <li key={input}>{input}</li>)}</ul>
        </article>
        <article>
          <span className="eyebrow">Timing</span>
          <dl>
            <div><dt>Expected effort</dt><dd>{task.effort}</dd></div>
            <div><dt>Work window</dt><dd>{task.workWindow}</dd></div>
            <div><dt>Deadline</dt><dd>{task.deadline}</dd></div>
          </dl>
        </article>
        <article>
          <span className="eyebrow">Review and dependencies</span>
          <dl>
            <div><dt>Reviewer</dt><dd>{task.reviewer}</dd></div>
            <div><dt>Dependencies</dt><dd>{task.dependencies}</dd></div>
          </dl>
        </article>
      </div>

      <div className="task-boundaries">
        <article><span className="eyebrow">Permission boundary</span><p>{task.permissionBoundary}</p></article>
        <article><span className="eyebrow">Why this assignment</span><p>{task.assignmentRationale}</p></article>
      </div>

      <footer className="task-actions">
        <div><span className="eyebrow">Next action</span><strong>{task.nextAction}</strong></div>
        <button className="primary-action" disabled>{task.primaryAction}</button>
        <button className="secondary-action" disabled>Flag estimate, skill, input or availability</button>
      </footer>
    </section>
  );
}

export function EmployeeWorkspace() {
  const [activeView, setActiveView] = useState<WorkView>("Today");
  const tasks = useMemo(() => previewTasks.filter((task) => task.view === activeView), [activeView]);
  const [selectedTaskId, setSelectedTaskId] = useState<string>(previewTasks[0].id);
  const selectedTask = tasks.find((task) => task.id === selectedTaskId) ?? tasks[0] ?? previewTasks[0];

  function selectView(view: WorkView) {
    const firstTask = previewTasks.find((task) => task.view === view);
    setActiveView(view);
    if (firstTask) setSelectedTaskId(firstTask.id);
  }

  return (
    <>
      <section className="employee-intro" aria-labelledby="employee-work-heading">
        <div>
          <div className="proposal-kicker">
            <span className="section-number">Employee workspace / repository preview</span>
            <span className="preview-label">Sample data - read only</span>
          </div>
          <h2 id="employee-work-heading">Your work, with the context you are allowed to use.</h2>
          <p>This surface separates approved employee context from restricted planning material. It does not load live tasks or change shared state until an authenticated desktop session is connected.</p>
        </div>
        <dl className="work-summary" aria-label="Preview task summary">
          {workViews.map((view) => (
            <div key={view}><dt>{view}</dt><dd>{previewTasks.filter((task) => task.view === view).length}</dd></div>
          ))}
        </dl>
      </section>

      <div className="employee-layout">
        <aside className="task-inbox" aria-label="My task views">
          <div className="work-view-tabs" role="tablist" aria-label="Task status views">
            {workViews.map((view) => (
              <button className={activeView === view ? "active" : ""} key={view} onClick={() => selectView(view)} role="tab" aria-label={`${view} tasks (${previewTasks.filter((task) => task.view === view).length})`} aria-selected={activeView === view}>
                <span>{view}</span><strong>{previewTasks.filter((task) => task.view === view).length}</strong>
              </button>
            ))}
          </div>
          <p className="view-description">{viewDescriptions[activeView]}</p>
          <div className="task-list">
            {tasks.map((task) => (
              <button className={`task-list-item ${selectedTask.id === task.id ? "active" : ""}`} key={task.id} onClick={() => setSelectedTaskId(task.id)} aria-label={task.title} aria-pressed={selectedTask.id === task.id}>
                <span className="task-list-kicker">{task.projectLabel}</span>
                <strong>{task.title}</strong>
                <span className={`task-list-status ${task.statusTone}`}>{task.status}</span>
                <small>{task.timing}</small>
              </button>
            ))}
          </div>
          <p className="preview-boundary">Illustrative records only. Live views must be permission-filtered by the API for the authenticated employee.</p>
        </aside>

        <TaskDetail task={selectedTask} />
      </div>
    </>
  );
}
