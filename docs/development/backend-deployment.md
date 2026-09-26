# Portable backend deployment

The backend does not require Google Cloud. `services/backend/Dockerfile` produces one OCI image
with two runtime commands:

- API: `python -m uvicorn coordination.api.main:app --host 0.0.0.0 --port 8080`
- worker: `python -m coordination.worker.main`

Run the API on a request-serving container platform and keep at least one worker process
available to lease durable jobs. The host may be Fly.io, Railway, Render, Azure, AWS, Google
Cloud Run or another OCI-compatible service. Provider choice is operational, not part of the
product authority model.

Both processes need their own least-privileged Postgres connection capable of assuming only the
appropriate `coordination_api` or `coordination_worker` group role. The API also needs the
Supabase URL and JWT issuer. Neither process needs a deployment-wide Gemini credential in
production.

## Company Gemini BYOK

1. A company administrator signs in and opens **Connections**.
2. The API checks the supplied key against the configured Gemini model without sending company
   content.
3. A security-definer database function writes the key to Supabase Vault and stores only its
   Vault identifier, SHA-256 hint and validation metadata in `app`.
4. A durable model job runs under the requesting user's current company context.
5. Only `coordination_worker` may call the plaintext resolver. It constructs a short-lived Google
   Gen AI SDK client for that company and never returns or logs the key.
6. Rotation updates the existing Vault entry. Removal deletes it and future model jobs stop with
   `company_gemini_not_configured`.

`COORDINATION_GEMINI_API_KEY` is an optional local/test fallback and is ignored in production.
The desktop contains only the API origin, Supabase URL, Supabase publishable key and user session.

## Required production configuration

- `COORDINATION_ENVIRONMENT=production`
- `COORDINATION_BUILD_COMMIT=<40-character-release-commit>`
- `COORDINATION_SUPABASE_URL`
- `COORDINATION_SUPABASE_JWT_ISSUER`
- `COORDINATION_DATABASE_URL` supplied separately to API and worker deployments
- worker lease, renewal, batch and polling values appropriate for the host

Secrets belong in the chosen host's secret store. Company Gemini keys do not: they enter through
the authenticated admin workflow and remain encrypted in Supabase Vault. Health endpoints expose
only non-secret configuration state. Deployment, billing and hosted migration application remain
explicit operator actions.
