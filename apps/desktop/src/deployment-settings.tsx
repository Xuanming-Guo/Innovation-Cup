import { useState } from "react";

import {
  type PublicRuntimeConfig,
  type PublicRuntimeConfigInput,
} from "./runtime-config";

interface DeploymentSettingsProps {
  config: PublicRuntimeConfig;
  onReset: () => void;
  onSave: (input: PublicRuntimeConfigInput) => void;
  locked?: boolean;
}

export function DeploymentSettings({ config, onReset, onSave, locked = false }: DeploymentSettingsProps) {
  const [apiOrigin, setApiOrigin] = useState(config.apiOrigin);
  const [supabaseUrl, setSupabaseUrl] = useState(config.supabaseUrl ?? "");
  const [supabasePublishableKey, setSupabasePublishableKey] = useState(
    config.supabasePublishableKey ?? "",
  );
  const [defaultCompanyId, setDefaultCompanyId] = useState(config.defaultCompanyId ?? "");
  const [error, setError] = useState<string | null>(null);

  function save() {
    setError(null);
    try {
      onSave({ apiOrigin, supabaseUrl, supabasePublishableKey, defaultCompanyId });
    } catch (value) {
      setError(value instanceof Error ? value.message : "Deployment configuration is invalid");
    }
  }

  if (locked) return (
    <section className="deployment-panel" aria-label="Deployment configuration" data-onboarding-target="deployment">
      <header>
        <div>
          <span className="eyebrow">Public runtime configuration</span>
          <h2>Deployment override</h2>
          <p>This hackathon installation is already connected. Configuration is locked for the demo.</p>
        </div>
        <span className="connection-state configured">configured</span>
      </header>
      <div className="deployment-form">
        {[
          ["API origin", "api-origin-mask"],
          ["Supabase project URL", "supabase-url-mask"],
          ["Supabase publishable key", "supabase-key-mask"],
          ["Company ID", "company-id-mask"],
        ].map(([label, id]) => <div key={id}>
          <strong id={id}>{label}</strong>
          <p aria-labelledby={id} aria-label={`${label} configured`}>{"*".repeat(24)}</p>
        </div>)}
      </div>
    </section>
  );

  return (
    <section className="deployment-panel" aria-label="Deployment configuration">
      <header>
        <div>
          <span className="eyebrow">Public runtime configuration</span>
          <h2>Deployment override</h2>
          <p>
            Production installers already contain these public values. This local override is for
            development, operator recovery, or intentionally connecting a different deployment.
            {config.apiMode === "supabase-discovery" &&
              " This installer currently discovers the laptop host after sign-in; saving here switches this device to a static API origin."}
          </p>
        </div>
        <span className={`connection-state ${config.supabaseConfigured && config.defaultCompanyId ? "configured" : "not_configured"}`}>
          {config.supabaseConfigured && config.defaultCompanyId ? "configured" : "setup required"}
        </span>
      </header>
      <div className="deployment-warning">
        The publishable key is not privileged, but Auth and RLS still enforce access. Never enter a
        database password, Supabase secret/service-role key, or Gemini API key here. A company
        administrator adds the Gemini key later under Connections.
      </div>
      <div className="deployment-form">
        <label htmlFor="api-origin">API origin</label>
        <input id="api-origin" type="url" value={apiOrigin} onChange={(event) => setApiOrigin(event.target.value)} placeholder="https://api.example.com" />
        <small>The HTTPS origin of the deployed FastAPI service. Loopback HTTP is accepted only for local development.</small>

        <label htmlFor="supabase-url">Supabase project URL</label>
        <input id="supabase-url" type="url" value={supabaseUrl} onChange={(event) => setSupabaseUrl(event.target.value)} placeholder="https://your-project-ref.supabase.co" />
        <small>Project Settings → Data API → Project URL.</small>

        <label htmlFor="supabase-key">Supabase publishable key</label>
        <input id="supabase-key" value={supabasePublishableKey} onChange={(event) => setSupabasePublishableKey(event.target.value)} placeholder="sb_publishable_..." autoComplete="off" />
        <small>This client key is intentionally public and remains constrained by Auth and RLS.</small>

        <label htmlFor="company-id">Company ID</label>
        <input id="company-id" value={defaultCompanyId} onChange={(event) => setDefaultCompanyId(event.target.value)} placeholder="00000000-0000-0000-0000-000000000000" autoComplete="off" />
        <small>The company UUID created by the seed/operator workflow, not a user ID.</small>

        {error && <p className="inline-error" role="alert">{error}</p>}
        <div className="deployment-actions">
          <button className="secondary-action" type="button" onClick={onReset}>Use build defaults</button>
          <button className="primary-action" type="button" onClick={save}>Save and connect</button>
        </div>
      </div>
    </section>
  );
}
