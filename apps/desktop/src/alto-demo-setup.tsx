import { useMemo, useState } from "react";
import { altoRequest, type AltoApiContext, type DemoData, type DemoRun, type WorkspaceBootstrap } from "./alto-api";
import { ErrorNotice, Loading, PageHeading } from "./alto-ui";
import { humanize, navigate, useCommand, useResource } from "./alto-state";
import "./alto-demo-setup.css";

export function DemoSetup({ api, workspace, onSelectRun, locked = false }: {
  api: AltoApiContext;
  workspace: WorkspaceBootstrap | null;
  onSelectRun: (run?: string, actor?: string, actorKey?: string) => void;
  locked?: boolean;
}) {
  // Setup never reuses an expired actor session to list the visitor's own runs.
  // Selecting an actor still requires an explicit, server-authorised command.
  const setupApi = useMemo(() => ({ ...api, demoRunId: undefined, demoActorSessionId: undefined }), [api]);
  const resource = useResource<DemoData>(setupApi, "/demo/runs");
  const command = useCommand();
  const [role, setRole] = useState<"manager" | "employee">(workspace?.viewer.role ?? "manager");
  const [selectedRun, setSelectedRun] = useState(api.demoRunId ?? "");
  const [mode, setMode] = useState("live");
  const [personId, setPersonId] = useState("");
  const activeRuns = resource.data?.runs.filter((run) => run.status === "active") ?? [];
  const people = resource.data?.actors.filter((person) => person.role === role) ?? [];
  const suggestedPerson = people.find((person) => person.display_name.startsWith(role === "manager" ? "Maya" : "Iris")) ?? people[0];
  const person = people.find((value) => value.id === personId) ?? suggestedPerson;
  const run = activeRuns.find((value) => value.id === selectedRun);
  const lockedPeople = resource.data?.actors ?? [];
  const lockedPerson = lockedPeople.find((value) => value.id === personId)
    ?? lockedPeople.find((value) => value.id === workspace?.viewer.employee_id)
    ?? lockedPeople.find((value) => value.synthetic_key === "maya")
    ?? lockedPeople[0];

  async function continueAsRole() {
    if (!person) return;
    let runId = selectedRun || undefined;
    if (!runId) {
      const created = await altoRequest<DemoRun>(setupApi, "/demo/runs", { method: "POST", body: { mode } });
      runId = created.id;
      // Persist the created run before the next command, so a failed actor step
      // can be retried without creating another run or losing the user's choice.
      setSelectedRun(runId);
      onSelectRun(runId);
      resource.refresh();
    }
    const selected = await altoRequest<{ actor_session_id: string }>(setupApi,
      `/demo/runs/${runId}/actor-sessions`, { method: "POST", body: { employee_id: person.id } });
    onSelectRun(runId, selected.actor_session_id);
    navigate("/home");
  }

  async function switchPerson() {
    if (!lockedPerson || !api.demoRunId) return;
    const selected = await altoRequest<{ actor_session_id: string }>(setupApi,
      `/demo/runs/${api.demoRunId}/actor-sessions`, {
        method: "POST",
        body: { employee_id: lockedPerson.id },
      });
    onSelectRun(api.demoRunId, selected.actor_session_id, lockedPerson.synthetic_key);
    navigate("/home");
  }

  if (locked) return <div className="alto-demo-setup">
    <PageHeading eyebrow="Hackathon demo" title="Switch demo person"
      subtitle="Choose whose view you want to explore. Your isolated workspace stays the same." />
    {resource.loading && <Loading label="Loading demo people…" />}
    <ErrorNotice error={resource.error ?? command.error} retry={resource.refresh} />
    {!resource.loading && lockedPeople.length > 0 && <label className="alto-field">Demo person
      <select value={lockedPerson?.id ?? ""} onChange={(event) => setPersonId(event.target.value)}>
        <optgroup label="Managers">
          {lockedPeople.filter((value) => value.role === "manager").map((value) =>
            <option key={value.id} value={value.id}>{value.display_name} · {value.job_title}</option>)}
        </optgroup>
        <optgroup label="Team members">
          {lockedPeople.filter((value) => value.role !== "manager").map((value) =>
            <option key={value.id} value={value.id}>{value.display_name} · {value.job_title}</option>)}
        </optgroup>
      </select>
    </label>}
    <div className="alto-button-row">
      <button className="alto-primary" disabled={command.busy || !lockedPerson || !api.demoRunId}
        onClick={() => void command.run(switchPerson)}>{command.busy ? "Switching…" : "Use this person"}</button>
      <button className="alto-secondary" onClick={() => navigate("/home")}>Cancel</button>
    </div>
  </div>;

  return <div className="alto-demo-setup">
    <PageHeading eyebrow="Synthetic company · Demo setup" title="How would you like to use ALTO?"
      subtitle="Choose a role to explore. You can switch here at any time without starting over." />
    <p className="alto-info-banner">This changes your role only inside this isolated demo. Your signed-in account stays the same; real company permissions are not changed.</p>
    <div className="alto-role-options" aria-label="Choose your demo role">
      {(["manager", "employee"] as const).map((value) => <button key={value} type="button"
        className={`alto-role-option ${role === value ? "selected" : ""}`} aria-pressed={role === value}
        onClick={() => { setRole(value); setPersonId(""); }}>
        <strong>Explore as {value}</strong>
        <span>{value === "manager" ? "Describe a goal, review plans and coordinate your team." : "See your assigned work, submit results and keep feedback private."}</span>
      </button>)}
    </div>
    {resource.loading && <Loading label="Loading your demo choices…" />}
    <ErrorNotice error={resource.error ?? command.error} retry={resource.refresh} />
    {person && <p>You’ll explore as <strong>{person.display_name}</strong>, {person.job_title}. Your actions remain labelled as demo activity.</p>}
    {!resource.loading && resource.data && !person && <p>No permitted {role} profile is available. Refresh the choices or ask the demo operator to check scenario setup.</p>}
    {activeRuns.length > 0 && <label className="alto-field">Demo workspace
      <select value={selectedRun} onChange={(event) => setSelectedRun(event.target.value)}>
        <option value="">Create a new isolated workspace</option>
        {selectedRun && !run && <option value={selectedRun}>Selected workspace · refreshing details</option>}
        {activeRuns.map((value) => <option key={value.id} value={value.id}>{value.name} · {humanize(value.mode)} · {value.id.slice(0, 8)}</option>)}
      </select>
    </label>}
    {!selectedRun && <label className="alto-field">Planning mode
      <select value={mode} onChange={(event) => setMode(event.target.value)}>
        <option value="live">Live AI — uses your Google credential</option>
        <option value="authored_replay">Guided replay — no live AI planning</option>
      </select>
      <small>{mode === "live" ? "Create the workspace first, then connect AI in Settings. Live requests may incur Google charges; choosing a role makes no AI call." : "A labelled, pre-authored example for exploring the workflow without live model planning."}</small>
    </label>}
    <details className="alto-demo-advanced"><summary>Choose a different demo teammate</summary>
      <label className="alto-field">{role === "manager" ? "Manager" : "Employee"} profile
        <select value={person?.id ?? ""} onChange={(event) => setPersonId(event.target.value)}>
          {people.map((value) => <option key={value.id} value={value.id}>{value.display_name} · {value.job_title}</option>)}
        </select>
      </label>
    </details>
    <div className="alto-button-row">
      <button className="alto-primary" disabled={command.busy || !person || (!selectedRun && !resource.data?.can_create)}
        onClick={() => void command.run(continueAsRole)}>{command.busy ? "Opening your workspace…" : `Continue as ${role}`}</button>
      {api.demoRunId && <button className="alto-secondary" disabled={command.busy}
        onClick={() => { onSelectRun(); navigate("/home"); }}>Return to my signed-in identity</button>}
    </div>
    <details className="alto-demo-advanced"><summary>Advanced demo controls</summary>
      <p>Clock, fork, archive and reset controls are for exploring scenarios. They are not needed to plan or do your work.</p>
      <button className="alto-secondary" onClick={() => navigate("/simulation")}>Open advanced controls</button>
    </details>
  </div>;
}
