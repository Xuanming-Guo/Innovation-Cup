# ADR 0004: Google AI credential modes

- **Status:** Accepted
- **Date:** 26 September 2026
- **Issue:** [#38](https://github.com/Xuanming-Guo/Innovation-Cup/issues/38)
- **Supersedes:** The single Developer API credential choice in ADR 0002

## Context

Some companies receive Gemini access as a Developer API key. Others receive a Google Cloud
service-account key whose project is authorised for Vertex AI. These are different authentication
mechanisms; a service-account JSON object is not a Gemini API key. Executing a pasted Python sample
or shipping either credential in a desktop binary would violate the existing trust boundary.

## Decision

Each company may configure exactly one active Google AI credential in **Connections**:

- `api_key` uses the Gemini Developer API; or
- `vertex_service_account` uses Vertex AI with explicit service-account credentials, project and
  server-configured location.

Only a current company administrator may test, configure, rotate or remove a credential. The API
performs a no-company-content model metadata request before persistence. Vertex input must be the
downloaded JSON object, never Python code. It is parsed as data with duplicate and unknown fields
rejected, checked for the expected service-account type, Google endpoints, project/email binding,
key shape and optional server project allowlist, then cryptographically loaded with only the
`cloud-platform` OAuth scope. The canonical JSON is the secret stored in Supabase Vault.

Application rows and API responses contain only provider mode, a one-way hint, validated model,
Vertex project ID, service-account email, location and timestamps. Test/configure/rotate/remove
actions are audited without plaintext. Only `coordination_worker`, under active company context,
may resolve the Vault plaintext. It constructs a short-lived official SDK client using either
`api_key=...` or `vertexai=True` with explicit project, location and credentials.

The original API-key request remains compatible. Database compatibility wrappers keep an older
API/worker deployment functional during rollout, but the legacy resolver fails closed when the
selected mode is Vertex.

## Consequences

- Companies can use organiser- or company-provided Vertex access without a product-wide Google
  credential and may still choose a Developer API key later.
- The host adds no Google secret environment variable. It may restrict accepted Vertex projects
  with `COORDINATION_VERTEX_ALLOWED_PROJECT_IDS` and sets the location with
  `COORDINATION_VERTEX_LOCATION`.
- A service-account key exposed in chat, logs or screenshots must be revoked and replaced before
  it is installed; encrypted storage cannot make an already exposed key safe.
- Live Vertex access, IAM roles, API enablement, quota, billing and model availability remain
  external deployment checks and are not proven by fixture tests.
