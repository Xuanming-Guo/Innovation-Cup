import { useEffect, useMemo, useState } from "react";

import {
  startAuthorisedSession,
  type AuthorisedSessionState,
} from "./authorised-session";
import { EmployeeWorkspace } from "./employee-workspace";
import { PlanReviewWorkspace } from "./plan-review";
import { getPublicRuntimeConfig } from "./runtime-config";
import { getServiceStatus, type ServiceStatus } from "./service-status";

const initialStatus: ServiceStatus = { state: "checking", detail: "Checking configured API origin" };
const initialSession: AuthorisedSessionState = { status: "unconfigured" };
type WorkspaceSurface = "manager" | "employee";

export function App() {
  const config = useMemo(() => getPublicRuntimeConfig(), []);
  const [serviceStatus, setServiceStatus] = useState<ServiceStatus>(initialStatus);
  const [authorisedSession, setAuthorisedSession] = useState<AuthorisedSessionState>(initialSession);
  const [activeSurface, setActiveSurface] = useState<WorkspaceSurface>("manager");

  useEffect(() => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 4_000);
    void getServiceStatus(config, controller.signal)
      .then(setServiceStatus)
      .catch(() => setServiceStatus({ state: "unreachable", detail: "API health check timed out" }))
      .finally(() => window.clearTimeout(timeout));
    return () => { window.clearTimeout(timeout); controller.abort(); };
  }, [config]);

  useEffect(() => startAuthorisedSession(config, setAuthorisedSession), [config]);

  return (
    <div className="app-shell">
      <aside className="side-rail" aria-label="Primary navigation">
        <div className="brand"><img src="/brand-mark.svg" alt="" width="28" height="28" /><span>{config.productName}</span></div>
        <nav className="navigation">
          <button className={`nav-item ${activeSurface === "manager" ? "active" : ""}`} aria-current={activeSurface === "manager" ? "page" : undefined} aria-label="Manager review" onClick={() => setActiveSurface("manager")}>
            <span className="nav-index">01</span>Manager review
          </button>
          <button className={`nav-item ${activeSurface === "employee" ? "active" : ""}`} aria-current={activeSurface === "employee" ? "page" : undefined} aria-label="My work" onClick={() => setActiveSurface("employee")}>
            <span className="nav-index">02</span>My work
          </button>
          <span className="nav-item disabled" aria-disabled="true"><span className="nav-index">03</span>Connections</span>
        </nav>
        <div className="side-note">
          <span className="eyebrow">{activeSurface === "manager" ? "Review boundary" : "Visibility boundary"}</span>
          <strong>{activeSurface === "manager" ? "Human-led commitment" : "Approved context only"}</strong>
          <p>{activeSurface === "manager" ? "AI proposes. Z3 checks. Authorized people decide. The database commits atomically." : "Employees see their authorised task facts and approved brief, never the full private planning context."}</p>
        </div>
      </aside>
      <main className="workspace">
        <header className="topbar">
          <div><span className="eyebrow">Coordination Engine - {activeSurface === "manager" ? "Manager workspace" : "Employee workspace"}</span><h1>{activeSurface === "manager" ? "Plan review" : "My work"}</h1></div>
          <div className="topbar-status">
            {config.supabaseConfigured && (
              <span className="session-chip" aria-live="polite">
                {authorisedSession.status === "connected"
                  ? `${authorisedSession.unreadNotifications} unread`
                  : `Session ${authorisedSession.status.replace("_", " ")}`}
              </span>
            )}
            <span className={`service-chip ${serviceStatus.state}`} title={serviceStatus.detail}><span className="status-dot" aria-hidden="true" />API {serviceStatus.state}</span>
          </div>
        </header>
        {activeSurface === "manager" ? <PlanReviewWorkspace /> : <EmployeeWorkspace />}
      </main>
    </div>
  );
}
