# Cloud Run deployment boundary

The repository contains reviewable deployment definitions but does not deploy automatically:

- `deploy/cloud-run/api.service.yaml` describes the request-driven FastAPI service.
- `deploy/cloud-run/worker-pool.yaml` describes the continuously allocated durable worker.
- `services/backend/Dockerfile` supplies one image with separate commands.

Before deployment, replace `PROJECT_ID`, `REGION`, `COMMIT_SHA`, `SUPABASE_PROJECT_URL` and
`SUPABASE_JWT_ISSUER`; create the named service accounts and secret versions.
Use distinct least-privilege service accounts. The worker pool must not use the API service's
public request identity.

Create separate `coordination-api-database-url` and `coordination-worker-database-url` secrets.
The API connection may assume only `coordination_api`; the worker connection may assume only
`coordination_worker`. Only the worker receives `coordination-gemini-api-key`. Neither database
URL nor the Gemini key belongs in the desktop build.

The definitions reference secret names, never values. Prefer workload identity and Cloud Run
service accounts over downloadable Google service-account JSON keys. Deployment, billing and
external writes require an explicit owner action and are **not performed by repository checks**.

The API liveness endpoint is `/health/live`. In production, `/health/ready` returns HTTP 503
until required server configuration is present and the durable-job database function is visible.
The worker performs the same durable-schema check before polling, publishes non-secret JSON cycle
metrics and records a database heartbeat. The committed file-scan handler remains deliberately
fail-closed in `review_required` until a malware scanner and private-object mover are configured.
