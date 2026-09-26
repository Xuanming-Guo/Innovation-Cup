# Portable backend deployment

The backend does not require Google Cloud. `services/backend/Dockerfile` produces one OCI image
with two runtime commands:

- API: `python -m uvicorn coordination.api.main:app --host 0.0.0.0 --port 8080`
- worker: `python -m coordination.worker.main`

Run the API on a request-serving container platform and keep at least one worker process
available to lease durable jobs. The host may be Fly.io, Railway, Render, Azure, AWS, Google
Cloud Run or another OCI-compatible service. Provider choice is operational, not part of the
product authority model.

For the Innovation Cup hosted demo, the selected provider is one operator laptop running
`deploy/local-host/compose.yaml`. It starts the API, worker, a pinned Cloudflare Quick Tunnel and a
registrar from one launcher. The registrar verifies the public `/health/ready` response and
maintains a short Supabase endpoint lease. Native clients authenticate first and resolve the lease,
so a changed Quick Tunnel URL does not require a new installer. This path is free but demo-grade:
the laptop must stay awake, online and running Docker Desktop. See
[ADR 0003](../adr/0003-single-laptop-hosted-demo.md).

Both processes need their own least-privileged Postgres connection capable of assuming only the
appropriate `coordination_api` or `coordination_worker` group role. The API also needs the
Supabase URL and JWT issuer. Neither process needs a deployment-wide Gemini credential in
production.

## Company Gemini BYOK

1. A company administrator signs in, opens **Connections**, and selects **Gemini API key** or
   **Vertex service account**.
2. For Vertex, the administrator pastes the downloaded JSON object—not Python code. The API
   validates its type, Google endpoints, project/email binding, private key and optional project
   allowlist, then checks configured-model access without sending company content.
3. A security-definer database function writes the API key or canonical service-account JSON to
   Supabase Vault. The `app` schema stores only its Vault identifier, SHA-256 hint, safe Vertex
   identity metadata and validation metadata.
4. A durable model job runs under the requesting user's current company context.
5. Only `coordination_worker` may call the plaintext resolver. It constructs a short-lived Google
   Gen AI SDK Developer API or Vertex client for that company and never returns or logs the secret.
6. Rotation or mode switching updates the existing Vault entry. Removal deletes it and future
   model jobs stop with `company_gemini_not_configured`.

`COORDINATION_GEMINI_API_KEY` is an optional local/test fallback and is ignored in production.
In static mode the desktop contains the API origin. In laptop-host mode it contains only the
discovery-mode flag, Supabase URL, Supabase publishable key, company UUID and user session.

## Required production configuration

- `COORDINATION_ENVIRONMENT=production`
- `COORDINATION_BUILD_COMMIT=<40-character-release-commit>`
- `COORDINATION_SUPABASE_URL`
- `COORDINATION_SUPABASE_JWT_ISSUER`
- `COORDINATION_DATABASE_URL` supplied separately to API and worker deployments
- `COORDINATION_CORS_ALLOWED_ORIGINS` when the native-origin defaults are not sufficient
- `COORDINATION_VERTEX_LOCATION` (default `global`) and, when policy requires it,
  `COORDINATION_VERTEX_ALLOWED_PROJECT_IDS`
- worker lease, renewal, batch and polling values appropriate for the host

Secrets belong in the chosen host's secret store. Company Google credentials do not: they enter through
the authenticated admin workflow and remain encrypted in Supabase Vault. Health endpoints expose
only non-secret configuration state. Deployment, billing and hosted migration application remain
explicit operator actions.

The complete ordered procedure, including runtime role provisioning and every environment value,
is in [production and hosted-demo setup](production-setup.md).
