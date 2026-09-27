# Coordination Engine

[![Repository quality](https://github.com/Xuanming-Guo/Innovation-Cup/actions/workflows/quality.yml/badge.svg)](https://github.com/Xuanming-Guo/Innovation-Cup/actions/workflows/quality.yml)

Coordination Engine is a human-led company coordination system proposed for the Recruit Holdings Innovation Cup 2026. It turns an authorised organisational decision into a source-grounded, capacity-feasible and permission-aware change to existing work.

> **Current status:** buildable application foundation with identity/tenancy, typed interpretation, trusted candidate materialisation, finite planning, exact approval/commitment, employee execution and durable coordination slices. It includes company-scoped Google Gemini BYOK through Supabase Vault using either a Gemini Developer API key or Vertex AI service-account JSON, connected manager/employee/company-settings surfaces, leased Postgres jobs, bounded retry/review/cancellation and manager recovery, durable Gemini/Z3 dispatch, transactional assignment/brief notifications, private Realtime refresh and a single-laptop hosted-demo mode with authenticated endpoint discovery. Native CI has produced checksummed Windows x64, macOS arm64 and macOS Intel artifacts for commit `ec45bcbc35a5b912b0e27178f48f2e29a1df46f0`; they are unsigned/ad-hoc and have not been installed-smoke-tested. Hosted migration 15 is present, the corrected compact structured-output contract has completed live synthetic Vertex calls, and the manager intake now supplies an explicit deadline without inventing priority policy. The complete installed manager-to-employee workflow still requires a repeated run. The legitimate clarification answer/resume path and cross-request action inbox remain tracked in issue #51. File scanning remains fail-closed until a real scanner is configured. Signed/notarised public releases, live connectors, benchmarks and customer validation are not implemented yet. See [implementation status](docs/implementation-status.md).


## Product idea

A manager describes the desired outcome or change in natural language. The system retrieves the permitted commitments, sources, priorities, deadlines, dependencies and capacity it already knows, then asks only for genuinely missing information or decisions that require explicit human authority, including approval of an employee-shareable brief. Gemini proposes typed task contracts; trusted code validates their evidence, meaning and authority before compiling admitted constraints into a finite Z3 scheduling model. The system explains the proposed changes, obtains the required authority and commits approved changes consistently. Employees then receive appropriate instructions, submit work and participate in later replanning.

The product is not an all-knowing AI manager. Models interpret and explain; trusted code enforces identity, authority and supported constraint types; Z3 constructs or checks schedules inside the admitted model; an independent validator checks the concrete schedule; humans or explicitly configured policy authorise material changes.

```text
Authorised sources
  -> versioned evidence
  -> candidate task contracts
  -> validated constraints
  -> immutable planning snapshot
  -> trusted Z3 model
  -> independently validated schedule
  -> approval and atomic commitment
  -> authorised employee task
  -> exact-version submission and review
```

## Intended architecture

| Area | Planned technology and boundary |
|---|---|
| Desktop | Tauri 2 with React, TypeScript and Vite |
| Backend | Python, FastAPI and Pydantic with separate API and worker processes |
| Hosted compute | Portable OCI image with separate FastAPI and durable-worker processes; the selected demo mode runs them on one laptop behind a free HTTPS tunnel |
| Planning | Server-side `z3-solver` with deterministic compilation and validation |
| Model API | Google Gemini through a typed server-side adapter; each company selects a Developer API key or Vertex AI service account and the initial model default is configurable |
| Platform | Supabase backend: Auth, Postgres, Vault, private Storage, Realtime and durable queue/job state |
| Jobs and writes | Durable jobs, transactional outbox, idempotent connector actions and reconciliation |
| Native targets | Windows 11 x64 and macOS 13+ on Apple Silicon and Intel |

Supabase is the shared backend platform and system of record. FastAPI and the durable Python worker run from the same portable container image with different commands. For the selected no-hosting-bill demo, one cloned Windows or macOS laptop runs the Docker Compose host bundle; installed clients authenticate with Supabase and discover its current HTTPS tunnel through a short-lived company lease. A company administrator selects and verifies either that company's Gemini API key or a downloaded Vertex service-account JSON object through the authenticated Connections screen. Vault encrypts the credential, and only the worker can resolve it under current tenant context. Pasted Python is never executed. Employees call the application API, never Google directly. No database or provider credential is shipped in the desktop application.

The initial demonstration connects software and HR operations teams through one shared specialist. Cross-team capacity may be used without disclosing another team's private context.

## Documentation

| Document | Purpose |
|---|---|
| [Implementation master prompt](docs/implementation_master_prompt_v2.md) | Self-contained engineering handoff. Part A is the build contract; Part B embeds the complete specification. |
| [Product and architecture specification](docs/coordination_engine_master_v2.md) | Authoritative product reasoning, policies, architecture, schema, evaluation protocol and evidence register. |
| [Version 2 changelog](docs/CHANGELOG_v2.md) | Maps substantive revisions and later clarifications. |
| [Formatted specification](docs/coordination_engine_master_v2.docx) | Formatted Version 2 snapshot for reading and presentation. The Markdown specification is authoritative and contains the current clarification. |
| [GitHub workflow](docs/development/github-workflow.md) | Issue, branch, commit, pull-request, merge and repository-rules conventions. |
| [Tenant and Storage boundary](docs/security/tenant-and-storage-boundary.md) | JWT, current-membership, RLS, private-file and hosted-secret boundaries. |
| [Interpretation boundary](docs/architecture/interpretation-boundary.md) | Permission-bounded retrieval, Gemini gateway, candidate admission and failure behavior. |
| [Planning boundary](docs/architecture/planning-boundary.md) | Validated constraints, immutable snapshots, Z3 scopes, diagnosis and independent validation. |
| [Approval and commitment boundary](docs/architecture/approval-commit-boundary.md) | Exact digest binding, authority rechecks, concurrency, atomic commit and disclosure separation. |
| [Employee workflow boundary](docs/architecture/employee-workflow-boundary.md) | Permission-safe task views, lifecycle concurrency, private submissions and exact-version review. |
| [Durable coordination boundary](docs/architecture/durable-coordination-boundary.md) | Leases, retries, outbox delivery, notifications, private refresh and operational health. |
| [Backend deployment](docs/development/backend-deployment.md) | Portable API/worker hosting, Supabase connectivity and company BYOK operations. |
| [Production and hosted-demo setup](docs/development/production-setup.md) | Exact Supabase, runtime-role, Edge Function, API/worker, environment and desktop setup order. |
| [Single-laptop hosted-demo ADR](docs/adr/0003-single-laptop-hosted-demo.md) | Why the free demo uses one Docker laptop, a Quick Tunnel and authenticated endpoint discovery. |
| [Google credential modes ADR](docs/adr/0004-google-ai-credential-modes.md) | API-key and Vertex service-account BYOK, validation, storage and worker boundaries. |
| [Native release matrix](docs/release-matrix.md) | Windows/macOS artifact targets, checksums, signing state and honest smoke-test boundary. |
| [Agent instructions](AGENTS.md) | Repository context and non-negotiable working rules for coding agents. |

## Delivery priorities

- **P0:** authenticated human workflow, tenant isolation, profiles and capacity, shareable briefs, typed interpretation, Z3 scheduling, independent validation, exact approval binding, atomic commitment, durable actions, employee submission/review, evaluation fixtures and native Windows/macOS delivery.
- **P1:** narrowly authorised automatic repairs, richer estimates, Japanese localisation, additional live connectors, evaluated alternatives and one bounded drafting executor with a human owner and reviewer.
- **Deferred:** unrestricted autonomous agents, recruitment decisions, payroll, surveillance, global employee ranking, arbitrary code execution and universal enterprise ingestion.

## Repository layout

```text
.github/                 Issue forms, PR template, ownership and CI
docs/                    Product, architecture and implementation specifications
  development/           Repository workflow and engineering process
scripts/                 Dependency-free repository checks
apps/desktop/            Tauri 2 and React/TypeScript native desktop foundation
services/backend/        FastAPI API and separate durable-worker process boundary
deploy/cloud-run/        Optional provider-specific example; not a product dependency
deploy/local-host/       Selected single-laptop hosted-demo Compose bundle and safe env template
supabase/                Migrations, seeds, database tests, Edge Functions and safe operator tooling
AGENTS.md                 Agent operating context
README.md                 Project entry point and honest status
```

The target application layout is defined in the implementation master prompt and is introduced through reviewed vertical slices. All Supabase CLI configuration, migrations, seeds, database tests, Edge Functions, shared function code, function tests and safe environment examples live under root `supabase/`. Company Gemini API keys or Vertex service-account JSON credentials are installed at runtime through the authenticated application and encrypted in Supabase Vault. Deployment environment variables contain only backend/runtime configuration and privileged Supabase connectivity; no real secret is committed. Repository migrations remain authoritative when the founder applies them manually to hosted Supabase.

## Contributing

Development follows short-lived branches and pull requests:

1. Open or select an issue with explicit acceptance criteria.
2. Create a branch such as `feat/123-plan-review`, `fix/456-tenant-check` or `docs/source-to-z3`.
3. Use Conventional Commit subjects such as `feat(planner): add typed eligibility constraints`.
4. Open a focused PR, link the issue, complete the template and include actual test evidence.
5. Resolve required checks and review comments.
6. Squash-merge to protected `main` and delete the branch.

Run the current repository contract locally with:

```powershell
python scripts/check_repository.py
```

Install the locked foundation dependencies and inspect local prerequisites:

```powershell
npm.cmd ci
uv sync --project services/backend --locked
npm.cmd run doctor
```

Run the API, worker and native desktop in separate terminals:

```powershell
npm.cmd run dev:api
npm.cmd run dev:worker
npm.cmd run dev:desktop
```

Laptop-host desktop installers bake in discovery mode, the Supabase project URL, publishable key
and company UUID, so employees do not configure them and tunnel restarts do not require a rebuild.
Static hosted deployments may still bake a stable HTTPS API origin. The release workflow refuses
to build when required public values are missing or malformed. **Deployment** remains an advanced
local/operator override; no privileged credential belongs in the desktop.
Follow the
[production setup runbook](docs/development/production-setup.md) before a connected demo.

Run the issue-level application check with `npm.cmd run check`. With its database configured,
the worker verifies the durable schema and consumes leased jobs; Gemini work additionally requires
the current company to have a verified Google credential. See [local development](docs/development/local-development.md),
[backend deployment](docs/development/backend-deployment.md) and the [complete GitHub workflow](docs/development/github-workflow.md).

## Security and evidence

Do not commit credentials, customer data or real employee information. Use synthetic fixtures until the necessary access, privacy and retention decisions are approved. Report security concerns through the process in [.github/SECURITY.md](.github/SECURITY.md), not a public issue containing exploit details.

Every implementation claim must be tied to observable evidence. Labels such as implemented, live, tested, supported or optimal must not be used when the capability is only specified, simulated, compiled or not run on the stated platform.
