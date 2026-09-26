# Supabase boundary

This is the only canonical Supabase tree in the repository. It contains local configuration,
ordered migrations, deterministic reference seed data, database tests, Edge Functions and
manual-application guidance. It contains no linked-project metadata or credential value.

## What this slice implements

- Supabase Auth identities resolved to current company membership in FastAPI.
- A non-exposed `app` schema for companies, teams, employees, sources and private-file metadata.
- Separate non-login API and worker roles that own no business table and cannot bypass RLS.
- Composite company foreign keys and fail-closed RLS for trusted direct Postgres access.
- Private quarantine/final buckets and a short authenticated Storage-ticket Edge Function.
- Manager planning requests, pinned source selections, bounded excerpts, retrieval/model run
  ledgers, immutable candidate contracts, clarifications and viewer-safe trace steps.
- Immutable validated constraints and canonical planning snapshots, solver runs with native and
  application status, source-linked diagnoses, independently validated proposals, placements and
  concrete schedule blocks.
- Exact planning/disclosure approval requirements, immutable decisions with expiry, current
  authority checks, revision-serialized atomic plan commitment, exclusion-protected committed
  human effort, approval-use evidence, audit events and transactional outbox intents.
- Task-scoped employee access, exact approved-brief binding, lifecycle events, immediate workload
  state, versioned reviewer policies and submissions, worker-only file-scan evidence, exact-version
  review, correction privacy and accepted familiarity/effort evidence.
- Deterministic synthetic company anchors and a guarded demo reset.

The Edge Function validates a real user session, runs only the narrow ticket functions as the
`authenticated` database role, and uses its server-only admin client solely to sign the exact
authorised object operation. A signed upload token may remain usable for Supabase Storage's
provider-defined lifetime; the ten-minute application intent prevents late finalisation but
cannot recall the underlying token. Download links default to 60 seconds and remain usable
until expiry. High-sensitivity downloads need a re-authorising proxy rather than a signed URL.

## Local commands

From the repository root, with Docker running:

```powershell
npm.cmd exec supabase -- start
npm.cmd exec supabase -- db reset --local
npm.cmd run test:supabase:db
npm.cmd run test:supabase:functions
python supabase/scripts/verify_migrations.py
```

`db reset --local` is destructive only to the local Supabase stack. Never substitute `--linked`.
The function test requires Deno; database tests use the project-pinned Supabase CLI.

To seed memberships for existing synthetic Auth users, copy `.env.example` to an untracked
environment file and provide `DEMO_MANAGER_USER_ID`, `DEMO_EMPLOYEE_USER_ID`, and a
migration/seed-operator `SUPABASE_DB_URL`, then run:

```powershell
node scripts/backend.mjs python supabase/scripts/demo_tenant.py seed
```

The script creates no Auth user and stores no password. Create synthetic `.invalid` accounts
through Supabase Auth first; never reuse a personal or customer account.

## Hosted application boundary

The founder applies hosted migrations manually. Follow [MIGRATIONS.md](MIGRATIONS.md) exactly.
The app must not deploy functions or change a linked database merely because this directory is
present. Hosted schema state, function deployment and Storage bucket state are separate facts
and must all be recorded.
