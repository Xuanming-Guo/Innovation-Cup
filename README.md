# Coordination Engine

[![Repository quality](https://github.com/Xuanming-Guo/Innovation-Cup/actions/workflows/quality.yml/badge.svg)](https://github.com/Xuanming-Guo/Innovation-Cup/actions/workflows/quality.yml)

Coordination Engine is a human-led company coordination system proposed for the Recruit Holdings Innovation Cup 2026. It turns an authorised organisational decision into a source-grounded, capacity-feasible and permission-aware change to existing work.

> **Current status:** buildable application foundation with identity/tenancy, typed interpretation, finite planning and exact approval/commitment slices. The repository contains a Tauri/React manager-review surface, FastAPI service, separate Python worker boundary, ordered Supabase migrations, fail-closed company membership resolution, private Storage ticketing, natural-language planning intake, one server-side Gemini adapter, deterministic candidate admission, an allowlisted Z3 compiler, bounded repair, independent schedule validation, immutable exact approvals, atomic revision-checked commitment, locked toolchains and Cloud Run definitions. These paths are repository-tested but are not claimed as applied to hosted Supabase, exercised with a live Gemini credential or yet connected through the durable worker. Employee workflows, durable outbox processing, signed native releases, live connectors, benchmarks and customer validation are not implemented yet. See [implementation status](docs/implementation-status.md).

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
```

## Intended architecture

| Area | Planned technology and boundary |
|---|---|
| Desktop | Tauri 2 with React, TypeScript and Vite |
| Backend | Python, FastAPI and Pydantic with separate API and worker processes |
| Hosted compute | Google Cloud Run service for FastAPI and a Cloud Run worker pool for durable Python planning work |
| Planning | Server-side `z3-solver` with deterministic compilation and validation |
| Model API | Google Gemini API, called only from trusted server-side code through a typed adapter; configurable initial default `gemini-3.8-flash` |
| Platform | Supabase backend: Auth, Postgres, private Storage, Realtime and durable queue/job state |
| Jobs and writes | Durable jobs, transactional outbox, idempotent connector actions and reconciliation |
| Native targets | Windows 11 x64 and macOS 13+ on Apple Silicon and Intel |

Supabase is the shared backend platform and system of record. A Google Cloud Run service hosts FastAPI and a Cloud Run worker pool runs the durable Python compute tier connected to it: the worker retrieves a permission-bounded source projection, calls Gemini, validates its structured output, compiles trusted constraints, runs Z3 and persists the result to Supabase. A Supabase Edge Function may call Gemini for a short, bounded request, but long-running planning and Z3 work belongs in the worker pool. The Gemini credential is never shipped in the desktop application.

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
deploy/cloud-run/        Reviewable API service and worker-pool definitions
supabase/                Migrations, seeds, database tests, Edge Functions and safe operator tooling
AGENTS.md                 Agent operating context
README.md                 Project entry point and honest status
```

The target application layout is defined in the implementation master prompt and is introduced through reviewed vertical slices. All Supabase CLI configuration, migrations, seeds, database tests, Edge Functions, shared function code, function tests and safe environment examples live under root `supabase/`. Google Cloud, Gemini and privileged Supabase values are supplied later through local/deployment environment variables or secret stores; only descriptive placeholders are committed. Repository migrations remain authoritative when the founder applies them manually to hosted Supabase.

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

Run the issue-level application check with `npm.cmd run check`. The worker currently reports
foundation status and deliberately does not consume jobs. See [local development](docs/development/local-development.md),
the [Cloud Run boundary](docs/development/cloud-run.md) and the [complete GitHub workflow](docs/development/github-workflow.md).

## Security and evidence

Do not commit credentials, customer data or real employee information. Use synthetic fixtures until the necessary access, privacy and retention decisions are approved. Report security concerns through the process in [.github/SECURITY.md](.github/SECURITY.md), not a public issue containing exploit details.

Every implementation claim must be tied to observable evidence. Labels such as implemented, live, tested, supported or optimal must not be used when the capability is only specified, simulated, compiled or not run on the stated platform.
