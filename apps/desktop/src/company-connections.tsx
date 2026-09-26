import { useEffect, useState } from "react";

import {
  configureGeminiProvider,
  getGeminiProviderConfiguration,
  removeGeminiProvider,
  type AuthorisedApiContext,
  type GeminiProviderConfiguration,
} from "./api-client";

interface CompanyConnectionsProps {
  api?: AuthorisedApiContext;
  canManage: boolean;
}

function displayTime(value: string | null): string {
  return value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "Not yet";
}

export function CompanyConnections({ api, canManage }: CompanyConnectionsProps) {
  const [configuration, setConfiguration] = useState<GeminiProviderConfiguration | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!api || !canManage) return;
    let active = true;
    void getGeminiProviderConfiguration(api)
      .then((value) => { if (active) setConfiguration(value); })
      .catch((value: unknown) => {
        if (active) setError(value instanceof Error ? value.message : "Connection status failed");
      });
    return () => { active = false; };
  }, [api, canManage]);

  async function saveCredential() {
    if (!api || !canManage || !apiKey.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const value = await configureGeminiProvider(api, apiKey.trim());
      setApiKey("");
      setConfiguration(value);
    } catch (value) {
      setError(value instanceof Error ? value.message : "Gemini connection failed");
    } finally {
      setBusy(false);
    }
  }

  async function removeCredential() {
    if (!api || !canManage) return;
    if (!window.confirm("Remove this company's Gemini credential? New AI requests will stop.")) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setConfiguration(await removeGeminiProvider(api));
      setApiKey("");
    } catch (value) {
      setError(value instanceof Error ? value.message : "Gemini connection removal failed");
    } finally {
      setBusy(false);
    }
  }

  if (!api) {
    return (
      <section className="empty-workspace">
        <span className="eyebrow">Authorised connection required</span>
        <h2>Sign in to manage company AI access.</h2>
        <p>No Gemini credential is accepted or retained by the desktop before authentication.</p>
      </section>
    );
  }

  if (!canManage) {
    return (
      <section className="empty-workspace">
        <span className="eyebrow">Company administrator only</span>
        <h2>AI credentials are managed at company level.</h2>
        <p>Employees use the company connection through the backend and can never read its key.</p>
      </section>
    );
  }

  return (
    <section className="connection-panel" aria-labelledby="gemini-connection-title">
      <header>
        <div>
          <span className="eyebrow">Company-owned AI provider</span>
          <h2 id="gemini-connection-title">Gemini Developer API</h2>
          <p>The key is verified without company content, encrypted in Supabase Vault, and used only by the server-side worker.</p>
        </div>
        <span className={`connection-state ${configuration?.status ?? "loading"}`}>
          {configuration?.status.replace("_", " ") ?? "checking"}
        </span>
      </header>

      {configuration?.status === "configured" && (
        <dl className="connection-facts">
          <div><dt>Credential identifier</dt><dd>{configuration.credential_hint}</dd></div>
          <div><dt>Validated model</dt><dd>{configuration.validated_model}</dd></div>
          <div><dt>Last verified</dt><dd>{displayTime(configuration.validated_at)}</dd></div>
          <div><dt>Last rotated</dt><dd>{displayTime(configuration.rotated_at)}</dd></div>
        </dl>
      )}

      <div className="credential-form">
        <label htmlFor="gemini-api-key">{configuration?.status === "configured" ? "Rotate API key" : "Company API key"}</label>
        <input
          id="gemini-api-key"
          type="password"
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
          autoComplete="off"
          spellCheck={false}
          placeholder="Paste a Gemini API key"
        />
        <small>The plaintext value is submitted once and is never returned by the API.</small>
        <div className="connection-actions">
          {configuration?.status === "configured" && (
            <button className="danger-action" disabled={busy} onClick={() => void removeCredential()}>Remove connection</button>
          )}
          <button className="primary-action" disabled={busy || apiKey.trim().length < 20} onClick={() => void saveCredential()}>
            {busy ? "Verifying…" : configuration?.status === "configured" ? "Verify and rotate" : "Verify and connect"}
          </button>
        </div>
      </div>
      {error && <p className="inline-error" role="alert">{error}</p>}
    </section>
  );
}
