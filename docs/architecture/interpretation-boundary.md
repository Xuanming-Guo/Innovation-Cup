# Natural-language interpretation boundary

This slice turns a manager request into an untrusted candidate contract. It does not create a
schedule, a validated constraint, an approval or a committed task.

## End-to-end path

1. An authenticated manager or company administrator submits the original request, selected
   source IDs and optional requested deadline/priority with an idempotency key.
2. FastAPI resolves current company membership and stores the request in the non-exposed `app`
   schema. Selected sources are re-authorised and pinned to their current source-version IDs in
   the same transaction.
3. Interpretation rechecks the manager and every pinned source under the
   `coordination_worker` RLS role. It builds a bounded projection containing source metadata,
   permitted excerpts, permitted employee identities, known structured facts and explicit
   missing-data markers. It records a canonical SHA-256 digest.
4. One adapter calls the official `google-genai` SDK. The Gemini key exists only in server
   configuration. The call has an explicit timeout, at most three configured attempts, a fixed
   model/prompt/schema/safety profile, no model tools and a supported JSON response schema.
5. Pydantic rejects fields outside `CandidateTaskContract`. Trusted admission code then checks
   company/request/version identity, current source versions, retrieved locators, source
   freshness and authority, assumption references, task IDs, dependency endpoints and cycles,
   timezone-aware dates and explicit clarification/unsupported markers.
6. The database records the actual model/configuration version, provider outcome, latency,
   token metadata when supplied, candidate digest, validation issues and viewer-safe trace. It
   stores no API key and no invented chain-of-thought transcript.

```text
manager request
  -> current membership and selected-source authorization
  -> frozen permission-bounded projection + digest
  -> Gemini structured candidate (untrusted)
  -> deterministic admission
  -> admitted candidate | clarification required | rejected/failure
```

## Evidence and clarification rules

Every task, estimate, deadline, requirement and dependency must contain at least one typed
basis. An evidence basis must name a source-version ID and locator present in the projection. An
assumption basis must name a declared assumption. Stale, expired, cross-company or unselected
source versions reject the candidate. Material assumptions and non-authoritative evidence stop
at `clarification_required`; they do not silently become hard constraints.

Missing capacity, commitments or policy are represented explicitly instead of being treated as
zero or guessed. The interpretation may still identify proposed work, but the planning compiler
cannot run until its own required inputs and confirmations exist. The future Z3 compiler accepts
only `ValidatedConstraint` records produced by the next trusted boundary, never model JSON.

## Failure behavior

- Refusal, timeout, throttling, exhausted bounded retries, transport failure and invalid output
  are distinct recorded outcomes.
- Schema-invalid output is not repaired by executing model-provided code or expressions.
- A projection exceeding the configured character budget fails before a provider call.
- A reused idempotency key returns the original request only when its canonical request digest
  matches; a different request receives a conflict.
- Provider error messages and credentials are not returned to clients or stored in the run
  ledger.

The explicit interpret API is synchronous in this slice so the boundary is runnable. Durable
dispatch, leases and crash-safe retry move to the Cloud Run worker in issue #12. A live Gemini
call remains **NOT RUN** until the founder supplies a development credential; fixture tests use
no external model or company data.
