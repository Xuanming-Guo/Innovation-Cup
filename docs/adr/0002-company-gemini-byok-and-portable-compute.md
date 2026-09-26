# ADR 0002: Company Gemini BYOK and portable compute

- **Status:** Accepted; credential-mode decision superseded by ADR 0004
- **Date:** 26 September 2026
- **Issue:** [#13](https://github.com/Xuanming-Guo/Innovation-Cup/issues/13)

## Context

The original foundation selected Google Cloud Run and one deployment-wide Gemini secret. That
coupled model billing and credential authority to the product operator, made one leaked key affect
every tenant and implied that Google Cloud must host application sessions. The founder instead
selected company-owned Gemini credentials while retaining Supabase as the system of record.

Direct desktop-to-Gemini calls are rejected. A native binary cannot keep a shared secret, and
individual employee keys would fragment policy, billing, model configuration, audit and rotation.
Application sessions and durable job state belong in Supabase regardless of where compute runs.

## Decision

The original decision selected one Gemini Developer API credential per company. ADR 0004 extends
that boundary to a mutually exclusive choice between a Developer API key and Vertex AI
service-account JSON while preserving the same write-only, Vault-backed and worker-only rules.

Only the `coordination_worker` role can execute the plaintext resolver, and only with current
actor/company/purpose context and an active company membership. Every model-backed job resolves
the credential for the job's company and constructs a short-lived typed gateway. The API,
desktop, responses, logs, fixtures and audit details never receive the plaintext value. Rotation
updates the existing Vault entry; removal deletes it and makes later model jobs fail explicitly.

`COORDINATION_GEMINI_API_KEY` remains a local/test fallback and is ignored in production.

FastAPI and the durable worker continue to share one OCI image with separate commands. They may
run on any suitable container platform. Cloud Run manifests remain an optional example, not a
required topology. Supabase Edge Functions remain limited to short gateway operations; native
Python Z3 and multi-stage durable work stay in the worker.

## Consequences

- Each customer controls Gemini quota, billing, revocation and provider terms for its own use.
- Employees use the company connection without possessing its credential.
- Google associates Developer API keys or Vertex service accounts with projects for quota and
  billing, but the application does not need to run on Google Cloud.
- Production readiness can be evaluated without a global model credential; an individual model
  job fails safely when its company has no credential.
- The operator must secure Vault access, database function ownership, runtime database roles and
  the chosen container host.
- Live-provider, data-use, residency and contractual suitability remain company-specific release
  checks and cannot be inferred from fixture tests.
