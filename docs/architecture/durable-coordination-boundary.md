# Durable coordination boundary

Issue #12 moves interpretation, planning and internal notification delivery out of request-bound
execution. This document records the implemented repository boundary; it is not evidence that the
migration or optional deployment resources have been applied to a hosted environment.

## State and lease model

`app.durable_jobs` is the single durable queue. Planning-request inserts enqueue
`interpretation.run`; frozen snapshots enqueue `planning.run`; transactional outbox inserts enqueue
`outbox.deliver`; quarantined files enqueue `private_file.scan`. A logical aggregate has one job, and
command/idempotency digests prevent a different command from being hidden behind a reused key.

The worker atomically leases ready rows with `FOR UPDATE SKIP LOCKED`. Each attempt receives a new
lease token and an immutable `job_attempts` row. Renewal, completion, failure and side-effect
delivery require the exact worker and lease token. An expired lease is reconciled to bounded retry,
dead letter or cancellation. Ambiguous and non-retryable outcomes stop in `review_required` rather
than being guessed successful. A manager whose active planning authority was revoked cannot start
queued Gemini or Z3 work.

Interpretation uses deterministic attempt-scoped run identifiers and reconciles an already
persisted admitted/clarification outcome. Planning loads the immutable snapshot, runs the real
allowlisted Z3 engine and independent validator, and persists through the existing immutable
ledger. The API returns `202` plus a job identifier; it does not call Gemini or Z3 in the request.
No Supabase Edge Function owns this pipeline.

## Outbox and notifications

Approved state and `outbox_intents` are written by the existing atomic commit transaction. The
outbox trigger creates one `outbox.deliver` job. Delivery rechecks current target visibility for
each active membership and writes recipient-specific, idempotent `app.notifications` rows. The
persisted row is authoritative; delivery remains safe if the worker repeats after an ambiguous
response.

A notification insert emits only this private Supabase Realtime broadcast:

```json
{"schema_version":1,"type":"authorised_state_stale"}
```

The topic is `user:<auth.uid>`. Authenticated clients have an exact receive policy and no broadcast
write policy. Application tables are not added to the Realtime Postgres Changes publication. The
desktop treats broadcasts as lossy hints: it refetches `/v1/session` and its notification page
through FastAPI on initial connection, a later `SUBSCRIBED` state, focus, network recovery and a
fallback interval. Every refetch therefore repeats JWT, current membership and row-visibility
checks. Extra or malformed broadcast fields are ignored.

## Operations and remaining gates

The worker emits sanitised JSON job/cycle events and writes heartbeats. Managers can read company
queue/outbox/notification metrics through FastAPI. API readiness and worker startup verify that the
lease function exists; liveness remains process-only. The API and worker use separate database
secrets on any supported host; the Cloud Run definitions are one optional example. Company Gemini
keys are encrypted in Supabase Vault, and only the worker may resolve the current tenant's key for
a leased model job.

The quarantined-file job currently fails closed into `review_required` with
`file_scanner_not_configured`; no file is declared clean without a real malware scanner and private
object mover. Interpretation creates the admitted candidate, and planning consumes an already
frozen snapshot; the trusted candidate-to-constraint/snapshot materialiser is still a distinct
stage to complete with the connected scenario. Hosted migration, live-provider and crash/restart
evidence remain deployment/evaluation gates.
