import { useState } from "react";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { altoRequest, type AltoApiContext, type Connection, type WorkspacePreferences } from "./alto-api";
import { Badge, EmptyState, ErrorNotice, Icon, IconButton, Loading, PageHeading } from "./alto-ui";
import { dateTime, humanize, navigate, useCommand, useResource } from "./alto-state";
export function SettingsTabs({ active }: {
    active: string;
}) { return <nav className="alto-settings-tabs" aria-label="Settings sections">{[["workspace", "Workspace"], ["connections", "Connections"], ["ai", "AI & credentials"], ["deployment", "Deployment"], ["about", "About"]].map(([id, title]) => <button key={id} className={active === id ? "active" : ""} onClick={() => navigate(`/settings/${id}`)}>{title}</button>)}</nav>; }
export function WorkspaceSettings({ api, preferences, onSaved }: {
    api?: AltoApiContext;
    preferences: WorkspacePreferences;
    onSaved: (preferences: WorkspacePreferences) => void;
}) {
    const [draft, setDraft] = useState(preferences);
    const [saved, setSaved] = useState(false);
    const command = useCommand();
    function update(patch: Partial<WorkspacePreferences>) { setDraft((current) => ({ ...current, ...patch })); setSaved(false); }
    return <div>
<PageHeading eyebrow="Settings / Workspace preferences" title="Workspace preferences" subtitle="Customize your ALTO experience."/>
<SettingsTabs active="workspace"/>
<section className="alto-settings-section">
<h2>Sidebar display</h2>
<p>Choose how the sidebar appears across ALTO.</p>
<div className="alto-segmented">
<button className={!draft.sidebar_collapsed ? "selected" : ""} onClick={() => update({ sidebar_collapsed: false })}>Icons and labels</button>
<button className={draft.sidebar_collapsed ? "selected" : ""} onClick={() => update({ sidebar_collapsed: true })}>Icons only</button>
</div>
<small>You can also toggle the sidebar from any page.</small>
</section>
<section className="alto-settings-section">
<h2>Motion</h2>
<p>Control subtle animations in the graph and interface.</p>
<label className="alto-toggle">
<span className="alto-switch">
<input type="checkbox" checked={draft.graph_breathing} onChange={(event) => update({ graph_breathing: event.target.checked })}/>
<span className="alto-switch-thumb" aria-hidden="true"/>
</span>
<span className="alto-toggle-label">Gentle graph breathing</span>
</label>
<label className="alto-toggle">
<span className="alto-switch">
<input type="checkbox" checked={draft.reduce_motion} onChange={(event) => update({ reduce_motion: event.target.checked })}/>
<span className="alto-switch-thumb" aria-hidden="true"/>
</span>
<span className="alto-toggle-label">Reduce motion</span>
</label>
<small>Reduce motion overrides breathing and task-merge animations. Your operating system preference is also respected.</small>
</section>
<section className="alto-settings-section">
<h2>Desktop shortcut</h2>
<p>Quickly open the ALTO input bar from anywhere.</p>
<label className="alto-toggle">
<span className="alto-switch">
<input type="checkbox" checked={draft.desktop_shortcut_enabled} disabled={!isTauri()} onChange={(event) => update({ desktop_shortcut_enabled: event.target.checked })}/>
<span className="alto-switch-thumb" aria-hidden="true"/>
</span>
<span className="alto-toggle-label">Show ALTO input bar <kbd>{draft.shortcut.replace("Control", "Ctrl").replaceAll("+", " + ")}</kbd></span>
</label>
<small>{isTauri() ? "Microphone starts only when you press it. No automatic recording." : "The global shortcut is available in the installed desktop app. The browser never registers a system shortcut."}</small>{isTauri() && <button className="alto-text-button" onClick={() => void command.run(() => invoke("show_assistant_overlay"))}>Open desktop input bar</button>}</section>
<footer className="alto-settings-save">{saved && <span role="status">Preferences saved.</span>}<button className="alto-primary" disabled={!api || command.busy} onClick={() => void command.run(async () => { if (!api)
        return; if (isTauri())
        await invoke("set_assistant_shortcut", { enabled: draft.desktop_shortcut_enabled, shortcut: draft.shortcut }); const value = await altoRequest<WorkspacePreferences>(api, "/me/preferences", { method: "PATCH", body: { ...draft, row_version: undefined, expected_row_version: preferences.row_version } }); onSaved(value); setDraft(value); setSaved(true); })}>Save preferences</button>
</footer>
<ErrorNotice error={command.error}/>
</div>;
}
export function ConnectionsView({ api, isDemo = false }: {
    api?: AltoApiContext;
    isDemo?: boolean;
}) {
    const resource = useResource<{
        connections: Connection[];
    }>(api, "/connections");
    const command = useCommand();
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [permissionView, setPermissionView] = useState(false);
    const selected = resource.data?.connections.find((connection) => connection.id === selectedId) ?? null;
    return <div>
<PageHeading eyebrow="Settings / Connections" title="Connections" subtitle="Choose which work sources ALTO can use."/>
<SettingsTabs active="connections"/>{resource.loading && <Loading />}<ErrorNotice error={resource.error ?? command.error} retry={resource.refresh}/>
<div className={`alto-connections-layout ${selected ? "with-inspector" : ""}`}>
<section>{isDemo && <div className="alto-info-banner">
<Icon name="info"/>Demo sources are simulated for now</div>}{(["read", "write"] as const).map((direction) => <section key={direction} className="alto-connection-group">
<h2>{direction === "read" ? "Read sources" : "Write updates"}</h2>
<p>{direction === "read" ? "Allow ALTO to read information from your work tools." : "Allow ALTO to create or update information in your work tools."}</p>{resource.data?.connections.filter((connection) => connection.direction === direction).map((connection) => <button key={connection.id} className={`alto-connection-row ${selected?.id === connection.id ? "selected" : ""}`} onClick={() => { setSelectedId(connection.id); setPermissionView(false); }}>
<span className={`alto-provider-icon ${connection.provider.toLowerCase().replace(/[^a-z]/g, "")}`}>{connection.provider.toLowerCase().includes("teams") ? "T" : connection.provider.toLowerCase().includes("sharepoint") ? "S" : "O"}</span>
<div>
<strong>{connection.name}</strong>
<small>{connection.description}</small>
</div>
<span className="alto-connection-scope">{connection.scope}</span>
<Badge tone={["live", "fixture", "preview"].includes(connection.status) ? "mint" : "pending"}>{humanize(connection.status)}</Badge>
<Icon name="right"/>
</button>)}{!resource.loading && !resource.data?.connections.some((connection) => connection.direction === direction) && <p className="alto-muted">No authorised {direction} connections configured.</p>}</section>)}<p className="alto-caption">People manages profiles and preferences; Connections manages external work sources.</p>
</section>{selected && <aside className="alto-connection-inspector">
<header>
<h2>{selected.name}</h2>
<IconButton icon="close" label="Close connection details" onClick={() => setSelectedId(null)}/>
</header>
<p>{selected.direction === "read" ? "Read source" : "Write updates"}</p>
<p>{selected.description}</p>
<dl>
<dt>Scope</dt>
<dd>{selected.scope}</dd>
<dt>Status</dt>
<dd>
<Badge>{humanize(selected.status)}</Badge>
</dd>
<dt>Time zone</dt>
<dd>{selected.timezone ?? "Not configured"}</dd>
<dt>Last sync</dt>
<dd>{selected.last_synced_at ? dateTime(selected.last_synced_at) : "No successful sync recorded"}</dd>
</dl>
<section>
<h3>What ALTO will {selected.direction === "read" ? "import" : "update"}</h3>
<ul>{selected.imports.map((item) => <li key={item}>{item}</li>)}</ul>
</section>
<section>
<h3>Permissions</h3>
<p>Read and write grants are separate. Revoking a read source revalidates future planning access.</p>
<button className="alto-primary" onClick={() => setPermissionView(!permissionView)}>{permissionView ? "Hide permission details" : "Review permissions"}</button>{permissionView && <div className="alto-permission-details">
<p>Permitted scope: {selected.scope}</p>
<p>Capability: {humanize(selected.status)}. {selected.status === "fixture" || selected.status === "preview" ? "This is a synthetic fixture; no external OAuth connection exists." : "The server rechecks your current connection authority for changes."}</p>
<button className="alto-secondary" disabled={!selected.can_revoke || command.busy} title={!selected.can_revoke ? "Your role cannot revoke this connection" : undefined} onClick={() => void command.run(async () => { if (!api)
        return; await altoRequest(api, `/connections/${selected.id}/revoke`, { method: "POST", body: { expected_row_version: selected.row_version } }); resource.refresh(); })}>Revoke this grant</button>
</div>}</section>
</aside>}</div>
</div>;
}
export function DemoProviderSettings({ api, runMode, locked = false }: {
    api?: AltoApiContext;
    runMode?: string;
    locked?: boolean;
}) {
    const resource = useResource<{ profile_id?: string; current_profile_version_id?: string | null; latest_profile_version_id?: string; provider?: string; credential_kind?: string; management_mode?: string; can_manage?: boolean; status?: string; credential_hint?: string | null; version?: number }>(api, api?.demoRunId ? "/ai-provider/demo-binding" : null);
    const command = useCommand();
    const [kind, setKind] = useState("api_key");
    const [secret, setSecret] = useState("");
    const liveRunSelected = Boolean(api?.demoRunId) && runMode === "live";
    if (locked) return <section className="alto-settings-section">
<h2>Hackathon demo AI</h2>
<p>The shared model connection is managed by the demo operator and is ready to use in this workspace.</p>
<ErrorNotice error={resource.error} retry={resource.refresh}/>{resource.loading && <Loading />}
{resource.data && <div className="alto-project-row" data-onboarding-target="ai">
<div>
<strong>Vertex AI</strong>
<p>{resource.data.status === "configured" ? "Configured for the hackathon demo" : "Demo AI is temporarily unavailable"}</p>
<small aria-label="Credential is hidden">{"*".repeat(24)}</small>
</div>
</div>}
</section>;
    return <section className="alto-settings-section">
<h2>Your demo AI credentials</h2>
<p>Your credential belongs only to your authenticated account. A live run pins an explicit credential version; other visitors cannot use it.</p>
{!liveRunSelected && <div className="alto-info-banner">{api?.demoRunId ? "This workspace uses authored replay, not live AI. Select a Live workspace to connect this credential; your saved credential does not need to be uploaded again." : "Choose a Live demo workspace before connecting AI."}<button className="alto-text-button" onClick={() => navigate("/settings/demo")}>Choose Live workspace and role</button></div>}
<ErrorNotice error={resource.error ?? command.error} retry={resource.refresh}/>{resource.loading && <Loading />}{resource.data?.latest_profile_version_id && <div className="alto-project-row">
<div>
<strong>{humanize(resource.data.provider ?? "Google provider")} · version {resource.data.version}</strong>
<p>{humanize(resource.data.status ?? "not_configured")} · {resource.data.credential_hint ?? "Write-only credential"}</p>
<small>{resource.data.current_profile_version_id === resource.data.latest_profile_version_id ? "This exact version is bound to the selected run." : "Latest version is not bound to this run."}</small>
</div>
<button className="alto-secondary" disabled={command.busy} onClick={() => void command.run(async () => { if (!api)
        return; await altoRequest(api, `/ai-provider/demo-versions/${resource.data?.latest_profile_version_id}`, { method: "DELETE" }); resource.refresh(); })}>Revoke</button>
<button className="alto-primary" disabled={!liveRunSelected || command.busy || resource.data.status !== "configured" || resource.data.current_profile_version_id === resource.data.latest_profile_version_id} onClick={() => void command.run(async () => { if (!api || !liveRunSelected) return; await altoRequest(api, "/ai-provider/demo-binding", { method: "POST", body: { profile_version_id: resource.data?.latest_profile_version_id } }); resource.refresh(); })}>Bind exact version to this run</button>
</div>}<label className="alto-field">Credential type<select value={kind} onChange={(event) => { setKind(event.target.value); setSecret(""); }}>
<option value="api_key">Gemini Developer API key</option>
<option value="vertex_service_account">Vertex service account JSON</option>
</select>
</label>
<label className="alto-field">Write-only credential{kind === "api_key" ? <input type="password" autoComplete="off" value={secret} onChange={(event) => setSecret(event.target.value)}/> : <textarea rows={6} autoComplete="off" spellCheck={false} value={secret} onChange={(event) => setSecret(event.target.value)}/>}</label>
<button className="alto-primary" disabled={!liveRunSelected || command.busy || !secret.trim()} onClick={() => void command.run(async () => { if (!api || !liveRunSelected)
        return; if (kind === "vertex_service_account") {
        const parsed: unknown = JSON.parse(secret);
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
            throw new Error("Enter a service-account JSON object.");
    } await altoRequest(api, "/ai-provider/gemini", { method: "PUT", body: { credential_kind: kind, ...(kind === "api_key" ? { api_key: secret } : { service_account_json: secret }), correlation_id: crypto.randomUUID() } }); setSecret(""); resource.refresh(); })}>Validate and store securely</button>
<p className="alto-caption">Provider validation may make a content-free provider request. Credentials are never saved in browser storage or returned after saving.</p>
{liveRunSelected && resource.data?.current_profile_version_id && <div className="alto-info-banner">AI is connected to this workspace. You can now plan from Home.<button className="alto-primary" onClick={() => navigate("/home")}>Go to Home</button></div>}
</section>;
}
export function AboutView({ hostStatus, apiOrigin, locked = false, onReplayOnboarding }: {
    hostStatus: string;
    apiOrigin: string | null;
    locked?: boolean;
    onReplayOnboarding?: () => void;
}) { return <div>
<PageHeading title="About ALTO" subtitle="Human-led coordination. AI proposes. Z3 checks. People decide."/>
<SettingsTabs active="about"/>
<section className="alto-settings-section">
<h2>Connection diagnostics</h2>
<dl>
<dt>Runtime</dt>
<dd>{isTauri() ? "Installed desktop" : "Browser preview"}</dd>
<dt>Host</dt>
<dd>{hostStatus}</dd>
<dt>API origin</dt>
<dd>{locked ? "*".repeat(24) : apiOrigin ?? "Sign in to resolve the current host"}</dd>
</dl>
<p>Deployment and signing status must be verified from the release manifest. A browser preview is not a native installation test.</p>
{locked && onReplayOnboarding && <button className="alto-secondary" onClick={onReplayOnboarding}>Replay onboarding</button>}
</section>
<EmptyState title="Your data stays permission-scoped">No clipboard, screen, foreground-window or ambient microphone access is used to infer context.</EmptyState>
</div>; }
