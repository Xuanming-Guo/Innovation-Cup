import { useCallback, useEffect, useMemo, useState } from "react";

import {
  getEmployeeTasks,
  submitTask,
  transitionTask,
  type AuthorisedApiContext,
  type EmployeeTask,
} from "./api-client";

type WorkView = "today" | "upcoming" | "blocked" | "submitted";

interface EmployeeWorkspaceProps {
  api?: AuthorisedApiContext;
}

const views: Array<{ value: WorkView; label: string }> = [
  { value: "today", label: "Today" },
  { value: "upcoming", label: "Upcoming" },
  { value: "blocked", label: "Blocked" },
  { value: "submitted", label: "Submitted" },
];

function displayTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function briefText(task: EmployeeTask): string {
  const content = task.approved_brief?.content;
  if (!content) return "No employee brief has been disclosed for this task.";
  if (typeof content.summary === "string") return content.summary;
  return "The exact approved brief is available for this task.";
}

export function EmployeeWorkspace({ api }: EmployeeWorkspaceProps) {
  const [activeView, setActiveView] = useState<WorkView>("today");
  const [tasks, setTasks] = useState<EmployeeTask[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [submission, setSubmission] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!api) return;
    const value = await getEmployeeTasks(api, activeView);
    setTasks(value);
    setSelectedTaskId((current) =>
      value.some((task) => task.task_id === current) ? current : value[0]?.task_id ?? null,
    );
  }, [activeView, api]);

  useEffect(() => {
    if (!api) return;
    let active = true;
    const initialTimer = window.setTimeout(() => {
      void refresh().catch((value: unknown) => {
        if (active) setError(value instanceof Error ? value.message : "Task refresh failed");
      });
    }, 0);
    const timer = window.setInterval(() => {
      if (active) void refresh();
    }, 5_000);
    return () => {
      active = false;
      window.clearTimeout(initialTimer);
      window.clearInterval(timer);
    };
  }, [api, refresh]);

  const selected = useMemo(
    () => tasks.find((task) => task.task_id === selectedTaskId) ?? tasks[0] ?? null,
    [selectedTaskId, tasks],
  );

  async function runTransition(command: "acknowledge" | "start" | "unblock") {
    if (!api || !selected) return;
    setBusy(true);
    setError(null);
    try {
      await transitionTask(api, selected, command);
      await refresh();
    } catch (value) {
      setError(value instanceof Error ? value.message : "Task update failed");
    } finally {
      setBusy(false);
    }
  }

  async function sendSubmission() {
    if (!api || !selected || !submission.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await submitTask(api, selected, submission.trim());
      setSubmission("");
      setActiveView("submitted");
    } catch (value) {
      setError(value instanceof Error ? value.message : "Submission failed");
    } finally {
      setBusy(false);
    }
  }

  if (!api) {
    return (
      <section className="empty-workspace">
        <span className="eyebrow">Employee visibility boundary</span>
        <h2>Sign in to load only your authorised work.</h2>
        <p>Tasks, briefs and submissions are fetched through FastAPI after current membership and task-scoped access are rechecked.</p>
      </section>
    );
  }

  return (
    <>
      <section className="employee-intro" aria-labelledby="employee-work-heading">
        <div>
          <span className="eyebrow">Connected employee workspace</span>
          <h2 id="employee-work-heading">Your work, with only approved context.</h2>
          <p>Raw planning evidence, other-team context and solver diagnostics are intentionally absent.</p>
        </div>
      </section>
      <div className="employee-layout">
        <aside className="task-inbox" aria-label="My task views">
          <div className="work-view-tabs" role="tablist" aria-label="Task status views">
            {views.map((view) => (
              <button className={activeView === view.value ? "active" : ""} key={view.value} onClick={() => setActiveView(view.value)} role="tab" aria-selected={activeView === view.value}>
                <span>{view.label}</span>
              </button>
            ))}
          </div>
          <div className="task-list">
            {tasks.map((task) => (
              <button className={`task-list-item ${selected?.task_id === task.task_id ? "active" : ""}`} key={task.task_id} onClick={() => setSelectedTaskId(task.task_id)} aria-pressed={selected?.task_id === task.task_id}>
                <span className="task-list-kicker">{task.task_key}</span>
                <strong>{task.title}</strong>
                <span className="task-list-status teal">{task.status.replaceAll("_", " ")}</span>
                <small>{displayTime(task.start_at)}</small>
              </button>
            ))}
            {tasks.length === 0 && <p className="view-description">No authorised tasks in this view.</p>}
          </div>
        </aside>

        {selected && (
          <section className="task-detail" aria-labelledby="task-detail-title">
            <div className="task-detail-heading">
              <div><span className="eyebrow">Authorised task facts</span><h2 id="task-detail-title">{selected.title}</h2></div>
              <span className="task-state teal">{selected.status.replaceAll("_", " ")}</span>
            </div>
            <article className="approved-brief">
              <div><span className="eyebrow">Approved employee brief</span><strong>Disclosure version {selected.approved_brief?.version ?? "not approved"}</strong></div>
              <p>{briefText(selected)}</p>
            </article>
            <div className="task-facts">
              <article><span className="eyebrow">Scheduled window</span><p>{displayTime(selected.start_at)} — {displayTime(selected.finish_at)}</p></article>
              <article><span className="eyebrow">Review</span><p>{selected.reviewer_name ?? "Review policy pending"}</p></article>
            </div>
            {(selected.status === "in_progress" || selected.status === "revision_requested") && (
              <label className="submission-editor">
                <span className="eyebrow">Exact submission version</span>
                <textarea rows={6} value={submission} onChange={(event) => setSubmission(event.target.value)} placeholder="Describe the completed work and the evidence the reviewer should inspect." />
              </label>
            )}
            <footer className="task-actions">
              {selected.status === "assigned" && <button className="primary-action" disabled={busy} onClick={() => void runTransition("acknowledge")}>Acknowledge task</button>}
              {selected.status === "acknowledged" && <button className="primary-action" disabled={busy} onClick={() => void runTransition("start")}>Start work</button>}
              {selected.status === "blocked" && <button className="primary-action" disabled={busy} onClick={() => void runTransition("unblock")}>Resume work</button>}
              {(selected.status === "in_progress" || selected.status === "revision_requested") && <button className="primary-action" disabled={busy || !submission.trim()} onClick={() => void sendSubmission()}>Submit exact version</button>}
              {selected.status === "submitted" && <strong>Waiting for the assigned reviewer.</strong>}
              {selected.status === "accepted" && <strong>Accepted. This version is preserved.</strong>}
            </footer>
            {error && <p className="inline-error" role="alert">{error}</p>}
          </section>
        )}
      </div>
    </>
  );
}
