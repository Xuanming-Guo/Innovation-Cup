# Production and hosted-demo setup

This runbook turns a reviewed repository commit into one hosted Supabase project, one FastAPI
service, one continuously running worker and preconfigured desktop installations. It deliberately
keeps schema application, credentials and public deployment actions under the founder's control.

Production installers contain the API origin, Supabase project URL, publishable key and company
UUID at build time. Employees do not enter them. These values are public identifiers, but the
publishable key is safe only because Supabase Auth, RLS and least-privilege grants enforce access;
it is not a substitute for authorization. Never embed a database password, Supabase secret or
service-role key, migration-owner DSN, runtime-role DSN or Gemini key.

## 0. Exact configuration locations

| Scope | Exact location | Values |
|---|---|---|
| GitHub native release | Repository **Settings -> Secrets and variables -> Actions -> Variables** | `VITE_API_ORIGIN`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`, `VITE_DEFAULT_COMPANY_ID`; optional `VITE_PRODUCT_NAME` |
| Local desktop build | Ignored `apps/desktop/.env.production.local` for a production-mode build, or `apps/desktop/.env.local` for local Vite/Tauri development | The same five public `VITE_` values; use `apps/desktop/.env.example` as the template |
| API deployment | API service environment settings on the chosen container host | The API column in section 6; `COORDINATION_DATABASE_URL` uses the API login |
| Worker deployment | Worker service environment settings on the chosen container host | The worker column in section 6; `COORDINATION_DATABASE_URL` uses the worker login |
| Local API/worker | Ignored `services/backend/.env` | Copy `services/backend/.env.example`; the repository launcher loads this exact file |
| One-off demo provisioning | Current PowerShell process environment | `COORDINATION_ENVIRONMENT`, `SUPABASE_DB_URL`, `DEMO_MANAGER_USER_ID`, `DEMO_EMPLOYEE_USER_ID`; `supabase/.env.example` is a reference, but the provisioning command does not automatically load `supabase/.env` |
| Hosted Edge Function | Supabase-managed defaults plus project Edge Function secrets | Supabase injects its own URL/key/JWKS/database variables; set only optional `STORAGE_DOWNLOAD_TTL_SECONDS` with the CLI command in section 4 |
| Local Edge Function | Ignored `supabase/functions/.env`, passed explicitly with `--env-file` when serving locally | Copy `supabase/functions/.env.example`; never reuse hosted secret values |
| Company Gemini credential | Authenticated desktop **Connections** screen -> FastAPI -> Supabase Vault | One company-owned Gemini Developer API key; it is not a build variable or production process environment variable |
| Supabase CLI link | Generated ignored state under `supabase/.temp/`; CLI login is managed outside the repository | Do not edit or commit either; use `supabase link` from repository root |

Committed configuration and templates are `supabase/config.toml`, `supabase/migrations/*.sql`,
`supabase/seed.sql`, `supabase/functions/storage-ticket/`, `apps/desktop/.env.example`,
`services/backend/.env.example`, `supabase/.env.example` and
`supabase/functions/.env.example`. Real credentials never belong in those files.

## 1. Create and secure the Supabase project

1. Create a hosted Supabase project using PostgreSQL 17 in the region nearest the API/worker.
   Store the project reference, database password and recovery details in a password manager.
2. In **Project Settings → API/Data API**, leave the exposed schemas limited to `public` and
   `graphql_public`. Do not expose `app` or `app_private`.
3. Copy the project URL and the `sb_publishable_...` key. The publishable key is the only
   Supabase key that may be entered into the desktop.
4. In Auth, disable anonymous sign-ins. For a controlled demo, disable public sign-up after the
   two synthetic accounts have been created. Email/password is the implemented login path.
5. Never put the database password, secret key or service-role key into a `VITE_` variable.

### Optional GitHub integration shown in the Dashboard

The CLI workflow below does not require the GitHub integration. If you connect it anyway:

1. Select `Xuanming-Guo/Innovation-Cup`.
2. Enter `.` in **Working directory** because `supabase/` is directly under repository root.
3. Leave **Deploy to production** off for this repository's founder-controlled manual workflow.
4. Automatic preview branching requires the Supabase plan shown by the Dashboard and is not
   required to apply migrations manually.

If **Deploy to production** is enabled, Supabase automatically applies new migrations and deploys
configured Edge Functions and Storage buckets when changes reach `main`. That is a different
operating policy; do not combine it with the manual production push below or assume a merge is
database-neutral.

## 2. Apply the repository migrations in order

From a clean checkout of the reviewed `main` commit:

```powershell
npm.cmd ci
npm.cmd exec supabase -- login
npm.cmd exec supabase -- link --project-ref <project-ref>
npm.cmd exec supabase -- migration list --linked
npm.cmd exec supabase -- db push --dry-run
npm.cmd exec supabase -- db push
npm.cmd exec supabase -- migration list --linked
python supabase/scripts/verify_migrations.py
git rev-parse HEAD
```

Run every command from the repository root (the directory containing `package.json` and the
`supabase/` folder). Find `<project-ref>` in the Supabase project URL: for
`https://abcdefgh.supabase.co`, it is `abcdefgh`. `login` authorizes the CLI; `link` may prompt for
the database password and writes only ignored link metadata. `migration list --linked` identifies
local/remote drift, `db push --dry-run` previews the target changes, and only the subsequent
`db push` changes the hosted database.

Stop if hosted history is not an exact prefix before the push, or if the final list does not match
the eleven files under `supabase/migrations/`. Do not use `db reset --linked`. Do not paste edited
copies into the Dashboard SQL editor: that applies untracked bytes and loses reliable migration
history.

Using the migration-owner connection in the SQL editor, bind the installed rows to the reviewed
commit. Replace both placeholders before running it:

```sql
update app_private.migration_contract
set repository_commit = '<40-character-reviewed-main-commit>',
    environment_label = '<production-or-hosted-demo>'
where repository_commit is null;

select version, name, repository_commit, environment_label, installed_at
from app_private.migration_contract
order by version;
```

The migrations create the private schemas, both private Storage buckets, RLS/grants, durable job
state, private Realtime policy, Vault-backed Gemini credential functions and the two non-login
group roles. Supabase Vault is enabled by the final migration.

## 3. Create separate API and worker database logins

The migrations intentionally create `coordination_api` and `coordination_worker` as `NOLOGIN`
roles. Create one environment-specific login for each process with separate generated passwords.
Run this as the database administrator, replacing names/passwords with your secret-manager values:

```sql
create role coordination_api_prod
  login password '<unique-generated-api-password>'
  nosuperuser nocreatedb nocreaterole noinherit nobypassrls;
grant coordination_api to coordination_api_prod with inherit false, set true;

create role coordination_worker_prod
  login password '<unique-generated-worker-password>'
  nosuperuser nocreatedb nocreaterole noinherit nobypassrls;
grant coordination_worker to coordination_worker_prod with inherit false, set true;
```

Build two TLS Postgres connection strings from those logins. URL-encode the passwords. The API
deployment receives only the API login DSN; the worker receives only the worker login DSN. Test
that each login can connect and `SET ROLE` only to its granted group role. The migration-owner DSN
must not be used by either runtime.

## 4. Deploy the Storage ticket Edge Function

The hosted Edge runtime supplies `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEYS`,
`SUPABASE_SECRET_KEYS`, `SUPABASE_JWKS` and `SUPABASE_DB_URL` automatically. Do not copy those
generated values into the repository. Set only the optional application value and deploy:

```powershell
npm.cmd exec supabase -- secrets set STORAGE_DOWNLOAD_TTL_SECONDS=60 --project-ref <project-ref>
npm.cmd exec supabase -- functions deploy storage-ticket --project-ref <project-ref>
```

Keep JWT verification enabled. Confirm the function is deployed, and confirm the
`coordination-quarantine` and `coordination-private` buckets are private. The function creates
short-lived authorised tickets; it is not a general Storage proxy. File promotion remains
fail-closed until a real scanner/mover is configured.

## 5. Create the synthetic hosted-demo tenant

Skip this section for a real production tenant. The repository currently provides guarded
operator provisioning for the Northstar synthetic demo; general self-service company onboarding
is not implemented.

1. In **Authentication → Users**, create two synthetic `.invalid` email/password users, confirm
   them, and copy their Auth UUIDs. Do not use a personal or customer account.
2. Apply `supabase/seed.sql` to the hosted-demo project once, as the migration owner. It creates
   only the two fixed demo company anchors and no Auth users or passwords.
3. Keep the values in your password manager or an ignored `supabase/.env`; the seed command reads
   the process environment and does not parse that file automatically.
4. Export the four values in the current PowerShell session and run:

```powershell
$env:COORDINATION_ENVIRONMENT = 'demo'
$env:SUPABASE_DB_URL = '<migration-owner-or-seed-operator-dsn>'
$env:DEMO_MANAGER_USER_ID = '<manager-auth-uuid>'
$env:DEMO_EMPLOYEE_USER_ID = '<employee-auth-uuid>'
node scripts/backend.mjs python supabase/scripts/demo_tenant.py seed
```

The configured company ID is `11111111-1111-4111-8111-111111111111`. The manager becomes a
company administrator and can install the company's Gemini key. Remove the local filled env file
after provisioning if your operating process does not require it.

## 6. Deploy the API and worker

Build `services/backend/Dockerfile` once and deploy the same immutable image twice:

- API command: `python -m uvicorn coordination.api.main:app --host 0.0.0.0 --port 8080`
- Worker command: `python -m coordination.worker.main`

The API needs an HTTPS public origin. The worker must remain continuously available; closing the
desktop must not stop jobs. Configure the environment variables in the hosting platform's secret
or environment settings, not in Git or the desktop.

### Required production values

| Variable | API | Worker | Value/source |
|---|---:|---:|---|
| `COORDINATION_ENVIRONMENT` | yes | yes | `production` |
| `COORDINATION_BUILD_COMMIT` | yes | yes | Full 40-character deployed Git commit |
| `COORDINATION_SUPABASE_URL` | yes | recommended | `https://<project-ref>.supabase.co` |
| `COORDINATION_SUPABASE_JWT_ISSUER` | yes | no | `https://<project-ref>.supabase.co/auth/v1` |
| `COORDINATION_DATABASE_URL` | yes | yes | API-role DSN in API; worker-role DSN in worker |
| `COORDINATION_INTERPRETATION_MODE` | yes | yes | `gemini` |
| `COORDINATION_GEMINI_MODEL` | yes | yes | Initially `gemini-3.8-flash`; keep API and worker identical |

### Defaults that may be overridden

| Variable | Default | Purpose |
|---|---:|---|
| `COORDINATION_API_VERSION` | `1.0.0` | Public API compatibility value |
| `COORDINATION_LOG_LEVEL` | `INFO` | Server log level |
| `COORDINATION_CORS_ALLOWED_ORIGINS` | Native Tauri origins plus local Vite origins | Comma-separated explicit origins; never `*` |
| `COORDINATION_SUPABASE_JWT_AUDIENCE` | `authenticated` | Required JWT audience |
| `COORDINATION_SUPABASE_JWT_ALGORITHMS` | `ES256,RS256` | Explicit asymmetric allowlist |
| `COORDINATION_SUPABASE_JWT_LEEWAY_SECONDS` | `30` | Clock-skew allowance |
| `COORDINATION_DATABASE_CONNECT_TIMEOUT_SECONDS` | `5` | Postgres connection timeout |
| `COORDINATION_GEMINI_TIMEOUT_SECONDS` | `20` | Provider request timeout |
| `COORDINATION_GEMINI_RETRY_ATTEMPTS` | `2` | Bounded provider attempts |
| `COORDINATION_GEMINI_MAX_OUTPUT_TOKENS` | `8192` | Model output bound |
| `COORDINATION_GEMINI_MAX_PROJECTION_CHARACTERS` | `150000` | Authorised prompt projection bound |
| `COORDINATION_WORKER_POLL_SECONDS` | `5` | Durable queue polling interval |
| `COORDINATION_WORKER_BATCH_SIZE` | `4` | Jobs leased per worker cycle |
| `COORDINATION_WORKER_LEASE_SECONDS` | `120` | Lease duration |
| `COORDINATION_WORKER_RENEWAL_SECONDS` | `30` | Lease renewal interval; must stay below lease duration |
| `COORDINATION_WORKER_INSTANCE_NAME` | Container hostname | Optional stable worker label |

Do not set `COORDINATION_GEMINI_API_KEY` in production. It is a local/test fallback and production
ignores it. A company administrator enters the production key in **Connections**; the API verifies
model access without company content, Vault stores it, and only the worker resolves plaintext.
The API and worker do not need a Supabase secret/service-role key.

After deployment, require successful responses from `/health/live`, `/health/ready` and `/version`.
`/health/ready` must report both configuration and durable schema ready.

## 7. Bake the public desktop configuration and build installers

After the API exists and the company UUID has been provisioned, add these repository Actions
**Variables** (not Secrets):

| Variable | Exact value |
|---|---|
| `VITE_API_ORIGIN` | Deployed FastAPI HTTPS origin with no path, for example `https://api.example.com` |
| `VITE_SUPABASE_URL` | Project URL, for example `https://abcdefgh.supabase.co` |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | The project's `sb_publishable_...` client key |
| `VITE_DEFAULT_COMPANY_ID` | Provisioned company UUID; the demo value is `11111111-1111-4111-8111-111111111111` |
| `VITE_PRODUCT_NAME` | Optional display name; defaults to `Coordination Engine` |

Open GitHub -> repository **Settings -> Secrets and variables -> Actions -> Variables -> New
repository variable** and create each row. The release workflow validates the four required
values before compilation and refuses to produce a generic installer. It also rejects HTTP,
path-bearing origins, malformed company IDs and keys that are not `sb_publishable_...`, which
prevents accidentally embedding a privileged key.

For a local production build, copy `apps/desktop/.env.example` to the ignored
`apps/desktop/.env.production.local`, fill the same public values, and run the native build. The
**Deployment** screen is retained only as an advanced local/operator override and reset path; a
normally distributed production installer opens ready for sign-in without employee setup.

## 8. Final connected smoke check

1. Install and launch the platform artifact; record the OS and CPU architecture.
2. Confirm the baked API/Supabase/company values are active, then sign in as the synthetic manager.
3. In **Connections**, install and validate the company's Gemini Developer API key.
4. Create a planning request, wait for interpretation/materialisation/Z3 jobs, review the exact
   proposal and approve/commit it.
5. Sign in as the employee on the other platform, receive the authorised task, submit it, then
   review it as the manager.
6. Sign out, restart, exercise offline/reconnect behavior and confirm no privileged key appears in
   logs or the frontend bundle.
7. Record results in the release manifest/test ledger. A compiled artifact is not a passed
   installed-app smoke test.
