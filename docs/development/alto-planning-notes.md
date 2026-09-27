# ALTO planning implementation notes

Status: implementation written; final-phase verification is recorded separately below. No hosted migrations, provider calls, pushes or deployments are implied by this document.

## Complete candidates, not solver-generated schedules

`services/backend/src/coordination/planning/fixed_contracts.py` defines the immutable `PlanProposalV2` envelope and complete task/block/gate output. The server supplies company/run/request/snapshot references, parent/version and canonical SHA-256 digests. The model supplies complete declared values, never tenant identity, approval state or executable predicates. Equivalent offsets and task/block ordering are normalised for semantic candidate identity. Every actual active participant reserves their entire interval.

`fixed_verifier.py` uses `z3.Solver` on ground integer/Boolean expressions over exact submitted values. It does not call the historical optimiser, obtain replacements from a Z3 model, round times, or alter a candidate after a check. It preserves per-instance admitted rule IDs, records native status separately from `CHECKED`, `VIOLATIONS_FOUND`, `UNABLE_TO_VERIFY` and `INVALID_CANDIDATE`, rejects missing required coverage, and verifies candidate/snapshot digests. A separately implemented concrete validator recomputes exact intervals, effort, overlap, resource-local days, review order and gates before promotion.

Three additional finite constraint families express the scenario without hidden reservations: `active_participants`, `execution_gate` and `task_review_policy`. Self-certification is permitted only by an admitted policy. An explicit decision gate may require submitted, accepted, approved or self-certified work. Scheduling a review does not itself produce that decision. The historical compiler rejects these ALTO-only families rather than silently ignoring them; historical optimiser records remain readable.

`authoring.py` runs one initial authoring round and at most four replacement rounds using the existing official Google SDK adapter. Invalid schema regeneration consumes a round. Unchanged semantic candidates stop. Revisions preserve task definitions and admitted deliverables and are limited to actual failed-rule neighbourhoods and affected successors. SDK retries are one attempt; retryable provider errors return to the existing bounded durable worker. A manager may explicitly continue an older saved `fixed_plan_not_verified` Live job only while fewer than five immutable AI candidates exist. Unknown/timeout is not given to the model as a fabricated business-rule violation. A previous ambiguous unrecorded provider response requires human recovery.

The worker refreshes current source permission/freshness and admitted task content before each authoring round. Existing work has an exact expected row version bound into the candidate. Commitment must recheck that version and the scope revision; accepted artifacts are not silently overwritten by replanning.

Downstream repair scope uses only admitted snapshot dependency/execution-gate/review links,
not a failed candidate's possibly invalid gates. When a permitted review owner changes,
only the reviewed task's exact reviewer references may be synchronized outside that scope;
its schedule and other fields remain protected. Scope is computed once per candidate.

## Durable integration and database boundary

`durable/handlers.py` registers `plan.propose` as the ALTO path. `planning.run` remains explicitly legacy. Snapshot insertion enqueues the ALTO job through the migration-owned queue trigger. The handler reads run mode from the database, not a client/model assertion. The existing worker lease-renewal thread remains responsible for renewal.

`fixed_persistence.py` writes `model_runs`, `ai_plan_proposals`, `plan_verification_runs`, per-instance `plan_verification_rule_results`, and `plan_validation_runs`. Each write transaction sets `app.job_id` and `app.lease_token`; database triggers verify the live lease, cancellation, scope and actor before accepting rows. Provider computation and Z3 run outside transactions. A succeeded provider result, complete candidate and its checks are recorded atomically. `app.promote_verified_ai_proposal` alone promotes a passing candidate into the existing plan/placement/block ledger; it does not fabricate a solver-run row.

All owned planning, interpretation and provider stores propagate authorised demo-run and simulated-actor context. The authenticated Auth user remains the actor; simulation is separately attributed. Snapshot and approval revision reads use `app.scope_planning_revision`, preserving independent visitor run revisions.

Approval API evidence now distinguishes `author_kind`, nullable historical `solver`, `fixed_verification`, and `independent_validation`. Task definitions are joined through the exact snapshot membership, avoiding duplicate definitions from other request versions. A fixed check alone is never business approval, disclosure approval or commitment.

`workspace/graph_read.py` projects the latest exact proposed candidate and its per-instance rule results even when it failed and therefore has no promotable plan. Proposed nodes cannot be executed. Once committed, persisted work items are authoritative and the graph does not attach a newer draft's approval or check result to those committed nodes. People use directory display names, not invented model labels.

Managers can select recorded proposal history with `?proposal_id=<uuid>`. The response binds the selected candidate, verification and independent-validation evidence by their exact immutable IDs. An explicit historical preview never offers approval or execution, and returning to the current graph restores committed work rather than attaching failed D0 evidence to P1.

Successful promotion also creates separate task-scoped brief versions. Each brief contains only that task, and its audience is derived from the admitted owner, active participants and named reviewers. Restricted task prose is withheld. The existing disclosure ledger must approve each exact brief/audience; the worker does not publish briefs or shortcut that decision. Failed proposals produce no brief.

## Northstar authored mode

`planning/northstar.py` is the versioned production scenario module, not a test fixture or a live-model result. It contains the canonical 17 tasks, exact PDT windows, explicit gates and independent reviewer reservations. D0 puts Q1 at Tuesday 10:00–12:00, conflicting with Priya's protected 11:00–12:00 hour. P1 changes Q1 to 09:00–11:00. L1 consumes Alex and Nora's full shared interval; R2 is final accepted completion, not Friday's release start.

The directory/execution resource IDs are `uuid5(company_id, 'person:'+key)`. Task IDs are `uuid5(run_id, 'task:'+lowercase_task_key)`. Scenario source/version IDs come from the current authorised run's persisted records. Evidence locators are the actual `LAUNCH-02` and `LAUNCH-07` excerpts. Source content must include the corresponding exact task and authority/gate facts.

`workspace/northstar.py` creates the canonical request through the existing request store. It does not insert accepted work or bypass admission. The authored interpretation gateway uses the normal permission-bounded projection, deterministic admission and immutable interpretation recorder. Its model identifier is explicitly `authored:northstar-launch.2026-09.v1`. The authored materialiser constructs the exact typed snapshot from that lineage. `authored_replay` checks P1; `authored_d0_check` persists D0's real failure followed by the parent-linked, separately labelled authored P1 check. Neither mode calls Gemini or claims AI generation. Ordinary Live mode preserves the actual model candidate. In the explicitly locked hackathon build, Live request interpretation and materialisation remain unchanged, but the schedule stage directly selects canonical P1 with `authored_replay` provenance and zero model rounds so provider latency or malformed scheduling output cannot strand the judge walkthrough. P1 still has to pass the real fixed verifier and independent validator before promotion.

Live Northstar has a separate finite admission extension in `northstar_authority.py`; the old interpretation-v1 temporal edges alone are insufficient to express approval, self-certification, named reviews or shared active participants. The operator scenario manifest therefore persists a typed `planning_authority` in its LAUNCH-07 source entry and prints the same authority in that source's exact text. The leased worker loads only its run's pinned immutable manifest, checks its canonical digest, and compares all seven selected current source-version and excerpt hashes/text against that manifest. It rejects missing tasks, changed effort, omitted gates, unknown hard rules, unsupported manifest versions and additional scenario requests requiring new policy admission.

The live snapshot preserves model-interpreted task prose but supplements it with those complete trusted authority families. It uses current active resource profiles, protected calendar facts and committed reservations. Apart from the actual Friday release window and final milestone deadline, live task windows cover the full week: no authored P1 day/time is copied into the live choice domain. The live model still supplies every complete candidate placement/block. Profile/calendar changes must advance the scoped planning revision, invalidating approvals against old capacity.

LAUNCH-06 is shared only with Maya and Jordan in the operator source manifest. Fresh proposals also receive only currently confirmed, currently readable employee preference versions; superseded or revoked sharing is not resurrected from older versions. Preferences remain soft guidance, never qualifications, reviewer authority or hidden hard constraints.

## Provider and voice boundary

### Complete conflict feedback and bounded output (27 September follow-up)

The fixed verifier now reports all confirmed false hard ground rules, retaining its original
solver unsat core separately. The repair scope also understands older recorded per-rule
results, so a sufficient conflict subset cannot exclude another known-invalid task. Bounded
resource diagnostics describe the offending tasks and time intervals from the frozen
snapshot, not replacement placements or private source prose. Repairs retain movement locks
and unrelated work; no solver-generated schedule or authored replay is substituted.

Schema/truncation errors and changed admitted facts produce explicit allowlisted next-round
guidance. Known schema paths/categories are sanitized in the gateway; rejected values and
exception messages never enter the feedback. The same five-round bound applies. Prompt
`alto-plan-author.v3` and feedback version are included in the immutable input/configuration
digests, and new model checkpoints persist the exact prompt version.

Full schedules have an optional `COORDINATION_GEMINI_PLAN_MAX_OUTPUT_TOKENS` cap. Without
it, existing deployments retain their shared cap; the local-host bundle sets 32768 for
plan generation/revision only. Other operations retain their current limits, SDK attempts
remain one, and truncated responses still fail closed. Larger actual output can increase
Google charges. The configured host model's [official limits](https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flash)
support this bounded ceiling; this is not evidence that a new paid workflow passed.

Request progress counts only its selected planning job's deterministic model-run IDs under
the existing company/request/run permission boundary. The UI separates worker retries from
recorded AI attempts and maps only allowlisted final model codes. A model-run record is not
provider billing evidence. No schema migration or historical ledger rewrite is required.

The company provider factory supports a fenced per-job resolver. Demo resolution requires the run's immutable visitor-owned Vault credential version and has no company/environment fallback. Configuring a new demo profile returns masked profile/version IDs; binding and revocation are explicit version-scoped commands. Ordinary company configuration retains administrator authority.

The API exposes `GET`/`POST /v1/companies/{company_id}/ai-provider/demo-binding` and `DELETE /v1/companies/{company_id}/ai-provider/demo-versions/{profile_version_id}`. Mutations require an idempotency key and the authorised run context; binding accepts `{profile_version_id}`. Changing the latest profile does not silently replace an existing run's binding.

The shared gateway now supports typed structured operations and stopped-recording audio transcription with the same no-tools policy, SDK error classification, one provider attempt and client cleanup. Raw inline audio is bounded to 8 MiB and an allowlisted media type; the caller enforces duration/consent and deletion. No provider Files API object is created and a transcript is not automatically a command. Google's [official audio documentation](https://ai.google.dev/gemini-api/docs/generate-content/audio), inspected during implementation, documents audio input and structured speech transcription for the configured Gemini family. Installed-client recording, actual provider execution and microphone permission behavior require separate final verification.

## Verification record

Verification was deferred until the coordinating agent explicitly opened the final integration phase, as requested. On 27 September 2026:

- Focused backend suite: **77 passed** with one upstream Starlette/httpx deprecation warning. Command from `services/backend`: `.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_fixed_planning.py tests/test_planning.py tests/test_materialization.py tests/test_interpretation.py tests/test_interpretation_persistence.py tests/test_ai_provider.py tests/test_approval.py tests/test_worker.py`.
- The 14 fixed-planning regressions cover real P1 SAT and independent validation, real D0 UNSAT with immutable values, exact slot boundaries, full participant reservations, missing hard-rule coverage, unsupported authority, all 17 live task/review policies and 22 gates, bounded author/revise behavior, private scenario-source audiences and exact read-only historical candidate projection.
- Ruff passed on the owned planning, interpretation, provider, approval, durable handler, Northstar request/graph modules, both planning test scripts and the scenario operator script.
- Strict mypy passed on those **42 source/test/script files**, using the repository configuration and `--follow-imports=silent` for independently owned imports.
- Actual disposable PostgreSQL run `2577d71b-f6ed-480e-92b2-5ba547cb1c1d` completed the normal request → interpretation → snapshot → fixed D0/P1 checks → 18 exact plan/disclosure approvals → 17 committed tasks and task-specific briefs. It then completed all 17 tasks through actual owner commands, exact artifact submissions, named reviews/self-certifications, R1 readiness approval and R2 final approval. The project became `completed`; 18 capacity blocks remained (reviews were not double-counted), 52 exact gate-evidence uses were recorded, and clock movement alone never changed task status. This initial run used the operator connection with transaction-local restricted runtime roles; the reusable smoke now provisions separate non-owner NOINHERIT API/worker logins and explicitly verifies that neither can assume the other's role.
- A **fresh full reproduction passed** on run `39d1c788-f901-44ed-b21a-17c888ffebc2`, visitor `1f744c61-3800-405b-91fb-9c8ba9543918`, request `b7dafe63-77cb-42d0-bbfe-67c3f64c74b5`, plan `21b3dbbd-1117-56be-8458-30026e6aba61`, using those separate runtime logins throughout. Results again were D0 `VIOLATIONS_FOUND`, P1 `CHECKED` plus independent validation, 18 exact approvals, 17 task-specific briefs and committed tasks, all 17 tasks actually accepted and the project completed through R2, 18 capacity blocks and 52 exact gate-evidence uses. This reproduction included the corrected R1 audit-event provenance; the explicit gate records its real prior task state, not a fabricated `assigned` transition.

`services/backend/tests/alto_planning_smoke.py` is an explicit opt-in integration script, not an automatically collected unit test. It accepts only `localhost`/`127.0.0.1:55439`, requires the disposable scenario to have been provisioned, creates its own synthetic Auth visitor, and refuses to begin while another visitor has pending jobs. Set `ALTO_DISPOSABLE_DB_URL` to that disposable operator DSN and `PYTHONPATH` to the backend `src` directory, then run `.venv\Scripts\python.exe -u tests/alto_planning_smoke.py`. Operator access is used only for synthetic fixture/login provisioning and read-only owner lookup; production commands use the separate runtime logins. `--resume-run <uuid>` resumes execution only for a run whose synthetic visitor matches this script's explicit email namespace. No accepted statuses are manufactured with fixture SQL.

NOT RUN by this planning subtask: a real Gemini request using a visitor's credential, hosted migration deployment, installed-client microphone permission/audio capture, or a production workload/performance benchmark. Fake structured gateways test deterministic bounded orchestration; they are not represented as live model results. The real Z3 checks and independent validator were exercised both in tests and through the disposable database pipeline. Full-repository, desktop/native and database-suite results are recorded by their owning workstreams in the delivery runbook.
