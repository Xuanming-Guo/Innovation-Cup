import { useEffect, useMemo, useState } from "react";

import { PlanReviewWorkspace } from "./plan-review";
import { getPublicRuntimeConfig } from "./runtime-config";
import { getServiceStatus, type ServiceStatus } from "./service-status";

const navigation = ["Manager review", "My work", "Connections"] as const;
const initialStatus: ServiceStatus = { state: "checking", detail: "Checking configured API origin" };

export function App() {
  const config = useMemo(() => getPublicRuntimeConfig(), []);
  const [serviceStatus, setServiceStatus] = useState<ServiceStatus>(initialStatus);

  useEffect(() => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 4_000);
    void getServiceStatus(config, controller.signal)
      .then(setServiceStatus)
      .catch(() => setServiceStatus({ state: "unreachable", detail: "API health check timed out" }))
      .finally(() => window.clearTimeout(timeout));
    return () => { window.clearTimeout(timeout); controller.abort(); };
  }, [config]);

  return (
    <div className="app-shell">
      <aside className="side-rail" aria-label="Primary navigation">
        <div className="brand"><img src="/brand-mark.svg" alt="" width="28" height="28" /><span>{config.productName}</span></div>
        <nav className="navigation">
          {navigation.map((surface, index) => (
            <span className={`nav-item ${index === 0 ? "active" : "disabled"}`} aria-current={index === 0 ? "page" : undefined} aria-disabled={index === 0 ? undefined : "true"} key={surface}>
              <span className="nav-index">{String(index + 1).padStart(2, "0")}</span>{surface}
            </span>
          ))}
        </nav>
        <div className="side-note"><span className="eyebrow">Review boundary</span><strong>Human-led commitment</strong><p>AI proposes. Z3 checks. Authorized people decide. The database commits atomically.</p></div>
      </aside>
      <main className="workspace">
        <header className="topbar">
          <div><span className="eyebrow">Coordination Engine · Manager workspace</span><h1>Plan review</h1></div>
          <span className={`service-chip ${serviceStatus.state}`} title={serviceStatus.detail}><span className="status-dot" aria-hidden="true" />API {serviceStatus.state}</span>
        </header>
        <PlanReviewWorkspace />
      </main>
    </div>
  );
}
