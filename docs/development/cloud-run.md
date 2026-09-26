# Cloud Run deployment boundary

The repository contains reviewable deployment definitions but does not deploy automatically:

- `deploy/cloud-run/api.service.yaml` describes the request-driven FastAPI service.
- `deploy/cloud-run/worker-pool.yaml` describes the continuously allocated durable worker.
- `services/backend/Dockerfile` supplies one image with separate commands.

Before deployment, replace `PROJECT_ID`, `REGION`, `COMMIT_SHA`, `SUPABASE_PROJECT_URL` and
`SUPABASE_JWT_ISSUER`; create the named service accounts and secret versions.
Use distinct least-privilege service accounts. The worker pool must not use the API service's
public request identity.

The definitions reference secret names, never values. Prefer workload identity and Cloud Run
service accounts over downloadable Google service-account JSON keys. Deployment, billing and
external writes require an explicit owner action and are **not performed by repository checks**.

The API liveness endpoint is `/health/live`. In production, `/health/ready` returns HTTP 503
until required server configuration is present. This validates configuration presence only;
later slices add dependency-specific readiness.
