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
   permitted excerpts, permitted employee identities plus their active capability/permission
   identifiers, recorded availability windows, current committed schedule blocks, prior authorised
   clarification answers and explicit missing-data markers. It records a canonical SHA-256 digest.
4. One adapter calls the official `google-genai` SDK. The worker resolves the current company's
   encrypted Gemini API key or Vertex service-account JSON from Supabase Vault under the same
   tenant context and constructs a short-lived client for the selected mode. Vertex clients bind
   explicit service-account credentials, project and location. The call has an explicit timeout,
   bounded retry, a fixed model/prompt/schema/safety profile, explicitly disabled model tools and
   a compact provider-generation schema. The provider schema guides shape without duplicating
   every domain constraint; the full strict contract is enforced locally in the next step.
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
basis. An evidence basis must name a source-version ID and locator present in the projection. A
clarification basis must name an immutable response present in the permission-bounded projection.
An assumption basis must name a declared assumption. Stale, expired, cross-company or unselected
source versions and unknown response IDs reject the candidate. Material assumptions and
non-authoritative evidence stop at `clarification_required`; they do not silently become hard
constraints. Every deterministic `clarify` admission issue is converted to a visible blocking
manager question in the same transaction as the candidate. A deferred database invariant rejects
any clarification-required candidate transaction that finishes without such an action. Migration
17 backfills candidates created before that guarantee, including the connected-demo request that
exposed the defect.

Missing capacity, commitments or policy are represented explicitly instead of being treated as
zero or guessed. Recorded planning-resource availability and committed blocks are projected rather
than reported as missing. When a blocking question is legitimate, an active manager can answer all
current blocking questions. The database binds the immutable answers to the exact request version,
candidate, questions, actor, digest and idempotency command, marks the earlier request answered and
creates a derived request version. The worker sees only that authorised lineage and resumes through
the normal typed gateway and admission boundary. A resolved material assumption is cited through
its immutable clarification response and is not recreated as a new assumption. The trusted
materialiser converts admitted
candidate fields into allowlisted `ValidatedConstraint` records and an immutable snapshot; the Z3
compiler accepts only that snapshot, never model JSON. A unified cross-request action inbox remains
the incomplete part of #51.

## Failure behavior

- Refusal, timeout, throttling, exhausted bounded retries, transport failure and invalid output
  are distinct recorded outcomes.
- Schema-invalid output is not repaired by executing model-provided code or expressions.
- A projection exceeding the configured character budget fails before a provider call.
- A reused idempotency key returns the original request only when its canonical request digest
  matches; a different request receives a conflict.
- Provider error messages and credentials are not returned to clients or stored in the run
  ledger.

Interpretation runs through the durable worker. Live synthetic Vertex calls established that the
credential, project, model and basic structured-output route were valid while the original nested
JSON Schema exceeded Vertex's effective request complexity. The provider-facing schema is now
dereferenced and reduced to structural types, required fields, enums, nullability and the two
basis variants; the unmodified strict Pydantic contract and deterministic admission remain the
authoritative boundary. The exact corrected schema completed a live no-company-content Vertex
service-account probe on 26 September 2026. Fixture tests use no external model or company data;
the full hosted interpretation workflow still requires a post-deployment run. The worker host is
portable and is not required to run on Google Cloud.
