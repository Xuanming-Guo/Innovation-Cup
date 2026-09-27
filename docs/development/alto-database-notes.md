# ALTO database and Storage implementation notes

Status: implemented and locally verified on `feat/alto-product`. Final-phase verification ran only after the user's requested implementation phase. The initial local-only evidence below is historical: the founder subsequently applied the original ALTO migrations, and the agent applied follow-ups `20260927034000` and `20260927035000` with separate explicit approvals. The linked project is up to date through 35000. No branch was pushed. See the dated follow-ups and [journal](alto-implementation-journal.md) for current deployment evidence.

## Migration map and compatibility

The 17 pre-ALTO SQL files are unchanged. New migrations expand the existing `app` schema, which remains absent from the Supabase Data API schema list. The application keeps its existing non-owner, non-BYPASSRLS API and worker roles. `app_private.migration_contract` is registered in each migration; the root manifest records each new file's final SHA-256.

| New version | Scope |
|---|---|
| `20260927010000` | Synthetic employee identity without fake Auth users; fixed-company onboarding; visitor-owned demo runs, memberships, actor sessions and UI preferences. |
| `20260927011000` | Run and generated scope columns on existing mutable descendants, restrictive RLS, immutable-scope write fences, same-scope parent FKs, per-scope exclusive capacity and workload. |
| `20260927012000` | Operating groups, controlled skills, working rules, fixture/live connection metadata, safe calendar versions, graph dependencies/gates, private work drafts, feedback/consent versions, assistant threads and API command receipts. |
| `20260927013000` | Model checkpoints, immutable AI/replay proposals, fixed verification and independent validation, exact successful promotion into existing plans/placements/blocks. No fabricated optimizer result. |
| `20260927014000` | Explicit synthetic actor task/approval authority, scoped approval/commit revision, retained legacy transactional commit semantics, audit actor provenance and execution gates. |
| `20260927015000` | Scoped lease metadata, current authority/token fences, bounded `plan.propose` workflow, private assistant/preference/voice queue commands. Existing queued legacy kinds remain supported. |
| `20260927016000` | Visitor-owned Vault profiles, immutable credential versions and explicit per-live-run binding; no implicit fallback to another visitor or company credentials. |
| `20260927017000` | Extended authenticated Storage tickets, strict run paths/context/purpose/MIME/size contracts, private image artifacts and expiring voice uploads. |
| `20260927018000` | Operator-controlled scenario manifests, atomic deterministic run initialisation, non-destructive fork, audited clock changes and archive fencing. |
| `20260927019000` | Exact synthetic preference audiences, private assistant commands, lease-bound model/provider metadata and authenticated fixed-demo host discovery before onboarding. |
| `20260927020000` | Version-locked unaccepted-work changes, exact task/reviewer/gate materialisation and immutable task versions. Submitted/accepted/cancelled work requires explicit supersession and fails closed. |
| `20260927021000` | Single-file worker Storage capability, least-privileged private operation policies and private voice transcript records. |
| `20260927022000` | Deletion-only expired-audio cleanup leases and exact worker job-context restoration. |
| `20260927023000` | Reserved review nodes, recorded exact gate evidence and explicit Northstar R1/R2 approvals, including atomic S4/final milestone acceptance. |
| `20260927024000` | Recorded approver authority survives a viewer actor switch; per-task brief projections and synthetic display names. |
| `20260927025000` | ID-only exact-consent notifications, revoked-actor reconciliation and owner-authorised participant/viewer joins. |
| `20260927026000` | Optimistic connection revocation receipts, revoked-calendar projection denial and physical expiry of private transcripts. |
| `20260927027000` | Worker-only, current-lease-bound access to the run's exact pinned immutable scenario manifest for typed source-digest-bound admission. |
| `20260927028000` | Lease-bound worker identity, exact current preference audience and thread-scoped source predicates; capacity/calendar/connection changes invalidate the scoped planning revision. |
| `20260927029000` | Self-only optimistic profile skill-label overrides, isolated by run; canonical employee identity and verified eligibility remain unchanged. |
| `20260927030000` | Exact active consent recipients may read the corresponding shared-version decision/timestamp without gaining owner mutation rights. |
| `20260927031000` | Legacy commit/brief notification and delivery conflict targets match scoped idempotency keys; ordinary task grants and exact pending-review authority are preserved. |
| `20260927032000` | Row-local private preference/thread ownership permits valid INSERT RETURNING without relaxing exact audience or actor/scope privacy. |
| `20260927033000` | Complete cancellation audit metadata, idempotent assistant cancellation, archive lease-attempt closure and retained original cancellation authority. |

Before applying: compare linked migration history with the immutable repository prefix. If history/catalog differs, stop and reconcile; do not reset the project or repair history to suppress drift. New migrations retain ordinary records with `demo_run_id IS NULL`; `scope_id = COALESCE(demo_run_id, company_id)`. Historical IDs, content and digests are not recomputed. Expanded unique/FK/exclusion indexes may acquire locks and must be sized against the hosted data before application.

The scope installer uses an explicit legacy table allowlist. Its catalog-based FK step adds a matching scoped FK for every relationship whose two endpoints are scoped. It does not delete original FKs or create a second domain model. The commit migration deliberately asserts its narrowly targeted compatibility substitutions; if a newer function definition no longer matches, application stops for review.

## Request and worker context

Every runtime transaction keeps the verified real Auth identity in `app.actor_id`; company context remains `app.company_id` and purpose remains `app.purpose`.

Optional context:

```text
app.demo_run_id
app.demo_actor_session_id
app.job_id             # actual leased worker job
app.lease_token        # exact unexpired lease token
```

`app.employee_id_for_actor(company,user)` remains the real identity resolver. `app.effective_employee_id(company,user)` resolves an independently authorised synthetic actor only when an explicit valid session is selected. Expired/revoked/wrong-owner sessions fail closed. Selecting a synthetic actor never rewrites Auth identity, grants company administration or authorises another run.

The API calls `app.resolve_demo_context(company,run,session)` to obtain permitted simulated identity and UI role. The DB independently rechecks scope and authority. New worker ledger writes require `app.assert_alto_job_lease(company,job,token)` using the transaction-bound token; losing authority or lease prevents late writes. The lease response includes run/session/simulated employee identifiers for handler context construction.

`app.current_alto_lease_worker()` returns only the current valid lease's worker UUID, avoiding broad queue SELECT privileges. `app.preference_is_shared_to_viewer(company,version)` requires a valid lease and exact current confirmed version, active audience membership, synthetic audience identity where applicable, and unrevoked consent; an owner's ability to read private wording does not classify it as shared. `app.get_demo_scenario_manifest(company,run)` (or its no-argument current-context form) exposes only the leased run's pinned immutable operator manifest, including its hex digest, to the live admission worker.

`app.source_in_assistant_context(company,thread,source)` requires that exact thread's active assistant lease, thread ownership, current source permission and readable project/task context. It discloses only a source-to-context membership boolean, not the manager-only planning ledger. Person contexts never receive unrelated source bodies, and revoked mapped provider connections/grants are excluded.

Planning resource profile, calendar version and connection/grant changes advance that row's ordinary-company or demo-run planning revision. This makes a previously captured snapshot stale at approval/commit without affecting another run. Committed schedule writes retain the existing commit procedure's single atomic revision increment.

## API command contracts

Signatures below use PostgreSQL argument order; IDs are UUIDs and digests are 32-byte `bytea` values unless stated otherwise.

- `bootstrap_demo_membership(display_name text, requested_role text, idempotency_key text) -> jsonb`: chooses the single operator-enabled demo company, permits only configured member/manager bootstrap roles, never promotes an existing membership or creates company administrators.
- `fork_demo_run(company, mode text, parent_run nullable, idempotency_key text) -> uuid`: creates and initialises an owned run atomically from the operator template. It does not clone private visitor state.
- `select_demo_actor(company, run, employee) -> uuid` and `end_demo_actor_session(company,session) -> void`: explicit, owner-bound, expiring sessions.
- `initialise_demo_run(company,run) -> jsonb`: idempotent fixture materialisation, returning run/project IDs and replay state.
- `advance_demo_clock(company,run,expected_clock_version bigint,new_clock_at timestamptz,key text) -> jsonb`: owner/operator only. It changes presentation time, not work acceptance.
- `archive_demo_run(company,run,expected_row_version bigint) -> void`: cancels/fences pending work, revokes sessions and archives the run. It deletes no company work, directory entries or provider profiles.
- `promote_verified_ai_proposal(company,proposal,verification,validation) -> uuid`: worker-only; the candidate, snapshot, full trusted required-rule coverage and independent validator must agree before promotion. It creates normal approval requirements.
- `enqueue_alto_job(company,kind text,aggregate,payload jsonb,key text,digest bytea,correlation) -> uuid`: verifies private aggregate authority for supported assistant/preference/voice jobs.
- `enqueue_alto_assistant(company,thread,message,key text) -> uuid`; `cancel_alto_assistant(company,thread,key text) -> void`: actual owner plus exact selected actor context.
- `revoke_alto_connection(company,connection,expected_version bigint) -> jsonb`: only its owner, with an optimistic version match; returns connection identity, revoked status and resulting version.
- `approve_alto_gate(company,task,expected_version bigint,required_submission nullable,required_submission_digest nullable,key text,correlation) -> jsonb`: explicit named Maya approval in the Northstar run. R1 requires recorded readiness prerequisites; R2 binds S4's exact submitted version/digest plus accepted Q3, executes its normal review and completes the final milestone atomically. A clock advance cannot call this implicitly.
- `finalize_alto_upload(company,file,observed_size bigint) -> boolean`: owner/context/intent-expiry checked; only transitions to quarantine. The API must observe the stored object rather than accepting a client clean claim.
- `update_alto_profile_skills(company,employee,expected_version bigint,skills jsonb) -> jsonb`: edits only the effective employee's current-scope declared skill labels (at most 20 nonempty strings of 120 characters). First edit requires the canonical employee version; subsequent edits require the override's version. Returns employee ID, new `row_version` and `declared_skills`. Directory projections supplement, never replace or upgrade, verified qualifications/accepted evidence. No canonical synthetic profile, planning capability or eligibility is changed, so this presentation-only edit does not advance planning revision.

UI preferences, private drafts, employee-authored preference versions/decisions, assistant user messages and minimal command receipts have bounded direct table grants with self/scoped RLS. API handlers must still validate shapes, permitted state transitions and expected versions. No generic SQL/JSON mutation dispatcher is exposed.

Assistant cancellation records all five fields required by the existing cancellation audit constraint. Its command receipt makes a repeated key a no-op, including after newer work was queued; it cannot cancel that newer work accidentally. Queued jobs terminate immediately; leased jobs are fenced immediately and retain their lease until reconciliation. Run archive closes outstanding lease attempts, cancels pending jobs with complete audit metadata, preserves an existing cancellation's original authority, revokes actor sessions and restores the caller's previous run context.

## Privacy and access matrix

| Domain | API access | Worker access |
|---|---|---|
| Ordinary company records | Existing membership/domain authority, ordinary scope only. | Existing domain authority with current context; narrow global queue functions. |
| Demo run records | Active run membership plus selected actor's domain authority. | Exact run, actor/session and leased job. |
| Synthetic directory/functions | Company-owned immutable fixture identity; no credentials or private feedback. | Same canonical resource IDs, run-specific capacity projections. |
| Submission drafts/feedback | Owner/effective employee only; assigned-owner constraint for work drafts. | No blanket private-feedback SELECT. |
| Preference wording | Owner or explicitly shared exact version/audience; demo audience also names synthetic manager. | Only permission-filtered projection; suggestion output has no share authority. |
| Threads/messages | Owner membership **and** the same selected synthetic actor; context rights checked every read. | Same private thread context and job lease. |
| Calendar | Busy-only records have null titles; owner-only records do not become manager-readable. | Reduced capacity projections for planning. |
| Provider profiles | Masked owner metadata and narrow configuration/binding/revocation commands; no Vault UUIDs. | Bound secret resolution only under a live lease. |
| Files | Clean, current, unexpired owner/source/task access; voice owner/thread only. | Narrow leased validation/transcription path; no assumed successful scanner. |

Realtime carries the existing constant invalidation payload, not private preference wording or file content. Revoked consent is rechecked at read time; clients must refetch after invalidation.

## Provider contract

`configure_demo_ai_credential` accepts the same nine server-validated arguments as `configure_company_ai_credential` and returns only masked metadata plus profile/version identifiers. Rotation appends a new Vault secret/version; it does not mutate an in-flight run's secret.

`bind_demo_provider(company,run,version)` permits only a live run owner binding their own active version. A different version requires a new run rather than silent rebinding. `revoke_demo_provider_version(company,version)` prevents future resolution. `get_demo_provider_binding()` distinguishes the bound and latest version IDs. Model checkpoints record the exact bound version.

The existing `resolve_company_ai_credential()` name is retained as a compatibility gateway: ordinary scope calls the preserved company resolver; demo scope requires a leased job and resolves only that run's explicit active binding. Missing/revoked binding is an error, not an environment/company fallback.

## Storage and Edge Function

`storage-ticket` remains the user-facing authenticated Edge Function. A second bounded function, `worker-storage`, was required during implementation so actual quarantine scanning/transcription can access exactly one leased file without giving the Python worker a global Storage service key. This is a deliberate implementation change from the initial one-function baseline, not a new orchestration service. `app` remains unexposed.

`worker-storage` uses a database-verified, unguessable single-file job/cleanup lease capability instead of a user JWT. Its server-side service role may call only the explicitly granted public-schema authorization RPCs; the RPCs return server-generated bucket/path metadata after checking the exact job, file, active lease, scope and actor. The endpoint accepts no arbitrary path/bucket. Scan retries may read the exact pre-existing `validated.ext` object to compare hashes, never overwrite it.

Upload adds optional `demoRunId`, `demoActorSessionId`, `taskId` and `threadId`; download supplies the current run/actor selector and a file ID. The DB derives the actual stored context. Legacy nine-argument SQL calls remain supported through the strengthened implementation.

- Documents: PDF/DOCX/CSV/TXT, maximum 25 MiB.
- Work images: PNG/JPEG, maximum 10 MiB. SVG/executable/arbitrary extensions remain rejected.
- Voice: `voice_audio`, supported WebM/MP4/WAV MIME, maximum 8 MiB and 60 seconds after actual byte/duration validation; private thread required, maximum one-hour file expiry.
- Ordinary keys remain `<company>/<file>/payload.ext`; run keys are `<company>/runs/<run>/<file>/payload.ext`. File names/paths cannot be supplied as arbitrary storage locations and uploads cannot overwrite.
- Application upload intent remains 10 minutes. Download URL default remains 60 seconds, bounded 15–300. Provider upload-token lifetime is separate from the application deadline.

The bucket records **and** local `config.toml` are updated together. Hosted SQL and Edge deployment remain separate operator actions. No new OAuth/webhook function is introduced without an actual connector implementation.

Expiry checks deny future access but are not evidence of physical deletion. The worker's periodic `claim_expired_audio_cleanup(worker,limit)` physically purges expired transcript rows and leases only expired audio objects for deletion. `authorize_alto_audio_cleanup(file,token)` returns the two exact quarantine/private paths; `complete_alto_audio_cleanup(file,token)` records deletion only after the Edge handler successfully removes both. A crashed attempt expires after 60 seconds and can retry even when the run was archived or the original actor session expired. Cleanup capabilities cannot read or upload bytes. Worker byte validation, quarantine-to-private promotion, cleanup retries and hosted Storage credentials still require end-to-end integration verification. Never claim a file clean based only on MIME, extension or upload success.

## Scenario provisioning and reset

`demo_scenario_manifests` is operator-only and versioned by company/scenario/version. The payload contains deterministic synthetic project, sources, connection/calendar fixtures, groups, skills, working rules and resource availability. It contains neither real user data nor provider material. `demo_record_id(run,key)` derives RFC 4122 UUIDv3 identifiers; canonical keys include `project:launch`, `source:<key>`, `source-version:<key>`, `excerpt:<key>`, `connection:<provider>` and `calendar:<key>`.

Source items may have `audience_employee_ids`; if present, only those explicit employees receive grants. Absence means an intentionally company-readable synthetic source. The fixture builder must set classification and source audiences deliberately.

Initialisation creates no accepted work and no manufactured checked plan. Authored replay/check cases still use the fixed verifier and ordinary approval/submission/review boundaries. Reset is archive plus a new fork. The pre-existing destructive company-reset chain is not exposed to visitors.

## Final integration verification — 27 September 2026

The final repository contains **41 migrations: 17 unchanged legacy files and 24 additive ALTO files**. Verification used disposable PostgreSQL 17 containers based on `public.ecr.aws/supabase/postgres:17.6.1.167`, with the repository's `supabase/` directory mounted read-only. Existing local Supabase containers were not reset or mutated. Where the raw database image lacked the running platform's Storage/Realtime schema or current Auth helper definitions, schema-only definitions were read from the existing local platform and installed only in the disposable databases. No existing application rows or Auth users were copied.

| Verification | Actual result |
|---|---|
| Ordered SQL replay and populated legacy upgrade | All 41 migration registrations present. The original 17-file baseline ran the legacy committed-plan fixture successfully before the 24-file suffix was applied. |
| Populated upgrade preservation | `legacy_history_preserved = t`: captured task IDs/content/status/schedule/owner/version, snapshot and proposal digests, exact capacity blocks, approval/commit counts, queued job IDs/kinds/aggregates/states and company planning revision remained identical after all 41 files. |
| Entire SQL regression directory | **14 files, 308 passing pgTAP assertions**: 255 existing assertions plus 53 ALTO assertions. Each normal regression test rolls back its fixtures. |
| Immutable migration contract | `Supabase migration contract passed (41 immutable files).` No diff in the original `20260926*.sql` migration files. |
| Pinned Deno 2.9.6 | Formatting check, lint and frozen-lock type checks passed for both `storage-ticket` and `worker-storage`; **6 parser tests passed, 0 failed**. |

The 53 new SQL assertions exercise real non-owner API/worker roles, effective actor demotion, exact synthetic consent audiences/revocation, private INSERT RETURNING, cross-run/thread/profile/source-parent isolation, profile optimistic concurrency, pinned manifest/lease checks, thread/source projection, fixed worker Storage paths, expired audio denial, deletion-only retention capabilities after actor revocation, cancellation replay and complete audit metadata, archive version checks and other-run preservation. Storage assertions validate authorization and database lifecycle recording; they do **not** claim real Storage bytes were scanned or deleted.

Real integration also exercised the production planning and execution path in the shared disposable database: D0 failed the fixed check, P1 passed both fixed verification and independent validation, 18 separate approvals authorised 17 tasks/briefs, and all 17 tasks reached acceptance through actual submissions/reviews/gates, ending in R2 project completion. The retained result was 18 capacity blocks and 52 exact gate evidence uses. This was reproduced on a fresh run with separate non-owner NOINHERIT logins. The coordinating agent owns the API/worker HTTP evidence and overall release report; this document does not substitute a schema test for those checks.

Commands actually run (PowerShell, from the repository root; `docker exec` targeted only the disposable containers below):

```powershell
services/backend/.venv/Scripts/python.exe supabase/scripts/verify_migrations.py
git diff --name-only -- supabase/migrations/20260926*.sql

# Each ordered file was applied with this transaction/error-stop boundary.
docker exec alto-db-upgrade-20260927 psql -U supabase_admin -d postgres -v ON_ERROR_STOP=1 -1 -f /workspace/supabase/migrations/<ordered-file>.sql

# All 14 files were run with this boundary; the runner additionally rejected
# nonzero exit codes, "not ok", "Bail out!" and pgTAP failure summaries.
docker exec alto-db-verification-20260926 psql -X -U supabase_admin -d postgres -v ON_ERROR_STOP=1 -At -f /workspace/supabase/tests/database/<test-file>.test.sql

npm.cmd exec --yes --package=deno@2.9.6 -- deno fmt --check supabase/functions
npm.cmd exec --yes --package=deno@2.9.6 -- deno lint --config supabase/functions/deno.json supabase/functions
npm.cmd exec --yes --package=deno@2.9.6 -- deno check --config supabase/functions/deno.json --lock=supabase/deno.lock --frozen supabase/functions/storage-ticket/index.ts supabase/functions/worker-storage/index.ts
npm.cmd exec --yes --package=deno@2.9.6 -- deno test --config supabase/functions/deno.json --lock=supabase/deno.lock --frozen --allow-env supabase/functions/tests
```

Test container identities:

- `alto-db-verification-20260926`: network-isolated SQL regression database.
- `alto-db-upgrade-20260927`: network-isolated populated-upgrade database; captured history is retained in `public.alto_upgrade_baseline`.
- `alto-db-integration-20260926`: shared integration fixtures; only `127.0.0.1:55439` is published. Do not reset it while another agent is using its runs.

pgTAP/Deno output was captured in the execution transcript, not written to a persistent raw-log file. The table above is the repository evidence summary; PostgreSQL service logs remain available through `docker logs <exact-container-name>`. Verification and upgrade containers may be stopped without deleting their data after the final checks.

Final-phase findings were corrected and retested: scoped legacy outbox conflict targets, ordinary task-grant compatibility, exact pending-review authority, ordinary versus demo planning routing, operator workload scope, durable completion replay/renewal semantics, INSERT RETURNING visibility, truthful R1 event prior status, exact recipient consent-row visibility, and cancellation audit integrity. Existing migration files were never rewritten.

**NOT RUN in this database work:** applying SQL or deploying Edge functions to hosted Supabase; spending through live BYOK; physical hosted Storage scan/promotion/deletion; microphone/device capture or native installed-client integration. These need the corresponding explicitly authorised environment, credentials and hardware. A passing local capability test is not evidence of a deployed connector, hosted object deletion or signed native release.

## Lease-renewal follow-up (27 September 2026)

`20260927034000_alto_job_lease_renewal_result.sql` fixes a misleading return value in
`app.renew_durable_job_lease`: ordinary jobs have no outbox row, so returning `FOUND`
after the optional outbox update falsely reported lease loss. The new function captures
the actual job-update result first. The migration uses guarded replacements in the current
function definition, refusing unexpected shapes and retaining current owner/token/expiry/
run/actor checks, grants, ownership, security-definer setting and search path.

Only a new manifest entry was appended; the previous 41 hashes are unchanged. At this checkpoint the
manifest passes with 42 files. `14_alto_lease_renewal.test.sql` contributes 15 focused pgTAP
assertions. The actual migration and assertions passed in a rollback-only transaction in
the isolated verification database; function security attributes were compared unchanged.
The transaction left persistent tip33000 and zero test jobs, and the container was stopped.
This did not rerun the historical 308 assertions or apply anything to hosted Supabase.

The founder subsequently approved hosted application of only tip34000. The linked project
matched the requested project, migration history and dry run showed only that version
pending, application succeeded, and a runtime function-definition read confirmed the fix.
The [runbook](alto-runbook.md#apply-the-planning-role-and-cached-navigation-follow-up)
contains commands. Do not reset, reseed, modify applied SQL or repair history speculatively.

## Generated model-scope follow-up (27 September 2026)

`20260927035000_alto_model_run_generated_scope.sql` corrects the `model_run_transition`
BEFORE UPDATE trigger. PostgreSQL computes the stored generated `scope_id` after BEFORE
triggers, so comparing its NEW and OLD values rejected otherwise legal checkpoints. The
additive correction excludes only that generated column; its company/run inputs, model,
provider and input digest remain immutable. Terminal records stay closed. Grants, worker
lease fencing, function ownership and security settings are not broadened.

The migration checks the actual generated expression and current trigger definition before
changing either comparison. Unexpected catalog drift stops application for review. The
manifest now contains 43 files with the prior 42 entries unchanged. The new rollback-only
test `15_alto_model_run_transition.test.sql` exercises both the old failure and corrected
behavior, plus real `app.model_runs` checkpoints under the non-owner worker role.

Final verification passed **23 pgTAP assertions plus one function owner/ACL/settings
comparison**. Both pending local migrations were applied inside the same rolled-back
transaction for the test. The disposable database retained tip33000, with zero synthetic
model/Auth rows afterward, and was returned to its original stopped state. An initial
harness run correctly denied pgTAP access under the worker; the final harness executes
business statements as that role and checks temporary results after RESET ROLE, without
granting any new application privileges. The 43-file manifest check passed.

The founder separately approved hosted application. Linked history showed the preceding
42 versions present and dry run listed only 35000. Application succeeded on September 27;
a read-only runtime catalog comparison confirmed the exact expected definition, both
corrected comparison lists, the terminal guard and unchanged owner/ACL/search path/security
attributes. Final dry run reported no pending migrations, seeds or roles. This correction
does not alter historical model rows or authorize repeating an ambiguous provider call.

## Exact proposal assistant binding (27 September 2026)

`20260927036000_alto_exact_proposal_assistant.sql` adds an optional immutable-by-grant
`proposal_id` to project assistant threads. Existing conversations remain null-bound.
The database accepts a proposal binding only when the current actor has real manager or
current demo-planning authority and the exact proposal, snapshot and planning request all
belong to the selected project and current company/run scope. Thread reads and message/job
access reuse that check, so a cross-project binding fails and loss of planning authority
hides the conversation immediately. The API role has no column update grant, preventing a
saved conversation from being rebound to another proposal.

The manifest contained 44 immutable files at this checkpoint. The migration was applied after local tips
34000 and 35000 only inside one rollback-only transaction in the network-isolated
verification database. `16_alto_exact_proposal_assistant.test.sql` passed 8 pgTAP
assertions covering exact binding, cross-project denial, role loss, nullable compatibility
and absence of a rebinding grant. The container was returned to its original stopped state.
This migration was subsequently applied to hosted Supabase as recorded in the implementation
journal. No proposal, assistant message or provider call was created by that schema deployment.

## Confirmed assistant planning actions (27 September 2026)

`20260927037000_alto_confirmed_assistant_plan_actions.sql` adds immutable-target action previews
for project-assistant planning commands. Project, proposal and optional plan foreign keys prevent
free-floating actions. The worker can insert only a completed assistant message's exact owned
project/proposal binding; the API can update only decision lifecycle fields, and only while the
current actor retains manager planning authority. The worker cannot approve its own action and the
API cannot rewrite the staged description or payload.

This additive migration is registered in the immutable manifest and was included in the 18-assertion
rollback-only database verification described below. It was subsequently applied to hosted
Supabase together with migration 38000 after an exact two-migration dry run.

## Bounded Live fixed-plan continuation (27 September 2026)

`20260927038000_alto_bounded_live_plan_revision.sql` changes the proposal version check from a
maximum of three to a maximum of five. It replaces `app.retry_durable_planning_job` without
broadening its caller: only `coordination_api` retains execute permission. Existing manager,
company, membership, idempotency, digest, terminal-state and attempt fences remain. A
`plan.propose` retry additionally requires `last_error_code = 'fixed_plan_not_verified'` and fewer
than five AI-authored proposals for the exact snapshot. Other failed plan-authoring states cannot
use this path.

The migration registers version 38000 in `app_private.migration_contract`; the repository manifest
now contains 46 immutable files. Migrations 34000–38000 plus
`16_alto_exact_proposal_assistant.test.sql` passed 18 pgTAP assertions in one disposable
rollback-only transaction. The post-transaction catalog again showed the original
`version <= 3` constraint and no 34000–38000 contract rows, confirming that the verification did
not alter the disposable baseline. Migration 38000 was subsequently applied to hosted Supabase
together with 37000. Remote history records both versions and the final linked dry run is empty;
no seed, role, reset or application-row mutation accompanied the schema deployment.
