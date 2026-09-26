# Local development

## Prerequisites

- Node.js 24 and npm 11
- Rust 1.94 with the platform prerequisites documented by Tauri
- Python 3.11-3.13
- uv 0.11.x
- Optional for later database work: Supabase CLI and Docker

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

The native check requires the host platform's Tauri prerequisites. To build the Windows NSIS
installer locally, run:

```powershell
npm.cmd run tauri --workspace @coordination/desktop -- build --bundles nsis
```

The installer is written under `apps/desktop/src-tauri/target/release/bundle/nsis/` and build
outputs remain untracked. A successful build is not an installed-app smoke test.
