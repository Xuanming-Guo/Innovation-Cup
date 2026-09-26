# Local development

## Prerequisites

- Node.js 24 and npm 11
- Rust 1.94 with the platform prerequisites documented by Tauri
- Python 3.11-3.13
- uv 0.11.x
- Docker Desktop for local Supabase database tests
- Deno 2.9.x for Edge Function checks

The Supabase CLI is project-pinned as an npm development dependency; do not install an
untracked global version for repository verification.

On Windows PowerShell installations that block `npm.ps1`, invoke `npm.cmd` instead of changing
the machine-wide execution policy.

## Install and inspect

```powershell
npm.cmd ci
uv sync --project services/backend --locked
npm.cmd run doctor
```

Copy the relevant `.env.example` file to an untracked `.env` only when a runtime needs it.
The foundation runs without provider credentials. Never place a Gemini key or privileged
Supabase credential in `apps/desktop` or any `VITE_` variable.

For local identity and database work, copy `services/backend/.env.example` and
`supabase/.env.example` to untracked environment files and fill only local values. The desktop
may eventually contain the Supabase project URL and publishable key, which are public client
configuration, but it must never contain the database URL, secret/service-role key or Gemini
credential.

## Run the foundation

In separate terminals:

```powershell
npm.cmd run dev:api
npm.cmd run dev:worker
npm.cmd run dev:desktop
```

For a browser-only component preview use `npm.cmd run dev:web`; that is not evidence that the
native app works.

## Issue-level verification

```powershell
npm.cmd run check
cd apps/desktop/src-tauri
cargo test --locked
cargo check --locked
```

For changes to migrations, RLS or Edge Functions, run the dedicated boundary suite with Docker
and Deno available:

```powershell
npm.cmd exec supabase -- db start
npm.cmd run test:supabase:db
npm.cmd run test:supabase:functions
python supabase/scripts/verify_migrations.py
```

The database tests rebuild their test database from ordered repository migrations. They do not
connect to a linked or hosted project.

The native check requires the host platform's Tauri prerequisites. To build the Windows NSIS
installer locally, run:

```powershell
npm.cmd run tauri --workspace @coordination/desktop -- build --bundles nsis
```

The installer is written under `apps/desktop/src-tauri/target/release/bundle/nsis/` and build
outputs remain untracked. A successful build is not an installed-app smoke test.
