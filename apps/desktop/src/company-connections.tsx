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

type CredentialKind = GeminiProviderConfiguration["credential_kind"];

function displayTime(value: string | null): string {
  return value
    ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(
        new Date(value),
      )
    : "Not yet";
}

export function CompanyConnections({ api, canManage }: CompanyConnectionsProps) {
  const [configuration, setConfiguration] = useState<GeminiProviderConfiguration | null>(null);
  const [credentialKind, setCredentialKind] = useState<CredentialKind>("api_key");
  const [credential, setCredential] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!api || !canManage) return;
    let active = true;
    void getGeminiProviderConfiguration(api)
      .then((value) => {
        if (active) {
          setConfiguration(value);
          setCredentialKind(value.credential_kind);
        }
      })
      .catch((value: unknown) => {
        if (active) setError(value instanceof Error ? value.message : "Connection status failed");
      });
    return () => {
      active = false;
    };
  }, [api, canManage]);

  async function saveCredential() {
    if (!api || !canManage || !credential.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const value = await configureGeminiProvider(api, {
        kind: credentialKind,
        value: credential.trim(),
      });
      setCredentialKind(value.credential_kind);
      setConfiguration(value);
    } catch (value) {
      setError(value instanceof Error ? value.message : "Google connection failed");
    } finally {
      setCredential("");
      setBusy(false);
    }
  }

  async function removeCredential() {
    if (!api || !canManage) return;
    if (!window.confirm("Remove this company's Google AI credential? New AI requests will stop.")) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const value = await removeGeminiProvider(api);
      setConfiguration(value);
      setCredentialKind(value.credential_kind);
      setCredential("");
    } catch (value) {
      setError(value instanceof Error ? value.message : "Google connection removal failed");
    } finally {
      setBusy(false);
    }
  }

  if (!api) {
    return (
      <section className="empty-workspace">
        <span className="eyebrow">Authorised connection required</span>
        <h2>Sign in to manage company AI access.</h2>
        <p>No Google credential is accepted or retained by the desktop before authentication.</p>
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

  const isVertex = credentialKind === "vertex_service_account";
  const actionLabel = configuration?.status === "configured" ? "Verify and rotate" : "Verify and connect";

  return (
    <section className="connection-panel" aria-labelledby="gemini-connection-title">
      <header>
        <div>
          <span className="eyebrow">Company-owned AI provider</span>
          <h2 id="gemini-connection-title">Google Gemini</h2>
          <p>
            Choose a Gemini Developer API key or Vertex AI service-account JSON. The credential is
            verified without company content, encrypted in Supabase Vault, and used only by the
            server-side worker.
          </p>
        </div>
        <span className={`connection-state ${configuration?.status ?? "loading"}`}>
          {configuration?.status.replace("_", " ") ?? "checking"}
        </span>
      </header>

      {configuration?.status === "configured" && (
        <dl className="connection-facts">
          <div>
            <dt>Authentication</dt>
            <dd>{configuration.credential_kind === "api_key" ? "Developer API key" : "Vertex service account"}</dd>
          </div>
          <div>
            <dt>Credential identifier</dt>
            <dd>{configuration.credential_hint}</dd>
          </div>
          <div>
            <dt>Validated model</dt>
            <dd>{configuration.validated_model}</dd>
          </div>
          <div>
            <dt>Last verified</dt>
            <dd>{displayTime(configuration.validated_at)}</dd>
          </div>
          {configuration.credential_kind === "vertex_service_account" && (
            <>
              <div>
                <dt>Google Cloud project</dt>
                <dd>{configuration.vertex_project_id}</dd>
              </div>
              <div>
                <dt>Service account</dt>
                <dd>{configuration.vertex_client_email}</dd>
              </div>
              <div>
                <dt>Vertex location</dt>
                <dd>{configuration.vertex_location}</dd>
              </div>
            </>
          )}
          <div>
            <dt>Last rotated</dt>
            <dd>{displayTime(configuration.rotated_at)}</dd>
          </div>
        </dl>
      )}

      <div className="credential-form">
        <span className="credential-kind-label">Credential type</span>
        <div className="credential-kind-options" role="group" aria-label="Credential type">
          <button
            type="button"
            className={credentialKind === "api_key" ? "selected" : ""}
            aria-pressed={credentialKind === "api_key"}
            disabled={busy}
            onClick={() => {
              setCredentialKind("api_key");
              setCredential("");
              setError(null);
            }}
          >
            Gemini API key
          </button>
          <button
            type="button"
            className={isVertex ? "selected" : ""}
            aria-pressed={isVertex}
            disabled={busy}
            onClick={() => {
              setCredentialKind("vertex_service_account");
              setCredential("");
              setError(null);
            }}
          >
            Vertex service account
          </button>
        </div>

        <label htmlFor="google-credential">
          {isVertex
            ? configuration?.status === "configured"
              ? "Rotate service-account JSON"
              : "Service-account JSON"
            : configuration?.status === "configured"
              ? "Rotate API key"
              : "Company API key"}
        </label>
        {isVertex ? (
          <textarea
            id="google-credential"
            value={credential}
            onChange={(event) => setCredential(event.target.value)}
            autoComplete="off"
            spellCheck={false}
            rows={9}
            placeholder="Paste the downloaded service-account JSON object, not Python code"
          />
        ) : (
          <input
            id="google-credential"
            type="password"
            value={credential}
            onChange={(event) => setCredential(event.target.value)}
            autoComplete="off"
            spellCheck={false}
            placeholder="Paste a Gemini API key"
          />
        )}
        <small>
          The plaintext value is submitted once, cleared from this form, and never returned by the
          API. Revoke any service-account key that has appeared in chat, logs, or source control.
        </small>
        <div className="connection-actions">
          {configuration?.status === "configured" && (
            <button
              className="danger-action"
              disabled={busy}
              onClick={() => void removeCredential()}
            >
              Remove connection
            </button>
          )}
          <button
            className="primary-action"
            disabled={busy || credential.trim().length < 20}
            onClick={() => void saveCredential()}
          >
            {busy ? "Verifying..." : actionLabel}
          </button>
        </div>
      </div>
      {error && (
        <p className="inline-error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
