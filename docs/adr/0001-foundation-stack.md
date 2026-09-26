# ADR 0001: Native and hosted application foundation

- **Status:** Superseded in part by [ADR 0002](0002-company-gemini-byok-and-portable-compute.md)
- **Date:** 26 September 2026
- **Issue:** [#6](https://github.com/Xuanming-Guo/Innovation-Cup/issues/6)

## Decision

Use one npm workspace for a Tauri 2 and React/TypeScript/Vite desktop, and one uv-managed
Python package with separate FastAPI and worker process entrypoints. The API and worker share
domain code but remain separately deployable. Both use one backend container image with a
runtime command override.

Target Node 24, Rust 1.94 and Python 3.11–3.13. Commit npm, Cargo and uv lockfiles. The
desktop receives only public configuration. Runtime credentials are supplied through the chosen
host's secret mechanism or Supabase and are never bundled into Vite output. Per-company Gemini
keys follow the Vault workflow in ADR 0002.

The Cloud Run service and WorkerPool YAML files are optional deployment examples for the
request-driven API and continuously allocated worker boundary. Queue consumption, Supabase
access, Gemini calls and Z3 are deliberately absent from this foundation and are added only by
their dedicated issues.

## Consequences

- The desktop can be built without Python, Z3 or provider credentials.
- The API and worker can be tested independently.
- Product screens remain visibly unavailable until their real backend paths exist.
- Native support claims still require installed-artifact testing on each declared target.
