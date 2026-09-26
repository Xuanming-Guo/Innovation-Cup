# Migration and forward-repair policy

Repository migrations are authoritative and append-only after merge. There are no handwritten
down migrations: destructive rollback can re-expose old security behavior or lose audit data.
Fix a defect with a later timestamped repair migration using expand/backfill/validate/constrain
steps where populated data exists.

## Before a hosted application

1. Check out a clean, reviewed `main` commit and record its full SHA.
2. Run `npm exec supabase -- migration list --linked` and confirm hosted history is an exact
   prefix of the files in `migrations/`. Stop on drift.
3. Run `npm exec supabase -- db push --dry-run` and review the exact SQL and target project.
4. The founder runs `npm exec supabase -- db push` against the intended linked project.
5. Re-run `migration list --linked`; do not seed production and never use `db reset --linked`.
6. Deploy `storage-ticket` separately and configure its server-only secrets in Supabase project
   secrets. Keep `app` absent from Data API exposed schemas.
7. Record the environment alias, full repository SHA, ordered migration versions and hashes,
   function version, operator role alias and UTC time in the deployment ledger. Record no URL,
   password, API key or personal identity.
8. Using the migration owner, set `repository_commit` and `environment_label` for the newly
   applied rows in `app_private.migration_contract`. The value must be the reviewed 40-character
   commit SHA; runtime roles cannot modify this table.

`supabase migration repair` changes migration history only; it does not apply or undo SQL. Use
it only after independently proving the database schema already matches the referenced file and
recording that incident. Dashboard-only schema edits are drift, not migrations.

## Runtime login provisioning

The migrations create `coordination_api` and `coordination_worker` as `NOLOGIN`, non-owner,
non-superuser, non-`BYPASSRLS` group roles. Provision a separate `NOINHERIT` environment login
through the database administrator or secret-management process, grant it exactly one group
role with `SET TRUE` and `INHERIT FALSE`, and store its password only in the deployment secret
store. For example, the API login receives `GRANT coordination_api TO <api_login> WITH INHERIT
FALSE, SET TRUE`; use an environment-specific identifier, never the placeholder literally. The
API explicitly uses `SET LOCAL ROLE coordination_api` inside each transaction. The migration
owner can assume a runtime role for migration verification but is never an application runtime
credential.

## Reconciliation evidence

`migration-manifest.json` records each repository file hash, while Supabase records applied
versions in `supabase_migrations.schema_migrations`. `scripts/verify_migrations.py` fails if an
existing migration changes, disappears or is reordered. Together with the external deployment
ledger's commit SHA, those records identify exactly which reviewed bytes were applied.
