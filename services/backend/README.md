# Coordination backend

This package exposes two separate processes over one shared Python package:

- `python -m uvicorn coordination.api.main:app` runs the FastAPI service.
- `python -m coordination.worker.main` verifies the durable schema, leases queued work, renews exact
  attempt tokens and records bounded terminal/retry outcomes plus worker heartbeats.

No hosted database or model provider is contacted merely by importing or starting the package.
The repository runner adds `src/` to `PYTHONPATH`; this is an application, not a published
Python distribution.

Manager planning intake is available at
`POST /v1/companies/{company_id}/planning-requests` with a bearer token, matching
`X-Company-ID`, and an `Idempotency-Key`. The explicit
`POST /v1/companies/{company_id}/planning-requests/{request_id}/interpret` operation returns a
durable job with HTTP 202. The worker builds the fresh permission-bounded projection, calls the
server-only Gemini adapter and persists the untrusted candidate plus deterministic admission
result. No Gemini call occurs in the API process or without a server-side worker key.

The `coordination.planning` package implements the trusted post-interpretation boundary:
`ValidatedConstraint` records are frozen into a canonical `PlanningSnapshot`, compiled through
an allowlisted finite-domain registry, solved with the pinned native Z3 package and checked by
a separate validator that does not import or trust Z3. It distinguishes malformed input,
infeasibility, timeout/resource exhaustion, unknown and validated feasible/optimal-within-model
results. Existing authorised work is pinned first; at most one unchanged-snapshot repair scope is
tried, and only constraints explicitly marked movable are unpinned. The planning ledger persists
the immutable artifacts and concrete rows. Frozen snapshots enqueue real solver work for the
durable worker; Z3 never runs in an API request or Edge Function. The trusted
candidate-to-constraint/snapshot materialiser remains a separate incomplete stage.

The `coordination.approval` package exposes review/evidence and explicit approve, reject and commit
operations for an existing validated proposal. Decisions bind proposal, snapshot, source,
base-revision and policy digests. The database rechecks current authority and source freshness,
serializes commits under the company planning revision, copies the exact independently validated
candidate to committed work/schedule rows, and writes audit plus outbox intent in the same
transaction. Planning approval never substitutes for the separately hashed employee-brief
disclosure approval.

The `coordination.employee` package exposes the human execution boundary. Employees list only
their active owner assignments and the exact separately approved employee brief. Lifecycle
commands bind the current task version and an idempotency key. Managers assign a versioned reviewer
policy; submissions bind that exact policy, clean private-file metadata and an immutable digest;
the assigned reviewer accepts or requests revision against the exact version. A revision does not
increase accepted employee evidence. Acceptance updates only the submitting employee. See
[`docs/architecture/employee-workflow-boundary.md`](../../docs/architecture/employee-workflow-boundary.md)
for endpoint and trust-boundary details.
