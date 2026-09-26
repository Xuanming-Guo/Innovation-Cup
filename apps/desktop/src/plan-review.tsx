import { useState } from "react";

const tabs = ["Overview", "Evidence", "Assumptions", "Schedule", "Diagnostics"] as const;
type ReviewTab = (typeof tabs)[number];

const tasks = [
  { key: "INTAKE", title: "Confirm operating constraints", owner: "Operations lead", window: "Mon 09:00–10:00", offset: 2, width: 19, tone: "teal" },
  { key: "DRAFT", title: "Prepare reviewed operating guide", owner: "Content owner", window: "Mon 10:15–Tue 12:00", offset: 18, width: 44, tone: "rust" },
  { key: "REVIEW", title: "Independent acceptance review", owner: "Assigned reviewer", window: "Tue 13:00–14:00", offset: 65, width: 20, tone: "moss" },
] as const;

const evidence = [
  ["task.definition", "3 validated tasks", "Authoritative source"],
  ["resource.capacity", "Working windows and daily budget", "Confirmed profile"],
  ["acceptance.review", "Independent reviewer required", "Manager authority"],
] as const;

function Schedule() {
  return (
    <div className="schedule" aria-label="Proposed schedule">
      <div className="schedule-scale" aria-hidden="true">
        <span>MON 09</span><span>MON 13</span><span>TUE 09</span><span>TUE 13</span>
      </div>
      {tasks.map((task) => (
        <article className="schedule-row" key={task.key}>
          <div className="task-label">
            <code>{task.key}</code><strong>{task.title}</strong>
            <span>{task.owner} · {task.window}</span>
          </div>
          <div className="timeline-track" aria-label={`${task.title}: ${task.window}`}>
            <span className={`timeline-block ${task.tone}`} style={{ marginLeft: `${task.offset}%`, width: `${task.width}%` }} />
          </div>
        </article>
      ))}
    </div>
  );
}

function TabContent({ tab }: { tab: ReviewTab }) {
  if (tab === "Evidence") {
    return (
      <div className="evidence-list" aria-label="Proposal evidence">
        {evidence.map(([key, value, source]) => (
          <article key={key}><code>{key}</code><strong>{value}</strong><span>{source}</span></article>
        ))}
      </div>
    );
  }
  if (tab === "Assumptions") {
    return (
      <div className="review-note">
        <span className="eyebrow">Confirmed assumptions</span>
        <p>The proposal uses only admitted constraints. Human authority references remain review evidence; they are never converted into permissions by Gemini or Z3.</p>
      </div>
    );
  }
  if (tab === "Diagnostics") {
    return (
      <dl className="diagnostic-grid">
        <div><dt>Application result</dt><dd>Feasible</dd></div>
        <div><dt>Independent validation</dt><dd>Passed</dd></div>
        <div><dt>Solver scope</dt><dd>Authorized repair</dd></div>
        <div><dt>Committed state</dt><dd>None</dd></div>
      </dl>
    );
  }
  if (tab === "Schedule") return <Schedule />;
  return (
    <div className="overview-copy">
      <p>Three tasks fit inside the bounded planning horizon. The acceptance review remains separate from execution, and no deadline or cross-team authority is implied.</p>
      <div className="metric-strip">
        <div><strong>3</strong><span>tasks</span></div>
        <div><strong>2d</strong><span>horizon</span></div>
        <div><strong>1</strong><span>approval pending</span></div>
      </div>
    </div>
  );
}

export function PlanReviewWorkspace() {
  const [activeTab, setActiveTab] = useState<ReviewTab>("Overview");

  return (
    <>
      <section className="review-hero" aria-labelledby="review-title">
        <div>
          <div className="proposal-kicker">
            <span className="section-number">Proposal / design preview</span>
            <span className="proposal-status">Draft · not applied</span>
          </div>
          <h2 id="review-title">Prepare a reviewed operating guide.</h2>
          <p>Review the exact schedule, its evidence, assumptions and authority requirements before any shared work state changes.</p>
        </div>
        <aside className="binding-card" aria-label="Proposal binding">
          <span className="eyebrow">Exact binding</span>
          <dl>
            <div><dt>Proposal</dt><dd><code>48f6…a12c</code></dd></div>
            <div><dt>Base revision</dt><dd>0</dd></div>
            <div><dt>Policy</dt><dd>planning-v1</dd></div>
          </dl>
        </aside>
      </section>

      <div className="review-layout">
        <section className="review-main">
          <div className="review-tabs" role="tablist" aria-label="Plan review sections">
            {tabs.map((tab) => (
              <button className={activeTab === tab ? "active" : ""} key={tab} role="tab" aria-selected={activeTab === tab} onClick={() => setActiveTab(tab)}>{tab}</button>
            ))}
          </div>
          <div className="tab-panel" role="tabpanel"><TabContent tab={activeTab} /></div>
          {activeTab !== "Schedule" ? <Schedule /> : null}
        </section>

        <aside className="approval-panel" aria-labelledby="approval-heading">
          <span className="eyebrow">Authority</span>
          <h3 id="approval-heading">Approval required</h3>
          <div className="requirement-card">
            <span className="requirement-icon">01</span>
            <div><strong>Plan commitment</strong><p>Company manager · exact proposal only</p></div>
            <span className="pending-label">Pending</span>
          </div>
          <div className="disclosure-note">
            <strong>Employee brief is separate</strong>
            <p>No brief or audience disclosure is authorized by this planning approval.</p>
          </div>
          <button className="primary-action" disabled>Connect manager session to approve</button>
          <button className="secondary-action" disabled>Commit approved plan</button>
          <small>This repository preview cannot mutate shared state. Authenticated API operations recheck every digest, source version and authority at commit time.</small>
        </aside>
      </div>
    </>
  );
}
