import { useEffect, useMemo, useRef, useState } from "react";

import {
  startAuthorisedSession,
  type AuthorisedSessionController,
  type AuthorisedSessionState,
} from "./authorised-session";
import { CompanyConnections } from "./company-connections";
import { DeploymentSettings } from "./deployment-settings";
import { EmployeeWorkspace } from "./employee-workspace";
import { PlanReviewWorkspace } from "./plan-review";
import {
  clearPublicRuntimeConfig,
  getPublicRuntimeConfig,
  loadPublicRuntimeConfig,
  savePublicRuntimeConfig,
  type PublicRuntimeConfigInput,
} from "./runtime-config";
import { getServiceStatus, type ServiceStatus } from "./service-status";

const initialStatus: ServiceStatus = { state: "checking", detail: "Checking configured API origin" };
const initialSession: AuthorisedSessionState = { status: "unconfigured" };
type WorkspaceSurface = "manager" | "employee" | "connections" | "deployment";

export function App() {
  const environmentConfig = useMemo(() => getPublicRuntimeConfig(), []);
  const [config, setConfig] = useState(() => loadPublicRuntimeConfig());
  const [serviceStatus, setServiceStatus] = useState<ServiceStatus>(initialStatus);
  const [authorisedSession, setAuthorisedSession] = useState<AuthorisedSessionState>(initialSession);
  const [activeSurface, setActiveSurface] = useState<WorkspaceSurface>(() =>
    config.supabaseConfigured && config.defaultCompanyId ? "manager" : "deployment",
  );
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState<string | null>(null);
  const sessionController = useRef<AuthorisedSessionController | null>(null);

  useEffect(() => {
    const activeOrigin = authorisedSession.status === "connected"
      ? authorisedSession.api.apiOrigin
      : config.apiMode === "static"
        ? config.apiOrigin
        : null;
    if (activeOrigin === null) return;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 4_000);
    void getServiceStatus({ ...config, apiOrigin: activeOrigin }, controller.signal)
      .then(setServiceStatus)
      .catch(() => setServiceStatus({ state: "unreachable", detail: "API health check timed out" }))
      .finally(() => window.clearTimeout(timeout));
    return () => { window.clearTimeout(timeout); controller.abort(); };
  }, [authorisedSession, config]);

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

  function saveDeployment(input: PublicRuntimeConfigInput) {
    const nextConfig = savePublicRuntimeConfig(input, config.productName);
    setServiceStatus(initialStatus);
    setAuthorisedSession(initialSession);
    setConfig(nextConfig);
    setActiveSurface("manager");
  }

  function resetDeployment() {
    clearPublicRuntimeConfig();
    setServiceStatus(initialStatus);
    setAuthorisedSession(initialSession);
    setConfig(environmentConfig);
    if (!environmentConfig.supabaseConfigured || !environmentConfig.defaultCompanyId) {
      setActiveSurface("deployment");
    }
  }

  const api = authorisedSession.status === "connected" ? authorisedSession.api : undefined;
  const workspaceKey = authorisedSession.status === "connected"
    ? `${authorisedSession.userId}:${authorisedSession.api.companyId}`
    : "disconnected";
  const displayedServiceStatus = config.apiMode === "supabase-discovery"
    && authorisedSession.status !== "connected"
    ? {
        state: authorisedSession.status === "unreachable" ? "unreachable" : "checking",
        detail: authorisedSession.status === "unreachable"
          ? authorisedSession.detail
          : "Sign in to discover the active host computer",
      } satisfies ServiceStatus
    : serviceStatus;

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
          <button className={`nav-item ${activeSurface === "deployment" ? "active" : ""}`} aria-current={activeSurface === "deployment" ? "page" : undefined} aria-label="Deployment" onClick={() => setActiveSurface("deployment")}>
            <span className="nav-index">04</span>Deployment
          </button>
        </nav>
        <div className="side-note">
          <span className="eyebrow">{activeSurface === "manager" ? "Review boundary" : activeSurface === "employee" ? "Visibility boundary" : activeSurface === "connections" ? "Credential boundary" : "Deployment boundary"}</span>
          <strong>{activeSurface === "manager" ? "Human-led commitment" : activeSurface === "employee" ? "Approved context only" : activeSurface === "connections" ? "Company-managed BYOK" : "Public values only"}</strong>
          <p>{activeSurface === "manager" ? "AI proposes. Z3 checks. Authorized people decide. The database commits atomically." : activeSurface === "employee" ? "Employees see their authorised task facts and approved brief, never the full private planning context." : activeSurface === "connections" ? "The backend uses the company credential. It is never shipped to an employee device or returned after configuration." : "This device stores endpoint identifiers and a publishable client key. Privileged credentials remain on the backend."}</p>
        </div>
      </aside>
      <main className="workspace">
        <header className="topbar">
          <div><span className="eyebrow">Coordination Engine - {activeSurface === "manager" ? "Manager workspace" : activeSurface === "employee" ? "Employee workspace" : activeSurface === "connections" ? "Company settings" : "Installation settings"}</span><h1>{activeSurface === "manager" ? "Plan review" : activeSurface === "employee" ? "My work" : activeSurface === "connections" ? "Connections" : "Deployment setup"}</h1></div>
          <div className="topbar-status">
            {config.supabaseConfigured && (
              <span className="session-chip" aria-live="polite">
                {authorisedSession.status === "connected"
                  ? `${authorisedSession.unreadNotifications} unread`
                  : `Session ${authorisedSession.status.replace("_", " ")}`}
              </span>
            )}
            <span className={`service-chip ${displayedServiceStatus.state}`} title={displayedServiceStatus.detail}><span className="status-dot" aria-hidden="true" />API {displayedServiceStatus.state}</span>
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
        {authorisedSession.status === "unreachable" && (
          <section className="connected-banner">
            <span>{authorisedSession.detail}</span>
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
        {activeSurface === "deployment" && (
          <DeploymentSettings config={config} onSave={saveDeployment} onReset={resetDeployment} />
        )}
      </main>
    </div>
  );
}
