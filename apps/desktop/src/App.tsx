import { useEffect, useMemo, useState } from "react";

import { getPublicRuntimeConfig } from "./runtime-config";
import { getServiceStatus, type ServiceStatus } from "./service-status";

const futureSurfaces = [
  "Manager workspace",
  "Plan review",
  "My work",
  "Connections",
] as const;

const architecture = [
  ["Desktop", "Tauri 2 · React · TypeScript"],
  ["Application API", "FastAPI · versioned HTTP contract"],
  ["Durable compute", "Separate Python worker process"],
  ["System of record", "Supabase · configuration pending"],
] as const;

const initialStatus: ServiceStatus = {
  state: "checking",
  detail: "Checking configured API origin",
};

export function App() {
  const config = useMemo(() => getPublicRuntimeConfig(), []);
  const [serviceStatus, setServiceStatus] = useState<ServiceStatus>(initialStatus);

  useEffect(() => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 4_000);

    void getServiceStatus(config, controller.signal)
      .then(setServiceStatus)
      .catch(() => {
        setServiceStatus({
          state: "unreachable",
          detail: "API health check timed out",
        });
      })
      .finally(() => window.clearTimeout(timeout));

    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [config]);

  return (
    <div className="app-shell">
      <aside className="side-rail" aria-label="Primary navigation">
        <div className="brand">
          <img src="/brand-mark.svg" alt="" width="28" height="28" />
          <span>{config.productName}</span>
        </div>

        <nav className="navigation">
          <a className="nav-item active" href="#foundation" aria-current="page">
            <span className="nav-index">01</span>
            Foundation
          </a>
          {futureSurfaces.map((surface, index) => (
            <span className="nav-item disabled" aria-disabled="true" key={surface}>
              <span className="nav-index">{String(index + 2).padStart(2, "0")}</span>
              {surface}
            </span>
          ))}
        </nav>

        <div className="side-note">
          <span className="eyebrow">Build state</span>
          <strong>Foundation only</strong>
          <p>Product workflows remain unavailable until their reviewed slices merge.</p>
        </div>
      </aside>

      <main className="workspace" id="foundation">
        <header className="topbar">
          <div>
            <span className="eyebrow">Coordination Engine · 0.1.0</span>
            <h1>Application foundation</h1>
          </div>
          <span className={`service-chip ${serviceStatus.state}`}>
            <span className="status-dot" aria-hidden="true" />
            API {serviceStatus.state}
          </span>
        </header>

        <section className="intro-panel" aria-labelledby="foundation-heading">
          <div>
            <span className="section-number">01 / Foundation</span>
            <h2 id="foundation-heading">A native shell with honest boundaries.</h2>
            <p>
              The desktop, API and durable worker are separate executable processes. This
              screen reports only what is currently implemented; planning and employee
              workflows will appear through subsequent reviewed issues.
            </p>
          </div>
          <div className="api-readout" aria-live="polite">
            <span className="eyebrow">Configured API</span>
            <code>{config.apiOrigin}</code>
            <strong>{serviceStatus.detail}</strong>
            {serviceStatus.apiVersion ? (
              <small>
                API {serviceStatus.apiVersion} · build {serviceStatus.buildCommit}
              </small>
            ) : null}
          </div>
        </section>

        <section className="status-grid" aria-label="Foundation components">
          {architecture.map(([name, detail], index) => (
            <article className="status-row" key={name}>
              <span className="row-number">{String(index + 1).padStart(2, "0")}</span>
              <div>
                <h3>{name}</h3>
                <p>{detail}</p>
              </div>
              <span className="text-status">Configured</span>
            </article>
          ))}
        </section>

        <section className="boundary-panel" aria-labelledby="boundary-heading">
          <div>
            <span className="eyebrow">Credential boundary</span>
            <h2 id="boundary-heading">Only public configuration enters the desktop.</h2>
          </div>
          <ul>
            <li>
              <strong>Public:</strong> API origin, Supabase project URL and publishable key.
            </li>
            <li>
              <strong>Server only:</strong> database credentials, Supabase privileged secrets
              and Gemini credentials.
            </li>
            <li>
              <strong>Current state:</strong>{" "}
              {config.supabaseConfigured
                ? "public Supabase configuration supplied"
                : "Supabase public configuration not supplied"}
              .
            </li>
          </ul>
        </section>
      </main>
    </div>
  );
}
