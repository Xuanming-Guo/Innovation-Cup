import { useEffect, useMemo, useRef, useState } from "react";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { startAuthorisedSession, type AuthorisedSessionController, type AuthorisedSessionState } from "./authorised-session";
import { AltoShell } from "./alto-shell";
import { useRoute } from "./alto-state";
import { clearPublicRuntimeConfig, getPublicRuntimeConfig, loadPublicRuntimeConfig, savePublicRuntimeConfig, type PublicRuntimeConfigInput } from "./runtime-config";
import { getServiceStatus, type ServiceStatus } from "./service-status";

const INITIAL_SESSION: AuthorisedSessionState = { status: "unconfigured" };
const INITIAL_STATUS: ServiceStatus = { state: "checking", detail: "Checking configured API origin" };
export function App() {
  const environmentConfig = useMemo(() => getPublicRuntimeConfig(), []);
  const [config, setConfig] = useState(() => loadPublicRuntimeConfig());
  const [session, setSession] = useState<AuthorisedSessionState>(INITIAL_SESSION);
  const [service, setService] = useState<ServiceStatus>(INITIAL_STATUS);
  const controller = useRef<AuthorisedSessionController | null>(null);
  const route = useRoute();
  const serviceOrigin = session.status === "connected" ? session.api.apiOrigin : config.apiMode === "static" ? config.apiOrigin : null;
  useEffect(() => { const active = startAuthorisedSession(config, setSession); controller.current = active; return () => { controller.current = null; active.stop(); }; }, [config]);
  useEffect(() => {
    if (!serviceOrigin) return;
    const request = new AbortController(); const timeout = window.setTimeout(() => request.abort(), 4000);
    let current = true;
    void getServiceStatus({ ...config, apiOrigin: serviceOrigin }, request.signal).then((value) => { if (current) setService(value); }).catch(() => { if (current) setService({ state: "unreachable", detail: "Host is unavailable or still starting" }); }).finally(() => window.clearTimeout(timeout));
    return () => { current = false; request.abort(); window.clearTimeout(timeout); };
  }, [config, serviceOrigin]);
  useEffect(() => {
    if (!isTauri() || session.status === "connected" || route.path === "/assistant/overlay") return;
    void invoke("hide_assistant_overlay").catch(() => undefined);
    void invoke("set_assistant_shortcut", { enabled: false, shortcut: "Control+Space" }).catch(() => undefined);
  }, [session.status, route.path]);
  function saveDeployment(input: PublicRuntimeConfigInput) { const next = savePublicRuntimeConfig(input, "ALTO"); setService(INITIAL_STATUS); setSession(INITIAL_SESSION); setConfig(next); window.location.hash = "/home"; }
  function resetDeployment() { clearPublicRuntimeConfig(); setService(INITIAL_STATUS); setSession(INITIAL_SESSION); setConfig(environmentConfig); }
  const identityKey = session.status === "connected" ? `${session.userId}:${session.api.companyId}` : session.status;
  return <AltoShell key={identityKey} config={config} session={session} service={service} onSignOut={async () => { await controller.current?.signOut(); }} saveDeployment={saveDeployment} resetDeployment={resetDeployment} authController={controller} />;
}
