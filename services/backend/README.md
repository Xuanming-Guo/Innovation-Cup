# Coordination backend

This package exposes two separate processes over one shared Python package:

- `python -m uvicorn coordination.api.main:app` runs the FastAPI service.
- `python -m coordination.worker.main` runs durable background work. In the foundation slice it reports
  process readiness only; queue consumption is introduced by its dedicated issue.

No hosted database or model provider is contacted merely by importing or starting the package.
The repository runner adds `src/` to `PYTHONPATH`; this is an application, not a published
Python distribution.

Manager planning intake is available at
`POST /v1/companies/{company_id}/planning-requests` with a bearer token, matching
`X-Company-ID`, and an `Idempotency-Key`. The explicit
`POST /v1/companies/{company_id}/planning-requests/{request_id}/interpret` operation builds a
fresh permission-bounded projection, calls the server-only Gemini adapter and persists the
untrusted candidate plus deterministic admission result. This call is synchronous in the
current slice; issue #12 moves dispatch and retry ownership to the durable worker queue. No
Gemini call occurs unless the interpret operation is invoked and a server-side key is present.

The `coordination.planning` package implements the trusted post-interpretation boundary:
`ValidatedConstraint` records are frozen into a canonical `PlanningSnapshot`, compiled through
an allowlisted finite-domain registry, solved with the pinned native Z3 package and checked by
a separate validator that does not import or trust Z3. It distinguishes malformed input,
infeasibility, timeout/resource exhaustion, unknown and validated feasible/optimal-within-model
results. Existing authorised work is pinned first; at most one unchanged-snapshot repair scope is
tried, and only constraints explicitly marked movable are unpinned. The planning ledger persists
the immutable artifacts and concrete rows. Durable dispatch and public plan workflow endpoints
are intentionally deferred to issue #12 rather than running long solves in an API request.
