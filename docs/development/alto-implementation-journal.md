# ALTO implementation journal

Status: **LOCAL IMPLEMENTATION VERIFIED — external deployment/installed acceptance gates remain**.

## Scope and delivery controls

The 26 September 2026 implementation request adopts
[`alto_product_master_prompt.md`](../alto_product_master_prompt.md) v1.2. The pasted
attachment was compared with the repository prompt; it has no substantive difference.
The direct implementation request takes precedence: work on one local branch,
`feat/alto-product`; do not push until complete; defer all test execution and new migration
tests until final integration. No hosted migration, production reset, credential rotation,
external provider write, PR or release is authorised by this local implementation work.

The existing modified master prompt and untracked storyboard directories are preserved.
The root `simulation/` tree is excluded from all work.

## Ownership

| Workstream | Owned paths | Integration responsibility |
|---|---|---|
| Database and Storage | New `supabase/migrations`, manifest, config and functions | Compatible existing-schema changes, RLS, narrow procedures and private files |
| Desktop | `apps/desktop/src`, public assets, index | Shared storyboard-faithful UI; typed API contracts; no fake connected data |
| AI planning | Backend planning, interpretation and provider modules | Complete authored candidates, fixed checks and independent validation |
| Root integration | API/auth/database context, durable jobs, scenario provisioning, native integration and shared documentation | Contracts, boundaries, complete workflow and final verification |

Agents share this branch but do not edit each other's owned paths. Contract changes are
communicated before integration. Each workstream maintains its own implementation notes;
this journal records the integrated result, not an assumption that planned work exists.

## Decisions and progress

- Preserve internal `coordination` identifiers, historical migrations and original evidence.
  Active user-facing branding becomes ALTO.
- Preserve the signed-in Auth user as the actual actor. Add explicit optional run/session
  context rather than impersonating fictional Auth users.
- Transaction-local run and actor-session settings are reset on every company transaction,
  including ordinary requests, to prevent pooled-context leakage.
- Database changes are additive and hosted application remains founder-managed.
- Tests began only after the implementation phase, as requested. The final verification
  phase now includes actual isolated Postgres replay and non-owner HTTP/worker workflows.

### Integrated implementation before final verification

- New additive migration files preserve the original seventeen. Scope-aware
  composite integrity, RLS, real/simulated actor audit, explicit consent, per-run Vault
  bindings and lease-fenced model/worker writes are implemented; hosted state is unchanged.
- API context now carries company/run/actor session through every scoped transaction.
  Workspace, graph, calendar, People, tasks, private drafts, consent, feedback, assistant,
  voice, scenario and source-excerpt routes are connected to Postgres projections.
- Fixed-candidate planning and independent checking use actual immutable lineage;
  authored D0/P1 modes are labelled and use the same checker as live proposals.
  Generic legacy solver paths remain historical compatibility, not ALTO plan authorship.
- Actual execution includes one scheduled review per exact decision, self-certification
  only where admitted, gate provenance, and explicit readiness/final-milestone commands.
- The scenario operator script creates one deterministic 50-person directory/template;
  no fake Auth employees, accepted work, provider successes or current task completion.
- Live Northstar admission reads an operator-authored, version-bound authority manifest,
  preserving all explicit execution gates, review roles and active participants. Live
  candidate times are not copied from replay; current capacity and revoked connectors
  affect current scope revision. Unsupported authority stops instead of weakening checks.
- Self-edited skill labels are bounded run-scoped declarations. They neither mutate the
  canonical synthetic directory nor become verified qualifications or hard eligibility.
- The assistant is bounded and read-only. Replies cite re-authorised exact source versions.
  Raw employee feedback remains private; manager notifications carry an ID, not private text.
- ClamAV/byte validation and private object promotion replace the fail-closed scanner stub.
  A second narrow Edge Function grants only job-bound object operations. Successful voice
  transcription and expiry cleanup remove both registered audio objects; no service-role
  key is introduced into Python or desktop configuration.
- Native Rust implements a separate always-on-top overlay and opt-in global shortcut.
  OS microphone permission and installed-app behavior remain acceptance-test prerequisites.
- Run/setup and Northstar walkthrough are documented in [`alto-runbook.md`](alto-runbook.md).

### Ownership refinements

The planning agent additionally owns approval read adaptation, durable handler composition,
`workspace/northstar.py`, `workspace/graph_read.py` and provider endpoints. Root owns other
workspace modules, worker file/assistant jobs, the new `worker-storage` function, scenario
operator script, native integration and host bundle. This avoids simultaneous edits to the
same modules. Database/desktop/planning notes contain detailed subsystem contracts.

## Final evidence

Local implementation and available final verification completed on 27 September 2026.
Tests and migration regressions were written/run only after the implementation phase,
as requested. There are no commits, pushes, PRs, hosted migrations or Edge deployments
from this implementation task. All work remains together on `feat/alto-product`.

| Boundary | Actual result |
|---|---|
| Backend | 132 pytest tests passed; one upstream Starlette/httpx deprecation warning. Ruff clean; strict mypy clean across 95 source/test files. |
| Desktop | TypeScript and zero-warning ESLint passed; 38 tests across 9 files passed; production build passed. Vite has a non-failing >500 kB chunk advisory. |
| Database | 41 ordered migration hashes passed: original 17 unchanged plus 24 additive ALTO migrations. All 14 pgTAP suites passed, 308 assertions (255 legacy + 53 ALTO). Populated pre-ALTO upgrade preserved captured historical records/digests exactly. |
| Edge Functions | Pinned Deno 2.9.6 formatting/lint and frozen-lock type checks passed for both entrypoints; all 6 request-parser tests passed. |
| Real API/worker | `tests/alto_workspace_smoke.py` passed 42 HTTP/DB assertions with distinct NOINHERIT, non-owner API and worker logins. Includes onboarding, actor isolation, Home/projects/graph/calendar/50-person directory, private feedback, exact Maya/not-Jordan consent, revocation, private threads, actual leased replay answer, skill editing and actor-session end/denial. |
| Complete scenario | A fresh separate-login run passed real D0 failure, parent-linked P1 fixed verification and independent validation, 18 separate approvals, 17 task-specific briefs/committed tasks, all 17 actual accepted task workflows and R2 project completion. It retained 18 capacity blocks and 52 exact gate-evidence uses. Scenario time alone never executed work. |
| Visuals | All 20 source images mapped; 19 browser-fixture states captured and reviewed. Captures are explicitly labelled, not live data or pixel-difference/native acceptance evidence. M15 has no fabricated recording capture. |
| Native | Windows Rust compile and direct `rustfmt --edition 2021 --check` passed. Final unsigned x64 NSIS installer built successfully. The `cargo-fmt` wrapper was blocked by OS application control; direct installed rustfmt worked. |
| Host/media | Backend Linux container built as `alto-backend:local-verification`; actual in-container ffprobe accepted synthetic WAV, streaming WebM and MP4 and rejected 61-second audio. Node host/public-configuration regression tests: 14 passed. |
| Repository | Repository contract, migration-manifest and scoped diff-whitespace checks passed. Root `simulation/` was excluded. |

The coordinating agent independently read the final disposable records: exactly
17 accepted work items, project `completed`, D0 `VIOLATIONS_FOUND` and P1 `CHECKED`.
The fresh run ID is `39d1c788-f901-44ed-b21a-17c888ffebc2`. Both smoke scripts
use synthetic test Auth identities; this is not hosted Auth signup/JWT issuance evidence.

### Windows validation artifact

- Path: `apps/desktop/src-tauri/target/release/bundle/nsis/ALTO_0.1.0_x64-setup.exe`
- Size: 1,266,692 bytes.
- SHA-256: `b45a6dc63bdd0e37da54fb1e9c02016f7127244405603029786ef2cf4f6c8390`
- Build: `npm run tauri --workspace @coordination/desktop -- build --bundles nsis`.
- This is unsigned local packaging evidence, not a configured distributable release.
  The public release gate reports `VITE_API_MODE is required for a native release`.
  Supply/validate the intended public build configuration and rebuild before distribution.
  Never bake database, provider or service-role credentials into it.
- No installer was launched, installed, signed, notarised or published. No new macOS
  artifacts were built on this Windows machine. Older CI binaries are historical only.

### Corrections found by real integration

The final phase caught and fixed scoped legacy outbox conflict targets, exact pending-review
authority, ordinary task access compatibility, durable completion replay, new-row visibility
under INSERT RETURNING RLS, a nonexistent plan-status column, dependency-injected settings
being bypassed, truthful R1 event provenance, current-consent row visibility, complete
cancellation audit metadata, and archive cancellation fencing. Each affected workflow was
rerun. Browser checks also caught stale private scope state, microphone cleanup and the
calendar's late-arriving scenario clock.

### Remaining external gates

- At the initial local handoff, hosted migrations and Edge deployment were outstanding.
  The founder subsequently supplied successful migration/deployment logs; see the
  operator-setup follow-up below for the updated, explicitly bounded evidence.
- Run real Supabase Auth and hosted Storage upload/ClamAV scan/promotion/download/deletion
  with that deployment. Database capabilities, scanner protocol/byte guards and real
  media decoding passed locally; physical hosted object operations were not exercised.
- Supply a visitor-owned Gemini/Vertex credential, verify/bind it and exercise live
  model authoring, private preference suggestions and voice transcription. Authored
  replay is not live-model evidence and incurs no provider spend.
- Verify the installed overlay, shortcut, OS microphone permission and hide/close cleanup
  with configured services on Windows and both target Mac architectures.
- Live Microsoft connectors, signing/notarisation, production load/performance benchmarks,
  customer outcomes and pixel-exact image equivalence are not claimed.

The test databases were separately created and never replaced the existing local Supabase.
All three test database containers are stopped, not deleted; their records are retained.
Their identities and restart boundaries are in the database notes. Build outputs and local
container images are local artifacts; no hosted resource or user database was removed.

Detailed evidence: [database notes](alto-database-notes.md),
[planning notes](alto-planning-notes.md), [desktop notes](alto-desktop-notes.md),
[all-screen coverage](../storyboard-coverage.md), and [setup/runbook](alto-runbook.md).

## Operator-setup follow-up: saved local connection configuration

The founder supplied CLI output showing all 24 ALTO migrations applied to project
`ljyrrilzulffykvzmubt`, all 41 local/remote migration versions aligned, and successful
deployments of `storage-ticket` and `worker-storage`. These are founder-provided deployment
records, not an independently executed agent deployment or an end-to-end hosted smoke test.
A subsequent SQL Editor screenshot shows Northstar active and explicitly synthetic,
no version-1 scenario manifest, and no other enabled demo workspace. Provisioning still
failed behind the old generic error message; the underlying cause is not yet established.

At the founder's request to avoid repeatedly typing the connection string:

- `supabase/scripts/alto_scenario.py` automatically loads ignored `supabase/.env`, using
  either an explicit operator DB URL or a raw password combined with the CLI-linked pooler
  metadata. Process environment overrides remain supported. No owner credentials are
  copied from runtime configuration or hardcoded in tracked Python.
- An empty ignored `supabase/.env` template was created without overwriting an existing
  file. The founder must fill its password privately; no real credential was supplied.
- Added an explicit read-only `--check-connection` command; provisioning still requires
  the fixed company confirmation. Direct CLI usage resolves backend imports automatically.
- Required explicit host/database/user, TLS and bounded connection timeout. Safe error
  diagnostics expose the exception class, SQLSTATE and constraint name when available,
  but omit DSNs, server error messages and row details.
- Updated the safe environment example and operating guide. No migrations, scenario
  contents, desktop code or backend business behavior changed. No hosted command was run,
  no commit was created, and nothing was pushed during this follow-up.

Verification: 18 focused configuration/security regression cases passed using only temporary
files and fake credentials, with database connections blocked. Ruff lint/format checks and
strict mypy for the script/test file passed. The repository contract checker, CLI help and
Git ignore verification passed; `supabase/.env` is ignored. The first pytest run reported
an unwritable cache directory, so the final run disabled only pytest's cache provider.
No database/migration test suite or live connection check was run for this tooling change.

## Desktop fetch / first-provider follow-up (2026-09-27)

The founder subsequently reported successful Northstar provisioning: 50 synthetic profiles,
36 rich and 14 background, without Auth-account creation or completed work. The reported
desktop failures were then traced to two backend read-path compatibility defects:

- Existing projects can have SQL NULL in the additive `goal_label` column. API logs showed
  that the string response model rejected those rows, returning 500 for Home/Projects.
  The outer unhandled-error response lacked browser CORS headers, surfacing as "Failed to
  fetch". The `Project` response model now normalizes only NULL to empty display text;
  non-NULL invalid values still fail validation and stored project rows remain unchanged.
- Before a visitor creates a provider profile, `app.get_demo_provider_binding()` returns
  SQL NULL inside a result row. The store now returns an empty metadata object for that
  case instead of calling `dict(None)`. Existing metadata, run-selection/tenant context
  and database-error handling are preserved.
- The credential textbox itself accepts JSON. Its disabled save button without a selected
  run is intentional. Use Simulation to create/select an owned Live run, validate your
  credential in Settings, then explicitly bind its exact version. This authority guard
  was not removed, and no service-account JSON was read or copied by the agent.

The provider-store fix and regression tests were delegated to an isolated subagent; the
coordinator reviewed the actual patch and implemented the project-model fix and route
regressions. Only these two backend files, two focused test files and this journal/runbook
were changed in this follow-up; all earlier work was preserved on `feat/alto-product`.

Verification:

- `python -m pytest -p no:cacheprovider tests/test_project_read_models.py
  tests/test_demo_provider_binding.py tests/test_ai_provider.py tests/test_api.py`:
  **32 passed**, including 12 new cases. The new route cases exercise the real workspace
  store/model with NULL rows and verify 200 responses plus native CORS headers for Home,
  the project list and project detail. Database calls in these unit tests are mocked.
- Ruff lint/format and strict mypy passed for the four affected Python files. The first
  run found an incorrect `create_app` invocation in the new test harness; it was corrected
  to the application's existing dependency-override pattern before the successful rerun.
  Pytest emitted the existing Starlette/httpx deprecation warning, not a test failure.
- Rebuilt/recreated only `coordination-engine-host-api-1` using Compose `--no-deps`;
  readiness returned healthy. Worker, scanner, tunnel and registrar were left running.
  Registrar logs still report the same online endpoint; post-rebuild desktop requests
  for session/workspace/demo-run listing returned 200.
- A live diagnostic inside the rebuilt API used its existing non-owner runtime connection
  and resolved the configured host actor's active membership. Existing data contained two
  NULL project labels: both projects and Home loaded successfully with string labels.
  The existing owned run resolved successfully and its unconfigured provider returned
  `{}`. No run or profile was created by the diagnostic. The first read-only-intent probe
  used startup options that the pooler did not retain; every query was still read-only.
  The final probe explicitly used psycopg read-only transactions and verified
  `transaction_read_only = on` before repeating the successful checks. This is real
  database/read-path evidence, not an installed-desktop or signed-JWT smoke test.
- `python scripts/check_repository.py` and the scoped `git diff --check` passed. No
  migration test suite or unrelated full regression suite was run for these two fixes.

No migration, reset, reseed, Edge deployment, credential validation/provider request,
commit or push was performed for these fixes. Live provider validation and the final
desktop click-through remain founder-controlled, separate from backend regression evidence.

## Everyday planning, roles, loading and cached tabs (2026-09-27)

Founder requests: unify the confusing Simulation/Plan review/chat journey, expose explicit
employee/manager demo-role selection, stop indefinite workspace loading, and restore loaded
tabs immediately while refreshing them in the background. Work stayed on `feat/alto-product`
with separate subagent ownership for session/cache, planning UX, gateway diagnostics and
final visual/regression review. Existing work was preserved; nothing was committed or pushed.

### Product and authority changes

- Home now distinguishes **Plan work** from read-only **Ask question**. A preview precedes
  request submission. Progress, clarifications, stopped processing and exact plan review
  appear in one restorable conversation. Plan review is the inbox for those requests.
- Exact task/assignee/time review links to the exact recorded plan's graph and rules.
  Approval, brief disclosure and final commitment remain distinct explicit actions.
  Current authority and revision checks still control assignment; failed/history proposals
  cannot substitute a newer candidate or become committable merely by opening the graph.
- Sidebar **Switch demo role** opens manager/employee cards. Users can retain an existing
  owned run and its bound credential. Named teammate choice and simulation clock/fork/reset
  are advanced options. Actor sessions remain audited server decisions; real account roles
  do not change. A failed actor-selection step cannot silently create a duplicate workspace.
- Demo provider settings explain that binding requires an owned **Live** run. Authored
  modes cannot send misleading binding requests; saved bindings link back to Home.
- Session/read deadlines are 20 seconds; command deadlines are 120 seconds with ambiguous
  outcome warnings. No automatic write retry is introduced. Stable primitive dependencies
  prevent fresh API-context objects from repeatedly cancelling the workspace read.
- The in-memory cache keys by real account, host, company, run, actor and path; credentials
  are not keys or persisted cache data. Recent tab content renders immediately while reads
  revalidate. Pending reads are shared. Five-minute retention and an 80-inactive-entry
  eviction target bound retained views. Writes/Realtime/focus/session refresh invalidate
  relevant data. Polling does not continually cancel a slow request before its deadline.
- Transient read failures retain an explicitly stale permitted view; 401/403 clear that
  authority's cached data, and 404 clears the missing resource. Logout/scope changes hide
  old content. Thread-specific denial/deletion also hides local reply state, disables
  sending/capture and stops polling; retry cannot briefly resurrect rejected content.
- Guarded stage retry remains explicit, idempotent, cost-confirmed and limited to permitted
  terminal jobs. An API-role visibility check now precedes the SECURITY DEFINER recovery
  function, preventing recovery of a job outside the selected run.

### Two explicitly approved Live retries: actual result

Both retries targeted existing request `c2a07212-537b-4b70-8ec3-14c9669adf67` in existing
run `158f631f-b986-4358-865c-0d57028dee5a`, via normal scoped recovery of interpretation job
`2035e8e0-ba0c-4f3b-8847-9e0809ee4c94`. No new identity/run/provider credential was created.
The founder separately approved each retry because it could incur Google charges.

1. First retry proved truncation: `MAX_TOKENS` at the existing 16,384 output cap, with
   12,986 thought tokens and 3,383 visible candidate tokens. Safe logging records finish
   reason, counts and bounded schema paths, not source content, values, raw output or secrets.
2. The gateway now versions/records its model-compatible thinking allocation. Gemini 3
   text models use LOW, supported 2.5 models use bounded numeric budgets, and incompatible
   models receive no unsupported thinking field. The total output cap and single-attempt
   SDK policy did not increase. Strict finish/schema/admission validation stays mandatory.
3. The separately approved second retry passed interpretation and persisted an **admitted
   17-task candidate**, model `gemini-3.6-flash`. Materialization then stopped:
   `authored_materialization_rejected` (the legacy error name also covers Live admission).
   A scoped read-only diagnostic confirmed the original request is **not** the canonical
   Northstar intake. The existing live admission contract rejects it before snapshot
   creation. Observed counts were **zero snapshots and zero plans** for that request.
4. The saved request was not rewritten, reset, replaced with replay or approved. The UI
   and API now expose the demo's supported intake boundary before new spend and direct
   users to the deliberate **Prepare Northstar launch** path. General non-demo intake
   remains available; free-form read-only questions remain available in the demo.

This verifies the specific truncation correction, not complete Live schedule generation,
approval, commitment or employee execution. There was no third agent-triggered Live retry.
The worker's normal completion reconciliation uses the already persisted interpretation
without calling the model again. Worker logs subsequently recorded the recovery lease
as attempt 4, `succeeded` in 1,178 ms; this is completion reconciliation, not a third
agent-triggered provider retry.

### Lease-renewal correction and rollout boundary

The long successful interpretation exposed a second defect: `renew_durable_job_lease`
updated an ordinary job's expiry but returned PL/pgSQL `FOUND` after an unrelated outbox
update. With no outbox row, the worker incorrectly reported `job.lease_lost` even though
the lease update had succeeded. The additive
`20260927034000_alto_job_lease_renewal_result.sql` migration returns the captured job-update
result instead, retaining current owner/token/expiry/run/actor fencing and privileges.
Applied migrations are unchanged. This new migration is **not applied to hosted Supabase**;
the founder must review/apply it through the normal linked-project workflow in the runbook.
No database reset, scenario reseed, Edge redeployment or change to provider secrets occurred.

### Follow-up verification

- Final focused backend run: **130 tests passed**, covering interpretation/gateway, immutable
  request reads, fixed planning, provider handling, request/recovery API, project read models,
  cross-run recovery, supported-demo intake and exact-plan graph scope. One existing Starlette/httpx deprecation
  warning remains. Ruff and strict mypy passed for the 13 changed Python files checked.
- Desktop: **102 tests across 14 files passed**, including restored tabs/threads, account
  isolation, request deadlines, role setup, canonical demo intake and denied-thread handling.
- Production frontend build and zero-warning ESLint passed (614.51 kB JS / 170.84 kB gzip
  after the intake guard); the existing non-failing 500 kB chunk-size advisory remains.
  No new dependency was added.
- Three separate watermarked Edge fixture captures were inspected: explicit role choice,
  new request preview, and stopped planning. No JS exceptions or horizontal overflow at
  1672 by 941. Retry/refresh spacing and the demo-intake banner layout were corrected,
  then the three captures were regenerated and inspected against the final UI.
  Historical 19-screen captures were preserved. This is not installed-native/live evidence.
- API and worker were rebuilt with the gateway correction and returned healthy. Scanner,
  tunnel and registrar remained running. The original hosted connection and credential
  binding were reused without printing secrets. The final API guard was subsequently
  rebuilt/recreated and returned healthy; no additional provider call was made. The hosted
  migration rollout remains pending and separate from the two earlier retry results.
- Repository contract checks passed. No installed-native package was rebuilt in this
  follow-up; the old installer does not include these later UI changes.
- Lease migration: **15 pgTAP assertions passed** in the network-isolated disposable
  `alto-db-verification-20260926` database. A transaction applied the actual migration,
  compared function owner/grants/security/configuration unchanged, and exercised ordinary
  and outbox success plus wrong worker/token/company/run, expired, cancelled and terminal
  denials. Rollback left tip `20260927033000` and zero test jobs. The container was stopped
  again; no hosted SQL was applied. The manifest verifies **42 immutable files** with the
  prior 41 hashes retained.
- Verification initially encountered transient Docker named-pipe HTTP 500/timeouts and
  worker DNS failure; no Docker-engine restart was performed. The integration test container
  was returned to its initial stopped state. Local API readiness subsequently returned
  `ready`, and the final isolated SQL verification succeeded. An initial regression fixture
  set a company-scoped worker context without an actor; it was corrected to production's
  ordinary queue context. The integrated retry-bound fixture was also updated to canonical
  intake after the new guard correctly denied its older unsupported sample. Final runs
  passed; neither correction relaxed production authorization.

Run instructions: [ALTO runbook](alto-runbook.md#apply-the-planning-role-and-cached-navigation-follow-up).

## Autonomous planning, quiet refresh and supplied logo (27 September 2026)

### Cause and implementation

- Read-only diagnosis of request `eaa02f74-5af4-407f-a4a5-64003ab2ad5e` found that its
  live interpretation proposed `northstar.jules` as a hard skill on tasks `d1` and `m2`,
  while the pinned authority names Iris. The contract had already passed generic
  interpretation admission; repeating materialization only rechecked that same immutable
  bad contract. The checker was correct to reject the extra requirement.
- A reusable finite contract check now runs before interpretation completion, after the
  worker authenticates the leased run's immutable operator manifest, exact selected source
  versions/digests, access, freshness and projection bytes. Materialization repeats this
  authority check. It does not substitute an authored schedule, remove requirements or
  loosen the allowed source/task/owner policy.
- Model-representation errors become immutable rejected candidates. A later attempt can
  receive only allowlisted issue codes/field paths and the previous contract digest from
  that same company/request/run. The repair context is hashed into recorded model settings.
  Prompt `interpretation-v5` makes task-specific eligibility explicit. Repair context v2
  also contains a typed 17-task eligibility lookup derived only from the currently
  authenticated source authority, bound to the exact LAUNCH-07 version and included in
  the same provenance digest/input budget. Source revocation,
  policy gaps, refusals and real human decisions remain stops.
- Live interpretation has at most three total durable attempts, including the initial
  attempt; SDK calls remain single-attempt and the output cap remains 16,384. Completed
  interpretation reconciles without a new provider call. Fixed-plan authoring keeps its
  existing three-round bound. No attempt reset or automatic approval/commit was added.
- The request read model now follows ALTO's `plan.propose` job rather than only the legacy
  `planning.run` job. The API does not offer unsupported manual `plan.propose` recovery
  or an interpretation retry after its three-attempt budget.
- Finishing fixed-authoring rounds without a checked plan now records
  `fixed_plan_not_verified`, not a successful handoff. Historical successful jobs lacking
  a plan also stop UI handoff polling rather than leaving the conversation waiting forever.
- The desktop shows a small accessible activity circle for actual queued/leased/running/
  retry-scheduled stages, honors reduced motion, and keeps GET polling across handoffs.
  Terminal errors, human questions and proposals do not show a running circle. Successful
  cached refresh is silent; a failed refresh has a discreet stale-data notice and Retry.
- All shared in-app logo instances now display the unchanged `docs/design/LOGO.jpeg`
  through a tight viewport. No generated replacement, image editing or new dependency.
  This does not change native installer/application icons.

### Verification and deployment

- **133 focused backend tests passed**, including 22 new recovery cases, the actual
  Jules/Iris mismatch, rejected-before-handoff behavior, immutable scoped repair feedback,
  three-attempt stopping, source tampering, real-decision stops and authoring-stage reads.
  Ruff and strict mypy passed for the affected implementation. The existing Starlette/httpx
  deprecation remains. One prior run exposed an outdated 20-attempt API expectation; its
  assertion now separately enforces the three-attempt interpretation budget. A cache-write
  permission warning was avoided on the final run with `-p no:cacheprovider`.
- **71 focused UI tests passed** across planning, Home, logo, cached views and assistant.
  Desktop TypeScript/build and zero-warning ESLint passed. Production output includes the
  original 30.45 kB JPEG; the existing non-failing 500 kB JS chunk advisory remains.
  The new two-case logo test initially lacked explicit DOM cleanup; adding the existing
  suite's cleanup pattern corrected test isolation without a production change.
- Four separate watermarked fixture captures in
  `apps/desktop/src/test/autonomous-planning-visual-artifacts/` were regenerated and reviewed.
  Logo decode succeeded; running-circle animation and reduced-motion behavior were checked;
  stopped state had no circle, refresh chatter, JS exception or horizontal overflow. These
  are isolated browser fixtures, not installed-native or authenticated Live UI evidence.
- The founder explicitly approved applying **only** migration `20260927034000`. The linked
  project matched `ljyrrilzulffykvzmubt`; history showed the preceding 41 versions applied,
  and dry run listed only the lease-renewal migration, no seeds or roles. Application
  succeeded. A least-privileged runtime read of the function definition confirmed the
  captured-job-result correction. No reset, reseed or Edge deployment was performed.
- API and worker were rebuilt and returned healthy; existing scanner/tunnel/registrar
  were not recreated. The working tree remains on `feat/alto-product`, unpushed. The
  container's inherited base commit label is not a commit of these uncommitted changes.

### One expressly approved new Live verification

The founder approved one new supported Live workflow, including bounded provider repair
attempts, in existing run `158f631f-b986-4358-865c-0d57028dee5a`. Root created
`104dc632-9809-48c7-8727-9e344bfc25c8` through the normal scoped canonical request store,
with a stable single-use idempotency key, after rechecking current manager context and
the applied lease fix. The insert trigger starts its normal durable interpretation job;
no extra enqueue/reset was needed. The old request and candidate were preserved. This
uses existing least-privileged container configuration; it is not a Supabase JWT/login smoke.

Observed outcome: **no snapshot or plan**, terminal `review_required` with
`interpretation_contract_rejected`. Attempt 1 (prompt v4) returned a complete contract
with 17 rejected hard-requirement representations and scheduled automatic repair. Attempt
2 encountered `company_gemini_credential_unavailable` and lost its lease after about 126
seconds, with no corresponding interpretation record. Attempt 3 used the recorded repair
digest but still proposed Jules for D1 and was rejected. Two interpretation outputs were
recorded; this is not an assertion about billing for the interrupted credential lookup.

During this run, Docker Desktop's named-pipe API returned HTTP 500 and local API readiness
timed out. Read-only diagnostics through the same least-privileged API connection recovered
the saved state without creating another request. Docker subsequently recovered without
an engine restart; API, worker and registrar were healthy. The lease fix remained present,
and a final Supabase dry run reported no pending migrations.

The observed rejection motivated the source-bound typed lookup in prompt v5 described
above. The founder separately approved **one more new Live request** to verify that
refinement. The first verification request remains unchanged; no budget was reset and
no plan was approved or committed.

### Second separately approved Live verification: recovery passed, persistence stop

Request `03e7420f-7801-450f-beec-6b6058bb9350` used the same owned Live run and a new,
explicitly approved idempotency key. Prompt v5's first contract was rejected; its second
attempt, with source-bound task requirement guidance, was **admitted automatically**.
Interpretation job `0aa348b0-b9cf-4e37-9f05-b22441d0d0c4` succeeded on attempt 2.
Materialization succeeded on attempt 1 and saved snapshot
`10764d13-308b-5e19-990c-7947496386cd`. No manager click, source weakening or authored
schedule substitution was used between these stages.

Schedule job `be0f2fed-0e51-42f6-a6f9-ce774fd583fa` then reported
`fixed_planning_store_unavailable` after starting a model-run record. Its automatic
second attempt detected that incomplete record and stopped with
`planning_cancelled_fenced_or_ambiguous`; it did not blindly repeat the paid call.
There is **no saved proposal or plan** for this request. The model's unrecorded result
is unknown and was not reconstructed, approved or assigned.

Read-only runtime checks confirmed the checkpoint statement can be planned under the
existing worker's column-level UPDATE privileges. Local inspection identified the
`model_run_transition` BEFORE UPDATE trigger comparing generated `scope_id` before its
new value is calculated. A rollback-only temporary table in the network-isolated
disposable PostgreSQL reproduced the actual function rejecting a legal running-to-failed
transition with `55000 model_run_immutable_binding`. Authored replay bypasses these model
updates, explaining why its earlier tests did not cover this Live-only failure.
PostgreSQL's [generated-column trigger timing](https://www.postgresql.org/docs/17/trigger-definition.html)
also documents that distinction. The old hosted error did not retain an underlying SQLSTATE,
so this is a reproduced code defect consistent with the observed failure, not a recovered
provider response or a proof that no other persistence error occurred.

The additive `20260927035000_alto_model_run_generated_scope.sql` correction passed
**23 focused pgTAP assertions plus one function owner/ACL/settings comparison** in the
network-isolated database. The test reproduces the old failure, applies the actual patched
trigger, preserves company/run/model/provider/input bindings and terminal immutability,
and exercises real model checkpoints under the non-owner worker with exact lease checks.
The first harness run could not invoke pgTAP as the runtime role; the final harness records
temporary worker results and asserts after RESET ROLE, without application privilege changes.
All migrations and fixtures were rolled back. Persistent tip33000 and zero test model/Auth
rows were confirmed, and the disposable container was returned to its original stopped state.

The 43-file migration manifest and independent read-only migration review passed. Hosted
application of 35000 was then awaiting separate approval, subsequently received and applied
as recorded below. This correction does not
recover an ambiguous provider result or authorize resetting either verification run. No
additional paid workflow, approval or assignment was performed.

Final UI copy verification reran **32 planning/logo tests**, the production TypeScript/Vite
build and zero-warning ESLint successfully after the safe ambiguous-result message was
added. The production bundle is 616.77 kB JavaScript / 171.49 kB gzip with the existing
chunk advisory. API, worker and registrar were healthy on final read-only inspection.
Nothing was committed or pushed; full Live plan completion remains unverified.

### Separately approved hosted checkpoint migration (27 September 2026)

The founder approved applying only `20260927035000_alto_model_run_generated_scope.sql`.
The linked project was `ljyrrilzulffykvzmubt`; remote history matched the preceding 42
versions, and dry run listed only 35000, with no seeds or role changes. The local file hash
matched the tested manifest entry before application. `npm.cmd exec supabase -- db push
--yes` applied that one migration successfully; a subsequent dry run reported up to date.

Read-only catalog checks under the existing non-owner API role compared before/after
definitions. The deployed function matched the exact expected corrected SHA-256, had
both generated-column exclusions and retained its terminal guard. Function owner, ACL,
search path, security-invoker setting and generated expression were unchanged. An initial
diagnostic omitted the login's normal SET ROLE and was denied; using the established API
role selection resolved that read without granting any privileges.

Repository state: `feat/alto-product`, base commit
`4246e491c10a3635b2283af37a3e0c924f4b43cb`; the migration remains an uncommitted working-tree
file, not part of that base commit. Applied migration SHA-256:
`a01e9eda5787c440601e8b8543cfd78614e18f2c36580e1c4dc8d672d6e4a419`.
No reset, reseed, application-row repair, model call, approval, assignment, Edge deployment,
container restart, commit or push occurred. Old stopped requests remain history; this
deployment does not establish full Live plan completion or recover an unknown model result.

### Repeated fixed-plan failure: complete repair feedback (27 September 2026)

The founder reported `fixed_plan_not_verified` on request
`29ce7906-affb-42a5-ae9b-1aebdd519763` in their existing Live workspace. Scoped read-only
inspection found one durable planning attempt containing three recorded model attempts:
two saved proposals with real schedule violations, followed by `model_output_truncated`.
No plan, approval or assignment existed. This was distinct from the older ambiguous
checkpoint failure and required no further database migration.

The first proposal's report already recorded five failed hard rules: the protected
reservation and Alex, Maya, Priya and Sam resource checks. Its repair diagnostics only
included one sufficient solver conflict set. Consequently E1, which crossed Alex's
Monday 12:00–13:00 unavailable interval, was incorrectly excluded from the first repair
scope. The second proposal still contained that conflict; the final model response was
truncated. The defect is not evidence that the admitted schedule is infeasible.

Implemented with isolated planning and status-readmodel agents, followed by independent
review and root integration:

- Fixed verifier v2 reports every confirmed false hard rule, retaining the solver's
  original conflict subset separately. Unknown checks still stop without invented facts.
- Plan author prompt v2 / repair feedback v1 includes bounded offending time intervals,
  affected task IDs, capacity/daily-budget facts and safe schema/fact-copy corrections.
  It does not select replacement slots or expose raw private source/model content.
- Revision scope follows only admitted snapshot dependencies and review relationships,
  never rejected model gates. A changed review owner can update the reviewed task's
  exact reviewer references without gaining permission to move that task. Unrelated
  edits, movement locks, independent validation and explicit approval remain enforced.
- Full-plan authoring gets its own optional output ceiling. The host default is 32,768
  tokens; other operations retain 16,384 in this deployment. Three authoring rounds,
  single-call SDK attempts and the 150,000-character input boundary are unchanged.
  Future responses may consume more tokens and incur higher Google charges.
- The API/UI now separate worker attempts from exact scoped AI attempt records and
  expose only allowlisted latest error codes. Counts are not billing evidence. The
  current stopped request reads one worker attempt, three AI attempts and truncation.

Read-only replay of both immutable saved proposals through the new checker confirmed
that all five first-proposal failures are diagnosed together and E1 is now included in
the first revision scope. Only E1's resource rule remains false in the second proposal.
Building the permission-bounded repair inputs from the existing admitted facts measured
142,470 and 140,536 characters, below the unchanged 150,000-character runtime limit.
This computation did not write proposals, run the model or create a replacement plan.

Final focused verification:

- **178 backend tests passed** across repair/verifier/job outcome, output budget,
  checkpoint metadata, request API/readmodel, interpretation/recovery/persistence,
  provider and settings modules. The final command disabled pytest cache writes;
  one existing Starlette/httpx deprecation warning remains.
- **34 planning conversation UI tests passed**, plus ESLint and desktop typecheck.
- Ruff and strict mypy passed for affected backend implementation/test modules.
- Production desktop build passed: 619.42 kB JavaScript / 172.16 kB gzip, with the
  existing non-failing large-chunk advisory. No new native installer was produced.
- Repository contract checks and scoped diff whitespace checks passed.

The owned demo run had no queued, leased or scheduled-retry jobs before rollout.
Rebuilt only API and worker using Compose `up -d --build --no-deps --wait api worker`;
both returned healthy. Read-only runtime inspection confirmed prompt/verifier v2,
feedback v1, 16,384 general / 32,768 planning output limits and the 150,000 input limit.
No `.env` secrets, migrations, Edge Functions, old request records, approval decisions
or assignment state were changed. Nothing was committed or pushed.

A separate existing host-discovery problem was observed before and after rollout:
registrar unhealthy, public tunnel hostname resolution failing (`gaierror`, errno -2),
internal API readiness HTTP 200. Tunnel/registrar/DNS settings were left unchanged;
public reachability must be restored for clients relying on hosted discovery.
**A new paid Live run remains NOT RUN**; this evidence verifies the reproduced code
defects and rollout, not end-to-end model success or employee assignment.

### Public tunnel startup repair (27 September 2026)

The founder explicitly requested diagnosis and repair of `host:start` waiting on the
registrar. Runtime logs established the cause: the existing cloudflared process repeatedly
received `Unauthorized: Tunnel not found`, but remained running. Its container had started
at 08:20 UTC; the later host start rebuilt/recreated backend services but reused that tunnel.
The registrar correctly refused to publish the old unreachable public URL. This explains
the DNS failure observed during the preceding planning work; it was not a Supabase password
or planning-schema failure. The provider-side reason that session ceased to exist is unknown.

Restarting only the tunnel obtained a new registered connection and restored registrar
health without a credential, workspace, data or schema change. Permanent corrections:

- Compose now binds cloudflared metrics to `127.0.0.1:20241` inside its container and uses
  the pinned binary's `tunnel --metrics 127.0.0.1:20241 ready` health command. Nothing new
  is exposed on a host port. Registrar startup waits for real tunnel connectivity, then
  retains its separate public API and existing database lease checks.
- The launcher inspects only the current tunnel container/session's bounded logs. An
  explicit unrecovered `Tunnel not found` rejection allows one tunnel-only recreation
  before startup, or one recovery if first detected during startup. Healthy sessions,
  DNS-only failures, database errors and lease conflicts do not authorize rotation.
  Recovery does not reset the persistent host identity, volumes or application records.
- The registrar emits finite DNS/TLS/timeout/HTTP/invalid-response reasons on status
  changes, never raw exceptions or response bodies. Failed public/database rechecks
  remove its local ready marker; existing database lease expiry and ownership fences
  remain unchanged. `--status` returns only a fresh canonical registered origin matching
  the current tunnel log, so startup cannot announce an old historical URL as success.

Implementation was split between a launcher agent and root registrar/Compose work, then
independently reviewed. **16 launcher tests and 20 registrar tests passed**; targeted Ruff,
strict mypy, repository contract checks and scoped whitespace checks passed. Tests cover
one-time early/late recovery, no healthy/unrelated restart, current URL validation,
failure classification, rotated/stale markers and database heartbeat failure. No migration
or application/planning test suite was needed for this isolated host-lifecycle change.

The actual `npm.cmd run host:start` command then built and applied the updated bundle and
exited successfully with the current registered public URL. That normal deployment
recreated API, worker, tunnel and registrar for the updated image/configuration; the
initial targeted repair and future automatic stale-session recovery target the tunnel only.
Final Docker inspection showed **API, worker, scanner, tunnel and registrar all healthy**.
A separate Windows HTTPS request to the currently registered `/health/ready` returned
`service=coordination-api`, `status=ready`; registrar `--status` reported ready.
The prior public-discovery blocker is resolved at this checkpoint. No planning requests
were created/retried, no AI-provider verification was performed, no database migrations or
Edge Functions were changed, and nothing was committed or pushed. This does not establish
permanent Quick Tunnel uptime or complete the still-separate Live planning verification.

### Proposal actions and planning progress clarity (27 September 2026)

The founder reported `record was not found` from **Open approved brief** and **Inspect task
work** on the Northstar graph. The screenshot was an exact candidate preview. Its node IDs
belong to the immutable proposal payload and deliberately do not exist in `app.work_items`
until the exact plan is approved and committed. The backend correctly returned 404; the
desktop incorrectly presented committed-record actions for proposed nodes.

The graph inspector now states that the selected node is a proposed preview and disables
both actions as **Brief available after commit** and **Work available after commit**.
Committed nodes retain their existing navigation and work modal. No placeholder task,
brief, assignment or database row is fabricated to hide the lifecycle distinction.

The planning conversation now includes a **Progress summary** with three stable lines:
current recorded activity, confirmed completed stages and the next user action. It covers
interpretation, source/constraint checking, schedule checking, durable handoffs, blocking
questions, access stops, other terminal failures, ready proposals, committed plans,
unstarted requests and temporarily unavailable status. The existing circle still appears
only while a stage is genuinely queued, leased, running or awaiting a scheduled retry.
All copy is deterministically derived from persisted request/job/plan fields; it does not
stream or expose model chain-of-thought, raw provider content or private source text.

Implementation was split into independent task-action and progress-summary UI work. Focused
verification passed: **11 graph/contract tests** and **37 planning-conversation tests**,
targeted ESLint and desktop TypeScript checking. Root integration reran the combined
**48 focused tests**, targeted ESLint and the production desktop build successfully.
The build produced 622.72 kB JavaScript / 172.94 kB gzip with the existing non-failing
large-chunk advisory; no native installer was produced. No backend,
database, migration, Edge Function, provider call, planning retry, approval or assignment
was needed for these UI corrections. Nothing was committed or pushed.

### Quick Tunnel runtime recovery and Docker DNS fallback (27 September 2026)

The founder reported that a planning view timed out and restored service by restarting the public
tunnel. Read-only runtime evidence separated two failures. First, an earlier accountless Quick
Tunnel repeatedly returned `Unauthorized: Tunnel not found` without exiting, so Docker's restart
policy could not act and the existing startup-only repair was unavailable until the operator reran
the launcher. Second, cloudflared and the worker simultaneously lost Docker Desktop's single
upstream DNS resolver; the current tunnel later recovered those generic QUIC/DNS interruptions by
itself. The permanent session rejection and transient network loss must not share a restart policy.

The tunnel now uses a small supervisor around the pinned cloudflared binary. Only the exact
permanent rejection terminates and relaunches that child, with exponential backoff capped at 60
seconds. Generic DNS, TLS, QUIC and timeout messages do not trigger an internal restart. Signals are
forwarded for graceful shutdown, with a bounded kill fallback. The image has no Docker socket and
cannot restart the API, worker or data services. Existing cloudflared logfile and loopback metrics
behavior remain in place, so the registrar still withdraws an unhealthy URL and validates a newly
issued URL before republishing it.

Compose now supplies two explicit, overridable external DNS upstreams to the host services while
retaining Docker's embedded service-name resolver. Defaults are documented in the host `.env`
example, including the requirement to substitute organization-approved resolver IPs where a VPN or
corporate network blocks public DNS. This reduces dependence on one Docker Desktop upstream but
does not claim Quick Tunnel, laptop or network high availability. Six focused supervisor tests and
the rendered Compose configuration passed. The new tunnel image was built for validation, but no
running container was recreated or restarted while preparing this change.

### Exact candidate grounding for project assistant (27 September 2026)

The project graph's `VIOLATIONS_FOUND` state and Rules drawer already read an exact
immutable candidate, but project chat previously projected only project metadata,
committed work items and current source excerpts. It had no proposal ID, verification run
or rule results, so a provider could not truthfully answer “what are the violations?” from
the authorised prompt.

Backend support now accepts a nullable `proposal_id` only on project assistant contexts,
persists it on the private thread, compares it on every send and fails closed when the
exact company/project/proposal binding or current manager/demo-planning authority is no
longer valid. The worker projects only that candidate's digest/version, recorded product
and native statuses, rule counts, non-passing rule keys with stored safe diagnostics and
currently readable source metadata, plus independent validation outcome/issues. It does
not project raw solver diagnostics, candidate/model payloads or hidden reasoning. The
assistant instruction explicitly distinguishes a recorded violation from an unable check
and prohibits inventing a cause beyond the persisted evidence.

The graph now passes its exact `selected_proposal_id` into a proposal-bound project thread,
resets that thread when the selected proposal changes, and keeps proposed task questions in
the proposal context because those task IDs do not exist as committed work items. A visible
violation summary lists each recorded rule key, safe diagnostic and permitted source before
the user asks chat; the Rules drawer sorts and opens violations first and identifies them as
deterministic verifier evidence rather than hidden AI reasoning. Approval remains disabled.

Focused integration verification passed: 12 graph/contract UI tests, desktop typecheck,
31 combined workspace/worker tests, Ruff, the 44-file migration manifest and 8 rollback-only
pgTAP assertions. No provider call, planning retry, remote migration or hosted data change
occurred at this checkpoint.

### Personal calendar scoping and transient worker-store recovery (27 September 2026)

The manager **My calendar** route previously supplied no employee selector. Its read model
interpreted `NULL` as all permitted employees, so Maya's screen rendered the Northstar
dataset's repeated 15:00 protected blocks side by side. The route now always supplies the
authenticated/effective demo employee ID, and both committed-work and external-event queries
use strict equality. A missing employee profile returns no personal blocks rather than
widening authority. Permitted project deadlines remain separately selected markers.

The same incident showed the durable worker exiting when a transient Docker DNS failure made
its Supabase heartbeat unavailable. The daemon now catches only `DurableStoreError`, emits a
sanitised `worker.store_unavailable` event, and waits with a capped 1-to-30-second exponential
backoff. It does not infer a job result or bypass lease fencing; the recorded lease and durable
model checkpoints remain authoritative after connectivity returns. `--once` reports exit 3
instead of leaking a traceback. Focused calendar/worker tests and Ruff passed; no running host
container was restarted while preparing these changes.

### Integrated reliability, calendar and violation rollout (27 September 2026)

The linked Supabase dry run listed only
`20260927036000_alto_exact_proposal_assistant.sql`; that additive migration was then applied
successfully. No seed, reset or other migration was included. `npm.cmd run host:start` rebuilt
and recreated the host stack once, activating the API calendar/assistant changes, worker store
backoff, explicit DNS upstreams and supervised tunnel image. API, worker, scanner, tunnel and
registrar all reached healthy, and the registrar published a newly public-checked origin.

Final focused verification passed: 12 desktop graph/contract tests, desktop typecheck,
31 backend workspace/worker tests, Ruff, 6 tunnel-supervisor tests, the 44-file migration
contract, Compose validation and the connected five-service health gate. No planning request,
AI/provider call, retry, approval, assignment, seed or Edge Function deployment was performed.
The existing failed candidate remains immutable; users can review its newly visible rule evidence
or ask a new exact-bound assistant question without altering that candidate.

### Confirmed assistant actions and bounded Live schedule correction (27 September 2026)

The assistant can now stage explicit proposal-bound planning commands, but it still cannot silently
approve or commit work. A manager sees the exact action, target proposal, consequences and provider
cost warning, then must confirm or dismiss it. Migration
`20260927037000_alto_confirmed_assistant_plan_actions.sql` records that preview and decision with
project/proposal/plan foreign keys, manager-only lifecycle updates and worker/API privilege
separation. This migration is locally verified and remains pending on hosted Supabase.

The current Northstar version-three candidate was inspected read-only rather than relabelled. Its
four recorded violations have concrete schedule causes: Q1 was split between Monday and Tuesday
despite `split_allowed=false`; Q2 overlapped Priya's protected Tuesday 11:00–12:00 reservation; and
M3 placed Nora in her unavailable Tuesday lunch period. Rechecking the canonical P1 reference
schedule against the exact same saved snapshot passed all 157 deterministic checks. The fixture and
verifier are therefore internally consistent; deleting these rules would conceal an unsafe plan.

The correction keeps every failed proposal and result immutable while allowing one initial proposal
plus at most four complete replacements. Plan author prompt v3 explicitly requires a no-split task
to occupy one contiguous block on one local day and requires every scheduled slot to be available,
including across lunch boundaries. Relevant busy rows are filtered and sorted before deterministic
reservation numbering, so diagnostics no longer acquire unstable suffixes from unrelated resources.
An older saved `fixed_plan_not_verified` request with three candidates can expose an explicit
manager-confirmed retry into versions four and five; all other terminal errors and exhausted chains
remain closed. The continuation preserves the exact snapshot, evidence and parent chain.

Migration `20260927038000_alto_bounded_live_plan_revision.sql` widens only the proposal-version
constraint from three to five and narrows `plan.propose` retry authority to the exact safe error,
manager authority, fewer than five AI proposals and the existing 20-attempt ceiling. It retains
security-definer ownership, search path and API-only execute permission. It does not mutate the
current failed proposal, approve a plan, assign work or disable a verifier rule.

Verification passed **83 focused backend tests**, Ruff and strict mypy. The five pending additive
migrations through 38000 and database test 16 passed **18 pgTAP assertions** inside one disposable
rollback-only transaction; the baseline `version <= 3` constraint and zero new migration-contract
rows were confirmed afterward. The immutable migration manifest passes with 46 files and
`git diff --check` is clean. No provider call, hosted migration, hosted row mutation, approval,
commit or assignment was performed. Activating the continuation still requires hosted application
of migrations 37000/38000 and rebuilding API/worker; using it may incur up to two further provider
calls and requires separate authorization.

The founder then explicitly approved deploying both pending migrations. The linked project was
confirmed as `ljyrrilzulffykvzmubt` and healthy. Migration history matched local files through
36000, and `db push --dry-run` listed exactly 37000 and 38000 with no seeds or role changes. Both
migrations applied successfully. A subsequent remote migration listing records both versions and
the final dry run reports the database up to date with no pending migrations, seeds or roles. No
planning retry, provider call, approval, commit, assignment, Edge deployment or data reset was
performed as part of this deployment. The updated API/worker still needs to be rebuilt through the
normal host launcher before the new runtime paths are active.

### Zero-login judge activation (27 September 2026)

The founder explicitly approved the hosted hackathon quickstart rollout. The linked-project dry
run listed exactly `20260927039000_alto_hackathon_quickstart.sql`; the migration was applied with
Vault updates skipped and no seeds or role changes. A final linked dry run reported the database
up to date. The applied file came from the working tree based on commit
`4246e491c10a3635b2283af37a3e0c924f4b43cb` and has SHA-256
`d2d10ad7d39f53474391fe1ff4e4c14e09945c71f66bcbe904bde9458ca972fa`; the ALTO worktree remains
uncommitted, so that base commit is not represented as containing the migration.

Northstar's only active, validated, unrevoked Vertex service-account version (v2) was selected as
the operator-managed default. The operation stored only the existing Vault-backed version
reference and did not read or print the service-account JSON. Read-only verification confirmed the
default is enabled and still points to an active validated unrevoked version.

Hosted Auth initially rejected the fresh-judge smoke because anonymous sign-ins were disabled. A
full config diff showed four locally declared changes, so the project config was deliberately not
pushed. A temporary minimal config was independently diffed and showed exactly one declared update:
`auth.enable_anonymous_sign_ins=false -> true`. That single property was pushed; twelve undeclared
remote settings were left unchanged, and the temporary config was removed.

A real fresh-judge smoke then passed hosted anonymous Auth, fixed Northstar onboarding, isolated
Maya quickstart and operator binding with `provider_status=configured`. The smoke made no Gemini
generation call and therefore is evidence of an AI-ready binding, not evidence of shared Vertex
output quality or billing. One earlier harness attempt created an isolated anonymous membership but
correctly failed quickstart because the harness omitted `X-Company-ID`; the desktop client already
sends that required header. Desktop verification passed all 136 tests, TypeScript typecheck, ESLint
and repository contract checks. The running desktop must be fully reopened once so its existing
pre-change Auth controller replaces the legacy password session with the new anonymous identity.

The first reopened development client exposed a Supabase startup race: its `INITIAL_SESSION` event
advanced the Auth revision while `getSession()` was pending, so restoration correctly abandoned its
stale result but the event path directly activated the legacy password session. The event path now
routes any non-anonymous session back through the same locked-demo conversion, and the quickstart
403 Retry action explicitly renews that identity. A regression reproduces the interleaving; all 137
desktop tests, TypeScript typecheck, ESLint and repository contract checks pass afterward.

### Gemini-first verified Northstar fallback (27 September 2026)

The locked hackathon worker now gives Gemini one complete schedule-authoring attempt for a fresh
Live Northstar request. A passing AI candidate remains `ai_authored`. If that attempt returns an
invalid or unverifiable schedule, malformed structured output or a provider error, its recorded
model/candidate evidence is preserved and the worker appends canonical P1 with truthful
`authored_replay` provenance. P1 is not marked successful by the fallback: it must pass the same
fixed Z3 verifier and independent concrete-schedule validator, otherwise the job still closes as
`fixed_plan_not_verified`. Ordinary deployments retain the existing five-proposal authoring budget.

The locked desktop offers **Prepare a new Northstar plan** for an existing saved schedule failure.
That action creates an idempotent canonical successor and leaves the failed request unchanged.
Technical author-kind text is omitted from the locked proposal selector but remains in persisted
evidence and in normal installations. No fallback banner or automatic approval/commit was added.

Verification passed the broader affected backend planning/worker suite, all **140 desktop tests**,
desktop TypeScript typecheck and ESLint, plus scoped Ruff and strict mypy for the changed backend
modules and tests. No provider call, hosted data mutation, migration, approval, commitment or
assignment was performed. `npm.cmd run host:start` rebuilt the host images with this worker and all
five services returned healthy at the newly registered public origin. A fresh Live scheduling
request remains required to exercise the fallback outside fixtures.

### Required Maya first-run tour (27 September 2026)

The locked downloadable hackathon client now starts a required three-step tour only after
quickstart confirms the default Maya manager, Live Northstar run and operator-managed AI binding.
The first step routes through the masked Vertex and deployment panels. The second uses the real
durable assistant endpoint in Ask mode with the exact guided question; it persists only opaque
thread and command identifiers, resumes idempotently across reloads, and does not advance without
a completed assistant message. The third highlights the existing canonical Northstar action and
records completion only after that request succeeds. The saved completion is not cleared by demo
restart, while About exposes an explicit replay that creates fresh command keys.

The coachmarks add no UI dependency and include focus control, keyboard operation, responsive
placement and reduced-motion handling. An inaccessible saved thread or failed assistant/request
command remains on its current step with an explicit retry; no canned answer or successful result
is substituted. Completion still opens the ordinary planning conversation and does not approve or
commit a proposal.

Verification passed all **150 desktop tests**, TypeScript typecheck, ESLint and the production Vite
build. The suite covers the complete locked Maya path, exact guided prompt and idempotency headers,
reload between thread creation and message submission, inaccessible-thread failure, request
success/failure, completion persistence and About replay. Unsigned Windows x64 NSIS packaging also
passed and produced `ALTO_0.1.0_x64-setup.exe`; the package was not installed or visually exercised,
so installed interaction and responsive visual acceptance remain separate evidence gates.

### Layered locked-demo AI rate limiting (27 September 2026)

The locked API now admits at most 12 unique AI-triggering idempotency keys per anonymous Auth user
inside a rolling minute. Assistant messages, the canonical Northstar request, interpretation and
clarification commands, eligible retries, transcription and AI-assisted private feedback share that
boundary. Thread creation, reads, polling, review, approval and commitment remain outside it. A
rejected key is not recorded, while replaying an accepted key in the active window is free. The API
returns a safe HTTP 429 response with `Retry-After`, and the desktop preserves that value on its
typed error while the existing onboarding retry path keeps the current stage.

The single worker process now shares a separate 120-call rolling window across every tenant Gemini
gateway used by interpretation, fixed-candidate authoring, assistant answers, preference suggestions
and transcription. Capacity is checked before model-run evidence begins and then reserved at the
exact Google SDK boundary; because the current worker executes leased jobs serially, this prevents
rate waiting from manufacturing a new model run or durable attempt. Accepted work waits under the
existing lease-renewal thread. Ordinary installations receive no limiter. Both counters are
process-local by design for the one-API/one-worker laptop topology and must move to shared Postgres
reservations before horizontal scaling.

Verification passed **347 backend tests**, including eight focused limiter regressions, and all
**154 desktop tests**, including typed `Retry-After` handling and the locked onboarding retry state.
Ruff, strict mypy across source and tests, ESLint, TypeScript typecheck, the production Vite build,
16 host-launcher tests, repository contracts, the 47-file migration manifest and `git diff --check`
all pass. The rebuilt API and worker both reported locked mode with limits `12 / 120`; API, worker,
scanner, tunnel and registrar all reached healthy. No Gemini request, hosted data mutation,
migration, approval, commitment or assignment was made during verification.

Unsigned Windows packaging produced the refreshed NSIS installer
`ALTO_0.1.0_x64-setup.exe` (1,303,618 bytes, SHA-256
`042CF06D1E34D113F05B1CF2FE5DDAC1F51C9A4E33283450C9D4365A8158B2F1`) and MSI
`ALTO_0.1.0_x64_en-US.msi` (1,814,528 bytes, SHA-256
`1CBC1AE089B419FE9C33BFF943F51DA048DE7C367DD0E98F663088566C48EBE9`). Neither package was
installed, signed or visually exercised; those remain separate release gates.

### Deterministic locked-demo schedule handoff (27 September 2026)

The observed locked Northstar request reached schedule checking with an invalid model candidate,
leaving all 157 required rules unable to report pass or violation. A later attempt stopped with
`planning_cancelled_fenced_or_ambiguous` before the verified fallback could be saved. The locked
judge path no longer places schedule authoring behind a provider call. After the ordinary Live
interpretation and snapshot stages, it directly constructs canonical P1, records truthful
`authored_replay` provenance and zero model rounds, and runs the unchanged fixed Z3 verifier,
independent validator, immutable promotion and approval boundaries. Ordinary deployments continue
to use bounded Gemini schedule authoring.

The locked desktop now offers a fresh canonical Northstar successor for any non-policy terminal
failure at the schedule-checking stage, including the already-saved ambiguous failure; the failed
request remains immutable. Focused verification passed 24 backend planning tests and 39 desktop
planning-conversation tests. The broader suites then passed 346 backend tests and 155 desktop
tests; Ruff, strict mypy, desktop TypeScript/ESLint and repository contract checks also passed.
The production desktop web bundle also built successfully (96 modules); Vite reported only its
existing non-failing large-chunk advisory.
`npm.cmd run host:start` rebuilt the API, worker, registrar and tunnel images, and all five host
services returned healthy at the newly registered public origin. No fresh planning request or
provider call was made, so the installed-client end-to-end walkthrough remains a separate runtime
check.

### Release documentation and publication inventory checkpoint (27 September 2026)

The public root and landing-page READMEs were updated locally before release preparation. They now
describe ALTO, the Maya first-run experience, the three stable asset names, signing limitations,
safe application-opening guidance, the Data Room, release notes/checksums and authenticated backend
discovery. The public wording does not describe the physical demo-host arrangement. These README
changes remain part of the uncommitted `feat/alto-product` working tree and were not rewritten in
this documentation follow-up.

The repository currently contains 50 immutable migration files. Recorded hosted evidence ends at
`20260927039000_alto_hackathon_quickstart.sql`; the later
`20260927040000_alto_expired_job_reconciliation.sql`,
`20260927041000_alto_locked_demo_job_continuity.sql` and
`20260927042000_alto_locked_demo_session_rebind.sql` do not have recorded hosted application
evidence. An earlier final dry run was up to date only for the then-current `39000` repository tip.

The current native workflow builds three temporary `coordination-engine-*` Actions artifacts. It
has `contents: read`, does not create a GitHub Release, does not normalize the public ALTO asset
names and does not pass `VITE_HACKATHON_DEMO=true` into the build. Therefore no existing workflow
artifact is the final locked judge distribution, and the landing page's stable download URLs remain
dependent on the future tagged release automation.

The intended publication set includes the application, backend, local-host implementation,
Supabase migrations/functions/tests, release and Pages workflows, source tests, operational
documentation, ALTO logo, supplied storyboard references, explicitly watermarked browser evidence,
landing-page source and the compressed demo MP4. Filled environment files, credentials, runtime
state, `tmp/`, caches, `node_modules/`, `dist/`, Rust targets, downloaded artifacts and local
database/Docker state are excluded. Ignored or generated content must not be force-added.

Per the founder's instruction for this checkpoint, no regression test, repository check, linter,
typecheck, build, migration verification, live request or smoke test was run. No hosted setting,
migration, provider, GitHub branch, pull request, workflow, release or Pages deployment was changed.

### Three-platform release preparation and verification (27 September 2026)

Native release automation now validates the four application versions and the locked public
judge configuration, builds Windows x64 plus both macOS architectures, and assembles stable
ALTO installer names, per-platform manifests and `SHA256SUMS.txt`. Manual runs retain temporary
candidate artifacts. Reviewed stable SemVer tags publish only after the entire asset set has
been verified, using a draft release and refusing to replace a published tag. Windows remains
unsigned; macOS is ad-hoc signed and not notarized. Native compilation is not hardware testing.

With final checks now authorized, `npm.cmd run check` passed: ESLint/Ruff, TypeScript/mypy,
156 desktop tests, 348 backend tests, 16 host-launcher tests, the desktop Vite production build,
repository contracts and the 50-file immutable migration manifest. The landing-page suite
passed all four tests and its production build passed. Release safeguard tests passed all 17
cases. Existing non-blocking dependency-deprecation and Vite bundle-size advisories remain.
Stale test fixtures were corrected without weakening production authorization checks.

Read-only hosted inspection supersedes the previous checkpoint: migration history and the
runtime contract contain 49 migrations through `20260927041000`. Migration
`20260927042000_alto_locked_demo_session_rebind.sql` is still pending explicit hosted-change
authorization. API, worker, scanner, tunnel and registrar recovered to healthy without a
restart; endpoint discovery had a fresh lease. This is readiness evidence, not a completed
installed-client walkthrough or provider-response test.

The current locked Northstar planning path uses canonical interpretation, snapshot and schedule
data, truthful authored-replay provenance, and the real fixed Z3 verifier and independent
validator. The assistant remains provider-backed. Earlier journal descriptions of live
interpretation before the locked schedule handoff describe an older implementation.

The publication inventory excludes secrets, filled environment files, runtime state, `tmp/`,
caches and build outputs. Completed READMEs are preserved. GitHub MCP has created the release
preparation issue and topic branch from current `main`; remote source publication, PR checks,
native CI candidates, the tagged release and installed-client verification remain pending at
this checkpoint. No release is claimed from local compilation alone.

### Draft PR and database-test correction (27 September 2026)

GitHub MCP published the reviewed text source and opened draft PR #66. Its native-shell checks
passed on Windows and macOS; Edge Function checks passed. Repository and application checks
remain blocked by the missing supplied image files, including the imported ALTO logo. The working
MCP file tool treats binary payloads as text, while the binary-capable connector returns 403.
The one malformed test upload was removed. A separate, non-force Git upload of the 47 reviewed
images awaits the founder's permission; the existing demo video is unchanged.

The disposable CI database applied all 50 migrations, then exposed two stale test assumptions.
The schema test expected 44 migration registrations instead of 50. The session-rebinding test
called reconciliation and the STABLE authorization function in the same SQL statement, so the
authorization assertion saw the statement's pre-update snapshot. It now checks authorization
in a subsequent statement, matching the worker's execution boundary and preserving all five
assertions. No production function or immutable migration was changed.

Targeted rollback-only verification in the explicitly identified local Supabase Docker database
reproduced the original session-test failure, then passed the corrected five session assertions
and all 23 schema assertions. Migration 42000 was included only inside each rolled-back test
transaction; the local database still recorded 49 migrations through 41000 afterward.

The founder explicitly declined applying migration 42000 to the hosted database. Hosted state
was left unchanged. Fresh uninterrupted sessions can proceed, but queued planning work may fail
after a persona-session rotation, expiry or reopen until that migration is deployed. This
limitation remains separate from installer compilation and distribution readiness.
