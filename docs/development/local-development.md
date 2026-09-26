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
The API and all non-provider tests run without provider credentials. For normal connected use, a
company administrator installs the company's key through **Connections** after authentication.
`COORDINATION_GEMINI_API_KEY` is an optional local/test fallback and is ignored in production.
Never place a Gemini key or privileged Supabase credential in `apps/desktop` or any `VITE_`
variable.

For local identity and database work, copy `services/backend/.env.example` and
`supabase/.env.example` to untracked environment files and fill only local values. The desktop
contains only the Supabase project URL, publishable key and optional non-secret default company ID
for Auth/private Realtime. It must never contain the database URL, secret/service-role key or
Gemini credential.

If those public values are absent during development, the app opens **Deployment** and stores a
validated local override on that device. Production releases fail before compilation when the
four required public values are absent, so employees never need this setup step. Hosted API and
Supabase origins must use HTTPS; loopback HTTP is accepted only for development. Resetting the
screen returns to the compiled `.env` defaults.

## Run the foundation

In separate terminals:

```powershell
npm.cmd run dev:api
npm.cmd run dev:worker
npm.cmd run dev:desktop
```

The worker fails readiness until the durable migration is present. With a cached Supabase desktop
session, private Realtime signals cause the desktop to refetch current session and notifications
through FastAPI; signals themselves contain no plan/task details.

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
npm.cmd exec supabase -- start
npm.cmd run test:supabase:db
npm.cmd run test:supabase:functions
python supabase/scripts/verify_migrations.py
```

The database tests rebuild their test database from ordered repository migrations. They do not
connect to a linked or hosted project.

The backend suite uses a fake typed interpretation gateway and never spends Gemini quota. The
credential endpoint validates model access without sending company content. Live interpretation
evaluation is a separate company-authorised check; record the actual model, prompt/schema
versions, latency and result rather than treating a mocked response as provider evidence.

Planner fixtures use the pinned native `z3-solver` wheel installed by `uv sync`; they need no
network service or API key. The tests exercise finite real solver models and then validate the
returned rows through the separate non-Z3 checker. They are not production performance evidence.

The native check requires the host platform's Tauri prerequisites. To build the Windows NSIS
installer locally, run:

```powershell
npm.cmd run tauri --workspace @coordination/desktop -- build --bundles nsis
```

The installer is written under `apps/desktop/src-tauri/target/release/bundle/nsis/` and build
outputs remain untracked. A successful build is not an installed-app smoke test.
