import { useEffect, useMemo, useRef, useState } from "react";

import {
  startAuthorisedSession,
  type AuthorisedSessionController,
  type AuthorisedSessionState,
} from "./authorised-session";
import { CompanyConnections } from "./company-connections";
import { EmployeeWorkspace } from "./employee-workspace";
import { PlanReviewWorkspace } from "./plan-review";
import { getPublicRuntimeConfig } from "./runtime-config";
import { getServiceStatus, type ServiceStatus } from "./service-status";

const initialStatus: ServiceStatus = { state: "checking", detail: "Checking configured API origin" };
const initialSession: AuthorisedSessionState = { status: "unconfigured" };
type WorkspaceSurface = "manager" | "employee" | "connections";

export function App() {
  const config = useMemo(() => getPublicRuntimeConfig(), []);
  const [serviceStatus, setServiceStatus] = useState<ServiceStatus>(initialStatus);
  const [authorisedSession, setAuthorisedSession] = useState<AuthorisedSessionState>(initialSession);
  const [activeSurface, setActiveSurface] = useState<WorkspaceSurface>("manager");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState<string | null>(null);
  const sessionController = useRef<AuthorisedSessionController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 4_000);
    void getServiceStatus(config, controller.signal)
      .then(setServiceStatus)
      .catch(() => setServiceStatus({ state: "unreachable", detail: "API health check timed out" }))
      .finally(() => window.clearTimeout(timeout));
    return () => { window.clearTimeout(timeout); controller.abort(); };
  }, [config]);

  useEffect(() => {
    const controller = startAuthorisedSession(config, setAuthorisedSession);
    sessionController.current = controller;
    return () => {
      sessionController.current = null;
      controller.stop();
    };
  }, [config]);

  async function signIn() {
    setAuthError(null);
    try {
      await sessionController.current?.signIn(email.trim(), password);
      setPassword("");
    } catch (value) {
      setAuthError(value instanceof Error ? value.message : "Sign in failed");
    }
  }

  async function signOut() {
    setAuthError(null);
    try {
      await sessionController.current?.signOut();
    } catch (value) {
      setAuthError(value instanceof Error ? value.message : "Sign out failed");
    }
  }

  const api = authorisedSession.status === "connected" ? authorisedSession.api : undefined;
  const workspaceKey = authorisedSession.status === "connected"
    ? `${authorisedSession.userId}:${authorisedSession.api.companyId}`
    : "disconnected";

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
          <button className={`nav-item ${activeSurface === "connections" ? "active" : ""}`} aria-current={activeSurface === "connections" ? "page" : undefined} aria-label="Connections" onClick={() => setActiveSurface("connections")}>
            <span className="nav-index">03</span>Connections
          </button>
        </nav>
        <div className="side-note">
          <span className="eyebrow">{activeSurface === "manager" ? "Review boundary" : activeSurface === "employee" ? "Visibility boundary" : "Credential boundary"}</span>
          <strong>{activeSurface === "manager" ? "Human-led commitment" : activeSurface === "employee" ? "Approved context only" : "Company-managed BYOK"}</strong>
          <p>{activeSurface === "manager" ? "AI proposes. Z3 checks. Authorized people decide. The database commits atomically." : activeSurface === "employee" ? "Employees see their authorised task facts and approved brief, never the full private planning context." : "The backend uses the company credential. It is never shipped to an employee device or returned after configuration."}</p>
        </div>
      </aside>
      <main className="workspace">
        <header className="topbar">
          <div><span className="eyebrow">Coordination Engine - {activeSurface === "manager" ? "Manager workspace" : activeSurface === "employee" ? "Employee workspace" : "Company settings"}</span><h1>{activeSurface === "manager" ? "Plan review" : activeSurface === "employee" ? "My work" : "Connections"}</h1></div>
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
        {authorisedSession.status === "signed_out" && (
          <section className="session-panel" aria-label="Sign in">
            <div><span className="eyebrow">Supabase Auth</span><strong>Sign in to the connected workspace</strong></div>
            <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="Synthetic demo email" autoComplete="username" />
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Password" autoComplete="current-password" />
            <button className="primary-action" disabled={!email.trim() || !password} onClick={() => void signIn()}>Sign in</button>
          </section>
        )}
        {authorisedSession.status === "connected" && (
          <section className="connected-banner">
            <span>Connected as {authorisedSession.administrativeRole.replaceAll("_", " ")}</span>
            <button className="text-action" onClick={() => void signOut()}>Sign out</button>
          </section>
        )}
        {authError && <p className="inline-error" role="alert">{authError}</p>}
        {activeSurface === "manager" && (
          <PlanReviewWorkspace key={`manager:${workspaceKey}`} api={api} />
        )}
        {activeSurface === "employee" && (
          <EmployeeWorkspace key={`employee:${workspaceKey}`} api={api} />
        )}
        {activeSurface === "connections" && (
          <CompanyConnections
            key={`connections:${workspaceKey}`}
            api={api}
            canManage={authorisedSession.status === "connected" && authorisedSession.administrativeRole === "company_admin"}
          />
        )}
      </main>
    </div>
  );
}
