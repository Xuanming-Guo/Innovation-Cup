# Running ALTO

The current release-preparation worktree is on `feat/alto-product`; the ALTO product changes and
completed README updates have not yet been published through their release PR. Following this
guide does not itself apply hosted migrations, change Auth configuration, call a provider, push a
branch or publish a release. Final evidence is recorded separately in
[`alto-implementation-journal.md`](alto-implementation-journal.md).

## What changed

ALTO extends the existing Tauri/React desktop, FastAPI API, Python durable worker and
non-exposed Supabase `app` schema. It does not replace the database or create another
backend. Internal `coordination` package names and application identity are preserved.

The UI references are the actual PNGs in [`../employee`](../employee) and
[`../manager`](../manager). [`../storyboard-coverage.md`](../storyboard-coverage.md)
maps each screen to its implementation. The master prompt remains the product target,
not proof of installed-app fidelity or hosted readiness.

The implementation includes a shared manager/employee shell, Home, projects, graph and
rule evidence, task work/review, calendar, People/profile, connections, preferences,
assistant and simulation. New APIs carry explicit company, run and actor-session
selectors while retaining the real signed-in Auth identity. Native assistance is a
separate small Tauri window with an opt-in global shortcut, not an in-page imitation.

Planning is now: authorised intake and admission → frozen snapshot → complete Gemini
candidate → fixed-value Z3 checks → independent validation → human exact-version
approval → separate brief-audience approval → atomic commitment. Historical solver
plans remain readable and their already-queued legacy jobs remain distinct. A checked
candidate is not completed work or business approval.

## Existing Supabase: reconcile first

1. Back up the target and inspect its recorded migration history. The repository contains 50
   immutable migrations from `20260926010000_bootstrap_security_boundary.sql` through
   `20260927042000_alto_locked_demo_session_rebind.sql`.
2. Read-only hosted history inspected during release preparation contains 49 migrations through
   `20260927041000_alto_locked_demo_job_continuity.sql`, including expired-job reconciliation
   (`40000`). The repository's locked-demo session-rebinding migration (`42000`) still requires
   operator reconciliation and application before treating the hosted schema as current. Earlier
   “up to date” dry runs describe their own historical repository tips.
3. Compare hosted history and the existing schema with `supabase/migrations` and
   `supabase/migration-manifest.json`. Hosted history must be an exact prefix of the reviewed
   local chain. Do not edit applied SQL, delete existing tables, reset the project, mark unapplied
   SQL as applied, or blindly push the entire history.
4. The founder/operator applies hosted changes. Use migration-owner credentials only
   for this step. API and worker logins remain non-owner, non-BYPASSRLS roles.
5. Keep `app` out of the exposed PostgREST schemas. The narrowly exposed public RPCs
   are authenticated host discovery and service-role-only worker file capabilities.
   Private Storage buckets must stay private.
6. Redeploy both Edge Functions after the migrations when their contracts changed:
   `storage-ticket` and
   `worker-storage`. The latter intentionally uses `verify_jwt=false` because it verifies
   a current, short-lived database job lease or deletion-only expiry capability instead
   of a user JWT. It accepts no caller-chosen bucket or path. Never make its authorisation
   RPCs executable by `anon` or `authenticated`.

Do not run the legacy demo reset command against an ALTO workspace. New scenario
provisioning is additive and will refuse a conflicting immutable manifest version.

## Install and configure

Use the repository's pinned Node/npm, Python/uv, Supabase CLI, Rust and Tauri platform
prerequisites. The root package requires Node 24 and npm 11. The backend supports
Python 3.11–3.13. Native Windows builds need the Microsoft C++ toolchain and WebView2;
macOS packaging, microphone permissions and shortcut behavior require a Mac for native
verification.

From `C:\projects\Innovation-Cup`:

```powershell
npm ci
uv sync --project services/backend
```

Use the safe examples to fill ignored local environment files privately. If a file already
exists, merge only missing settings; do not overwrite existing credentials or configuration:

- `apps/desktop/.env.example` → `apps/desktop/.env`: public Supabase URL/key, ALTO label,
  and either local API mode or authenticated `supabase-discovery`.
- `services/backend/.env.example` → `services/backend/.env`: server-only configuration.
  Start the API and worker with their respective least-privileged database URLs; do not
  run both with an owner DSN. Environment variables override the file per process.
- For the single-laptop host, `deploy/local-host/.env.example` →
  `deploy/local-host/.env`: separate API/worker role URLs, public Supabase URL, existing
  real company-admin Auth ID for endpoint registration, and model settings.

Do not place Vault credentials, provider keys, database passwords or service-role keys
in `VITE_*`, desktop storage, source control or terminal command arguments. The Python
worker uses object-bound Edge capabilities; it does not need a Supabase service-role key.

## Provision the synthetic company once

The original seed must already contain the explicitly synthetic Northstar company
`11111111-1111-4111-8111-111111111111`. After the new migrations, link the intended
Supabase project and save its operator password once in ignored `supabase/.env`:

```dotenv
SUPABASE_DB_PASSWORD='your-raw-database-password'
SUPABASE_DB_URL=
```

Use the actual database-owner password, not an API key or a runtime-login password.
Do not URL-encode it in `SUPABASE_DB_PASSWORD`. Follow dotenv quoting rules if it contains
quotes or backslashes. The script obtains host, port, user and database from the linked
project's ignored `supabase/.temp/pooler-url`, then uses Psycopg to safely combine them
with the raw password. No credentials are hardcoded in tracked Python or passed as CLI
arguments. Do not copy this file into desktop or runtime configuration, or force-add it
to Git. Remove the saved operator secret after setup if ongoing local storage is unwanted.

Alternatively, put a complete migration-owner PostgreSQL connection string in
`SUPABASE_DB_URL` in that file or in the process environment. A nonempty DB URL takes
precedence over the password/link option; environment variables override the file for
the same setting. This does not reuse `services/backend/.env` or runtime-role credentials.
Explicit connections require host, database and user. TLS is required (stricter
certificate-verification modes are preserved); connection timeout defaults to 10 seconds
and must be between 1 and 30 seconds.

First check the connection and synthetic-company guard without changing data:

```powershell
services/backend/.venv/Scripts/python.exe supabase/scripts/alto_scenario.py --check-connection
```

On success, provision the scenario with the existing explicit company confirmation:

```powershell
services/backend/.venv/Scripts/python.exe supabase/scripts/alto_scenario.py --confirm-synthetic-company 11111111-1111-4111-8111-111111111111
```

The CLI now resolves backend imports itself; no `PYTHONPATH` export or interactive
credential prompt is needed. Database failures report the exception class, SQLSTATE and
constraint name when available, never connection strings, server messages or row values.
A read-only connection check does not prove that every provisioning write will succeed.
The script provisions Northstar
Labs in `America/Los_Angeles`, 50 synthetic directory people (36 rich, 14 background;
25 Product and 25 Software), group/team membership, skill declarations and one immutable
scenario template. It creates **no Auth users, fake model runs, accepted submissions or
completed tasks**. LAUNCH-08 evidence is created through actual work. Friday feedback is
created only by an explicit employee command, not preloaded as a director source.

Real visitors sign up/sign in through Supabase Auth, then choose demo onboarding.
Onboarding only joins the explicitly enabled synthetic company; it cannot create or
escalate a production company membership. A visitor is not silently turned into Maya.
Use Simulation to create a private run, then select a visibly labelled synthetic actor.
Actor sessions expire and must be renewed by selecting the actor again.

### Locked judge build

The hackathon build replaces that interactive account/setup flow with a per-installation
anonymous Supabase session. Both gates are required: set `VITE_HACKATHON_DEMO=true` in the
desktop build and `COORDINATION_HACKATHON_DEMO=true` on the API. The API still verifies the
anonymous JWT, active Northstar membership, demo-company marker, enabled demo policy, owned
run and actor session on every request. Clearing application data creates a new isolated
identity; it never reuses another judge's workspace.

After migration `20260927039000` is applied, point the operator default at an already validated
Northstar Vertex profile version. This stores only a reference to the existing Vault-backed
version; the script never reads the service-account JSON:

```powershell
services/backend/.venv/Scripts/python.exe supabase/scripts/alto_scenario.py `
  --confirm-synthetic-company 11111111-1111-4111-8111-111111111111 `
  --enable-hackathon-demo --provider-version <validated-version-uuid>
```

Rotation changes the default for new runs only. Existing live runs retain their immutable
version. To stop new quickstarts and immediately fence shared-provider resolution:

```powershell
services/backend/.venv/Scripts/python.exe supabase/scripts/alto_scenario.py `
  --confirm-synthetic-company 11111111-1111-4111-8111-111111111111 `
  --disable-hackathon-demo
```

Also disable Supabase anonymous sign-ins after judging, review the anonymous-signup IP rate
limit, and retain project quota/billing alerts. Never put the service-account JSON or a private
key in `VITE_*`, source files, installer resources, logs, or fixtures.

The locked host also applies two process-local rolling one-minute limits. Set
`COORDINATION_DEMO_AI_COMMANDS_PER_MINUTE=12` on the API and
`COORDINATION_DEMO_AI_MODEL_CALLS_PER_MINUTE=120` on the worker. The first admits only
new AI-enqueueing command keys per anonymous Auth user; reads, polling, approvals and
accepted idempotent replays are free. An over-limit command receives HTTP 429 and
`Retry-After`. The second is shared by interpretation, planning, assistant, preference and
transcription gateways. An accepted durable job waits under its renewed lease before the
Google SDK call instead of consuming another durable attempt. Both controls are disabled
when `COORDINATION_HACKATHON_DEMO` is false and reset with their respective process. A
horizontally scaled host must replace them with shared PostgreSQL-backed reservations.

To disable new public demo onboarding, an operator can set `enabled=false` on the
Northstar row in `app.demo_workspace_policies`. This does not revoke existing Auth
sessions or memberships; those require their explicit revocation controls. Do not
change a production company's `is_demo` flag to bypass membership checks.

## Start the application

The locally built Windows installer at
`apps/desktop/src-tauri/target/release/bundle/nsis/ALTO_0.1.0_x64-setup.exe` is unsigned local
packaging evidence only. It was not installed and is not the stable public
`ALTO-windows-x64-setup.exe` asset.

The GitHub native workflow produces temporary candidates on manual dispatch and publishes the
complete set only for a reviewed version tag. Every native build receives
`VITE_HACKATHON_DEMO=true`, `VITE_API_MODE=supabase-discovery`, the public Supabase URL and
publishable key, the Northstar company UUID and `VITE_PRODUCT_NAME=ALTO`. Existing server-only
`.env` files are not desktop configuration and must never be copied into the client. The first
public release is ready only when one published GitHub Release contains all three stable assets,
their platform manifests and `SHA256SUMS.txt`; see [the release matrix](../release-matrix.md).

For the intended laptop-host setup:

```powershell
npm run host:start
npm run host:status
```

The Compose bundle runs the API, worker, private ClamAV service, tunnel and authenticated
endpoint registrar. ClamAV's initial signature download can take time and needs several
GB of available memory. Until scanning is ready, files remain quarantined; no clean result
is fabricated. The worker image includes `ffprobe` for bounded media validation. Record
the resolved ClamAV image digest before a release; its maintained `1.4` tag is a patch line.

For local development use separate terminals, with the correct role DSN in each:

```powershell
npm run dev:api
npm run dev:worker
npm run dev:desktop
```

`npm run dev:web` is useful for browser UI work, but it cannot verify native global
shortcuts, OS overlays or installed-app microphone behavior. Local file/voice work also
requires an internal ClamAV daemon, `COORDINATION_FILE_SCANNER_HOST`, `ffprobe`, deployed
Edge Functions and reachable private Storage.

On PowerShell systems that block `npm.ps1`, use `npm.cmd` for the same commands; do not
change the system execution policy merely to start the app.

### Registrar waiting / rejected public tunnel

The registrar becomes healthy only after the public HTTPS `/health/ready` endpoint
responds correctly and the existing host identity successfully renews its database lease.
A running tunnel process alone does not establish either condition.

On September 27, cloudflared was repeatedly reporting `Unauthorized: Tunnel not found`:
Cloudflare no longer recognized that Quick Tunnel session, although its process stayed
running. Ordinary Compose `up` reused it, and the old hostname stopped resolving. Restarting
only the tunnel obtained a new working URL; no credential, workspace or schema reset was needed.

`npm.cmd run host:start` now detects that explicit rejection in the current tunnel session's
logs and recreates only the tunnel, at most once per invocation. Healthy tunnels and
DNS-only, database or competing-host lease failures are not automatically rotated. A real
cloudflared readiness check now gates the registrar; metrics stay on container loopback.
Startup prints the currently validated registered URL, never a URL copied from old logs.

The tunnel image also performs the same narrow repair while the host is already running. It
supervises only its own pinned cloudflared child: the exact `Unauthorized: Tunnel not found`
response terminates that child and requests a fresh Quick Tunnel after an exponential delay capped
at 60 seconds. The supervisor does not have the Docker socket and cannot restart the API or worker.
DNS, TLS, QUIC and timeout errors do not rotate the URL because cloudflared can normally reconnect
after those transient failures. The registrar must public-check a replacement URL before discovery
publishes it.

Compose uses `1.1.1.1` and `8.8.8.8` as explicit external DNS upstreams by default, while Docker's
embedded resolver continues to resolve service names such as `api` and `scanner`. If a corporate
network or VPN blocks public DNS, set both of these to organization-approved resolver IP addresses
in the ignored `deploy/local-host/.env`, then rerun `npm.cmd run host:start`:

```dotenv
COORDINATION_HOST_DNS_PRIMARY=10.0.0.53
COORDINATION_HOST_DNS_SECONDARY=10.0.0.54
```

Do not put hostnames in these settings. A DNS fallback reduces Docker Desktop resolver failures; it
does not mask a disconnected laptop or make a Quick Tunnel production-grade.

If startup still fails, inspect the safe waiting reason:

```powershell
npm.cmd run host:status
docker compose --env-file deploy/local-host/.env --env-file deploy/local-host/.env.runtime -f deploy/local-host/compose.yaml logs --tail 30 tunnel registrar
```

Registrar reasons distinguish DNS, TLS, timeout, HTTP and invalid public health responses.
Database registration retry and competing-host lease conflict remain separate errors.
Do not change credentials, disable TLS verification or reset the database to repair a
tunnel. Once startup reports online, return to the app and retry connecting; authenticated
host discovery picks up the changed URL without rebuilding the desktop.

This remains a demo tunnel, not a permanent production endpoint. Cloudflare documents
Quick Tunnels as a development/testing facility with no uptime guarantee:
[Quick Tunnels](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/).

## Walk through Northstar

1. Sign in and use **Choose my demo role** on Home, or **Switch demo role** in the sidebar.
   Select **Explore as manager**, keep your existing workspace (or explicitly create one),
   and click **Continue as manager**. The selected synthetic identity is displayed before
   confirmation; no real membership permission changes. Live mode requires the selected
   workspace's explicitly bound credential. Guided replay needs no live planning credential.
   From Home, **Prepare the Northstar launch plan** starts the canonical scenario request;
   **Plan work** in the composer lets you describe and confirm another request. **Ask a
   question** remains read-only. Nothing is assigned or accepted by merely sending a request.
2. Inspect the graph, complete task details and Rules. **Authored replay** checks the
   fixture P1 through the production verifier. To inspect the deliberate failure and
   bounded correction, create an **Authored D0 check** run: D0's Q1 Tuesday 10:00–12:00
   overlaps Priya's protected 11:00–12:00, then the linked P1 changes Q1 to 09:00–11:00.
   Select either recorded candidate in the graph history to inspect its own exact rules.
   Historical inspection cannot approve or replace a committed plan. Neither mode is
   presented as live Gemini.

### Open the presentation Z3 evidence

The graph read now selects the requested project directly and reuses its database transaction
for approval-status reads. It does not reconstruct the complete plan review (task placements,
constraint definitions and change records) just to decide whether approval is available.
These timeout-related changes have not been tested or timed following the user's instruction
to skip tests and runtime checks; no improved loading-time measurement is claimed.

The approval dialog's `GET /plans/{plan_id}` read also avoids rebuilding fixed-plan task
metadata through the constraint tables. It reads the exact stored proposal and retrieves
placements directly by company, plan and demo run. Proposal identity, scope and digests,
complete task membership, owners and placement times must match before the review is
returned. Missing or inconsistent fixed data produces an unavailable-review error, never
a partial approvable schedule. Legacy solver reviews retain their existing task query;
approval requirements, source/revision checks and commitment authority remain unchanged.
This read-path change does not require a migration or desktop rebuild. Runtime loading
performance and the end-to-end approval flow still require confirmation.

As a manager, open **Projects**, choose the Northstar project, and select **Rules** on the
task graph. The direct route is `/#/projects/<projectId>/graph?panel=rules`. A current P1
authored-replay run shows **SAT · CHECKED** only when all required constraints are covered,
no required constraint is unverified, the persisted digests still match, and the separate
concrete validator passed.

The drawer groups the recorded rule instances into Owner, Working hours, Busy time,
Effort, Eligibility, Dependencies, Participants, Handoffs, Protected time, Reviews,
Deadlines, and Authorised scope. Open **Protected time**, choose
`protected.priya.tuesday`, then expand **Raw Z3 assertion**. That view binds Q1 Tuesday
09:00–11:00 to Priya's protected 11:00–12:00 half-open interval and retrieves the exact
persisted expression for that rule result. The detail request is manager-only and is
bound to the exact company, demo run, project, proposal, verification run, and result.

The checker is evidence about one fixed encoded candidate, not a formal proof of
real-world correctness, optimality, or global feasibility. Independent validation and
manager approval remain separately labelled. Older runs without technical expressions
remain readable and say that the raw assertion was not recorded.
3. Continue in the saved Home request conversation. Answer any **A decision from you**
   questions with **Answer and continue**. When ready choose **Review plan**, inspect the
   exact task graph/Rules, and approve the exact candidate and source versions. Approve each required
   employee brief audience separately, then commit. A stale revision or revoked source
   requires a fresh proposal; the system must not silently commit a different candidate.
4. Use **Switch demo role → Explore as employee → Continue as employee** (Iris by default),
   keeping the same workspace. Open D1, acknowledge/start as permitted, save a private draft and submit
   the exact artifact. Switch to Maya and accept or request revision of that submission.
   Its single scheduled D2 review is the same decision, not a second work slot.
5. Continue as Alex, Priya, Iris, Nora and Sam through the admitted gates. M1 and S1 alone
   are explicit self-certifiable internal drafts. Other submissions require the appointed
   exact-version reviewer. A review rejection does not turn elapsed calendar time into
   acceptance.
6. Maya explicitly approves R1 readiness after its required acceptance decisions. Friday
   release involves Alex and active publisher Nora; support belongs to Sam. After Priya's
   Q3 acceptance and Sam's S4 submission, Maya reviews the exact S4 evidence in R2 and
   approves the milestone. Only that final command completes the project.
7. Iris/Sam may voluntarily record private feedback and request a tentative preference
   suggestion. Suggestions require a configured live provider; manual preference entry
   is available independently. Share, Keep private and Edit are separate explicit choices.
   Sharing exposes only the exact approved wording to the chosen manager, not raw feedback.
   Editing revokes old sharing; later preferences never rewrite historical plan evidence.

The simulation clock changes the scenario's displayed time. It never submits, reviews,
approves, publishes or completes work. Actual latency/lease timestamps use the real clock.
Clock, fork and reset are under **Switch demo role → Advanced demo controls**; ordinary
planning does not require that page. **Plan review** lists saved requests and pending
decisions and returns to the same conversation. It is not a second intake form.

## Live AI and voice

In the selected run's AI settings, configure your own Gemini API key or Vertex service
account. Validate it and explicitly bind the returned credential version to the run.
Rotation is not silent rebinding; other visitors cannot select your Vault secret.
Choose **Live** for model-authored proposals. The exact model is configurable and logged
as non-secret provenance. BYOK availability and billing are your provider's responsibility.

The assistant receives a bounded authorised projection, not unrestricted company data.
It is read-only: an answer cannot approve, accept or publish work. Authored replay chat is
labelled source-excerpt retrieval, not a fake model response.

Voice starts only after a user click and OS permission, stops before upload, and uses
quarantine/scanning plus duration validation (60 seconds / 8 MiB maximum). The worker sends
validated audio through the existing server-side typed gateway. The transcript remains
editable; it is not automatically sent as a message or command. Closing/hiding the overlay
releases microphone tracks. Audio is deleted after successful transcription; abandoned
audio expires after one hour and a deletion-only worker sweep retries Storage cleanup.
Transient signed URLs and provider-defined upload-token expiry do not bypass DB clean-state,
current-permission or lease checks.

## Troubleshooting and evidence boundaries

- Missing migration/schema: reconcile history; never reset to make a command pass.
- Operator setup failure: use `alto_scenario.py --check-connection` with the saved ignored
  operator settings. Report the safe error code, not the `.env` file or connection string.
  The old generic "Provisioning was rolled back" message also covered connection failures;
  it did not establish that a connection or transaction had started.
- No company after sign-in: complete enabled demo onboarding or ask your company admin;
  a directory identity is not an Auth membership.
- Empty/stale scenario: select the correct run/actor; changing scope invalidates private
  UI caches. Archived or expired actor contexts cannot keep writing.
- Workspace keeps loading: reads and session bootstrap now stop after 20 seconds with
  an actionable error, rather than spinning indefinitely. Use **Retry connection** or
  **Try again**; for an expired actor use **Choose or renew my demo role**. Do not silently
  fall back to another run or account. A command timeout can mean the change completed;
  refresh its status before retrying. Commands are not automatically retried by the client.
- Tabs reload: valid recent views are retained only in memory, scoped to account/company/
  run/actor and host. Returning displays saved data immediately and revalidates it.
  Successful background refresh is silent. A discreet stale-data notice and retry action
  appear only when refresh fails. Denied access discards cached data; logout clears
  it. Five-minute retention and an 80-entry inactive eviction target bound the cache.
- Interpretation says `review_required`: this is a stopped processing job, not a plan
  approval. The new conversation shows **Processing stopped** with the safe reason.
  For eligible jobs use **Review retry options**, enter what changed, confirm provider
  use, then **Retry saved request**. Keep the existing request; do not create duplicates.
  `model_output_truncated` means the provider hit its response budget, not invalid login.
  The gateway now records a model-compatible, bounded-thinking policy without raising
  the total response cap. It still rejects incomplete output; it never repairs missing
  structured fields by guessing. A successful interpretation is not a checked schedule.
- The isolated Northstar demo currently has typed planning authority for its approved
  launch intake only. Use **Prepare Northstar launch** on Home for that scenario. A legacy
  free-form software-release/onboarding request cannot be converted into that authority
  by retrying or editing its stored text. Keep its history; start the explicitly supported
  launch separately when ready. General questions remain available through **Ask question**.
- Home/Projects shows "Failed to fetch": inspect API logs as well as tunnel readiness.
  An unhandled backend 500 can appear as a browser network/CORS error. Older projects
  legitimately have a NULL `goal_label`; the read model now converts only that NULL to
  empty display text without changing stored rows. Do not reset or reseed the database.
- Credential JSON is pasted but **Validate and store securely** is disabled: first select
  or create an owned **Live** workspace using **Switch demo role**, then return to **Settings > AI &
  credentials**. Validate the JSON and explicitly bind the returned credential version.
  An initial provider lookup with no profile now returns an empty setup state; it is not
  a database error. The run-selection requirement remains intentional.
  Authored modes cannot bind a live credential; the UI now explains this and disables
  binding rather than sending a request that looks like an ownership failure.
- AI unavailable: check the selected run's explicit credential binding and model validation.
- File queued/quarantined: inspect worker/scanner readiness; do not manually mark it clean.
- Stale plan/version: refetch and review the new exact version rather than retrying a
  different payload under the same idempotency key.
- Native shortcut conflict/denied microphone: change or disable the shortcut; typing is
  always available. Browser behavior is not native acceptance evidence.

For these API-only compatibility fixes, rebuild just the API from the repository root;
keep the existing worker, scanner, tunnel and registrar running:

```powershell
docker compose --env-file deploy/local-host/.env --env-file deploy/local-host/.env.runtime -f deploy/local-host/compose.yaml up -d --build --no-deps --wait --wait-timeout 90 api
```

No migration, scenario reprovisioning, Edge redeployment or desktop rebuild is required
for those two earlier read-path fixes alone. Retry Home/Projects after API readiness returns.

### Apply the planning, role and cached-navigation follow-up

These later changes also include desktop and worker code. They are local on
`feat/alto-product`; GitHub publication is not required to run them locally.

1. Review/apply the additive `20260927034000_alto_job_lease_renewal_result.sql` migration
   using the existing linked project and your normal operator credentials. Do not reset
   or reprovision the existing schema or scenario. Inspect the dry run before pushing:

   ```powershell
   npm.cmd exec supabase -- migration list --linked
   npm.cmd exec supabase -- db push --dry-run
   npm.cmd exec supabase -- db push
   ```

   Only `20260927034000` should be pending against the founder's recorded 41-migration
   deployment. If the dry run lists older migrations, missing history or unexpected changes,
   stop and reconcile that difference before applying anything.

   The new migration fixes ordinary job lease renewal reporting the result of an unrelated
   outbox update. It preserves owner/token/expiry/run/actor fences and existing privileges.
   The earlier verification did not apply this change. During the later autonomous-planning
   follow-up, the founder separately approved it: migration history and dry run showed
   only this file pending, application succeeded, and the runtime definition was confirmed.
   Check your target's history before rerunning; do not attempt to reapply an existing version.

2. Rebuild only the API and worker; retain the current scanner, registrar and tunnel:

   ```powershell
   docker compose --env-file deploy/local-host/.env --env-file deploy/local-host/.env.runtime -f deploy/local-host/compose.yaml up -d --build --no-deps --wait --wait-timeout 90 api worker
   ```

3. Run the current desktop code from the repository root:

   ```powershell
   npm.cmd run dev:desktop
   ```

   A running development window normally refreshes automatically. An already installed
   older executable does not acquire local source changes: rebuild/reinstall it separately
   if you prefer packaged use. Browser-only development uses `npm.cmd run dev:web`.

4. Click **Switch demo role** in the sidebar, select **Explore as manager** or
   **Explore as employee**, and retain your existing workspace. Selecting a demo role
   makes no model call and does not change real company-account permissions. Reusing the
   existing Live workspace preserves its explicitly bound credential version.

5. Managers start from Home. Use the supported Northstar launch for this demo, or open
   an existing saved request from **Plan review**. Questions, stopped processing, exact
   plan review and final commitment are separate states in the same conversation.
   Only explicit final commitment assigns work. Employees see assigned work after that.

The second approved Live retry resolved the original response truncation and saved an
admitted 17-task interpretation. Its legacy intake did not match Northstar's supported
typed authority, so materialization stopped with no snapshot or plan. It is not evidence
that the complete Live planning/approval workflow passed. At that earlier checkpoint,
no additional Google retry, approval or commitment was performed to work around that stop.

### Autonomous planning, activity and branding follow-up

Use the same API/worker rebuild and desktop launch above. No Edge Function changes are
needed. The lease-renewal migration `20260927034000` was applied to the founder's linked
project with explicit approval on September 27. Live verification then exposed a separate
model-checkpoint defect, addressed by `20260927035000_alto_model_run_generated_scope.sql`.
The founder separately approved migration 35000; it was applied to the linked project on
September 27 after a one-migration dry run. A read-only catalog comparison confirmed the
exact corrected definition and unchanged permissions/security settings; the final dry run
reported no pending migrations. No restart or Edge redeployment is needed for this SQL
correction. Full Live plan completion still requires a separately authorized paid check.

- A new supported Live request proceeds through interpretation, source checks and fixed
  schedule verification without requiring a click between stages. Correctable model-output
  errors can consume up to three interpretation attempts in the existing durable ledger;
  fixed-plan authoring separately permits at most five immutable candidate versions. These calls can
  incur Google charges. Attempts are not reset, and SDK retries remain one call per attempt.
- The exact pinned source manifest and selected versions are authenticated before finite
  interpretation admission. Wrong task eligibility, omitted catalogue entries and similar
  model-representation errors are recorded as rejected outputs and can be regenerated.
  Missing permissions, changed sources, real business questions and exhausted limits still
  stop. ALTO does not invent authority or silently replace model output with a saved schedule.
- A small circle indicates actual queued/active/scheduled-retry work. It stops when a
  proposal or a decision is ready, processing fails, or current status is unavailable.
  The adjacent **Progress summary** uses only saved stage state to explain what is happening,
  what is complete and what happens next. It is an operational summary, not the model's
  hidden reasoning, and it never displays raw provider output or private source content.
  Cached tabs refresh silently; only a failed refresh needs a visible recovery notice.
- Old stopped requests remain immutable history. A candidate already admitted under an
  older version is not silently rewritten by this change. Do not repeatedly click Retry
  on an old materialization failure expecting a new model interpretation.
- Final review and **Commit plan** remain explicit. Automatic processing does not assign
  work. The shared in-app logo now uses `docs/design/LOGO.jpeg` unchanged; old installed
  executables need a separate rebuild to acquire desktop changes.
- Before commitment, project-graph nodes are proposal previews. Their approved brief and
  work record do not exist yet, so those actions are disabled and labelled as available
  after commit. Once a plan is committed, the same inspector exposes the real task record.

Two separately approved new Live requests are recorded in the
[implementation journal](alto-implementation-journal.md). The second automatically repaired
its interpretation and saved a source-checked snapshot, but stopped during model-result
persistence with no saved plan. The database correction does not reopen terminal records
or recover an unknown provider result. A further new paid verification needs separate
authorization; neither existing request should have its attempt count reset.

### Repeated `fixed_plan_not_verified` follow-up

The later request `29ce7906-affb-42a5-ae9b-1aebdd519763` is a different failure from the
older ambiguous checkpoint. Its two model proposals were saved: both violated resource
constraints, and the third response was truncated. In particular, E1 crossed Alex's
12:00–13:00 unavailable interval. The old repair scope used only a sufficient solver
conflict subset and incorrectly excluded that known-invalid task from the first revision.

The correction supplies all confirmed failed rules and bounded offending intervals for
repair, preserves unrelated work/permissions, and explains rejected schema responses.
Processing details now distinguish **Worker attempts** from **AI attempts recorded**, with
safe final-error explanations. Neither count is a provider billing receipt.

Use the same API/worker rebuild and desktop launch above to deploy this code-only change;
no SQL migration or Edge deployment is needed. The host bundle adds
`COORDINATION_GEMINI_PLAN_MAX_OUTPUT_TOKENS=32768` for full schedules only, keeping the
five-version authoring bound and other operation caps. An explicit lower value overrides
that ceiling; outside Compose, omitting it retains `COORDINATION_GEMINI_MAX_OUTPUT_TOKENS`.
Future Live responses can use more output tokens and incur higher charges. This does not
retry old jobs, recreate lost output, or authorize another paid verification run.

On September 27 this follow-up was built into the founder's local API and worker;
both returned healthy. Restart the development desktop if its source changes have not
refreshed. An older installed executable still needs a separate rebuild. The saved
failed request stays stopped; it is not retroactively repaired. A new paid Live run
was not performed during this fix.

A separate read-only host check found the registrar unhealthy before and after the
rollout: its existing Quick Tunnel hostname failed DNS resolution inside the container,
while the internal API returned HTTP 200. This can prevent installed clients from
discovering the host and is separate from schedule verification. No tunnel, registrar,
DNS settings or host endpoint lease were changed as part of this planning correction.
That network failure was subsequently diagnosed and repaired in the
"Registrar waiting / rejected public tunnel" follow-up above. It did not require resetting
the workspace or recreating credentials.

Live Teams/Outlook/SharePoint ingestion is not implied by a fixture connection card.
Synthetic connectors are visibly labelled. Signing/notarisation, installed Windows/macOS
acceptance, a hosted migration dry run, actual provider calls and connected external-account
tests require their own recorded evidence and credentials/hardware.

References used for implementation boundaries: [ClamAV stream protocol](https://docs.clamav.net/manual/Usage/ClamdProtocol.html),
[Supabase signed uploads](https://supabase.com/docs/reference/javascript/file-buckets-createsigneduploadurl),
[Gemini bounded audio input](https://ai.google.dev/gemini-api/docs/generate-content/audio),
[Tauri global shortcuts](https://v2.tauri.app/plugin/global-shortcut/).

## Repeat local verification safely

The ordinary regression suite does not require a hosted project:

```powershell
npm run test:desktop
npm run test:backend
npm run test:host
npm run lint
npm run typecheck
npm run build
services/backend/.venv/Scripts/python.exe scripts/check_repository.py
services/backend/.venv/Scripts/python.exe supabase/scripts/verify_migrations.py
```

The opt-in `services/backend/tests/alto_workspace_smoke.py` and
`services/backend/tests/alto_planning_smoke.py` use a separately provisioned disposable
Postgres database on **localhost:55439**. They deliberately refuse other targets. Apply
the full migration chain and synthetic anchors/template there first; set the explicitly
named `ALTO_DISPOSABLE_DB_URL` privately. These scripts create synthetic Auth records
and least-privileged test logins only in that disposable database. Run them serially:
the queue is intentionally global and simultaneous smoke workers can claim each other's
jobs. They do not exercise real Supabase sign-up/JWT issuance, a hosted Storage service
or live Gemini. Never redirect them to an existing local or hosted Supabase instance.
The retained local integration container was stopped after verification without deleting
its records; on this workspace it can be restarted with
`docker start alto-db-integration-20260926` before an explicitly intended local rerun.

```powershell
$env:PYTHONPATH = 'services/backend/src'
services/backend/.venv/Scripts/python.exe services/backend/tests/alto_workspace_smoke.py
services/backend/.venv/Scripts/python.exe services/backend/tests/alto_planning_smoke.py
```
