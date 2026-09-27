# AGENTS.md

## Mission and current reality

Build Coordination Engine: a human-led coordination system that turns an authorised organisational change into a source-grounded, capacity-feasible, permission-aware and low-disruption update to existing work.

The repository contains a buildable Tauri/React desktop with connected manager, employee and company-connections surfaces; a FastAPI service; a leased Python worker; ordered Supabase migrations; a single-laptop hosted-demo bundle with authenticated endpoint discovery; private Storage ticketing; natural-language planning intake; a typed Google Gen AI SDK adapter; company-scoped Gemini API-key or Vertex service-account BYOK backed by Supabase Vault; deterministic candidate admission and materialisation; an allowlisted finite Z3 compiler; bounded authorised repair; independent concrete-schedule validation; immutable ledgers; atomic revision-checked commitment; guarded recovery of side-effect-free terminal planning stages; assignment/approved-brief notifications; and private Realtime invalidation/refetch. Native CI has compiled checksummed Windows x64, macOS arm64 and macOS Intel artifacts, but no installed-app or complete hosted connected smoke test has been recorded. Repository tests are not evidence that migrations/functions were deployed, the laptop-host stack completed a live tunnel, or the corrected structured Vertex contract completed live. A manager-facing clarification answer/resume path and cross-request action inbox (issue #51), a real file scanner, signed/notarised public release, live connectors, benchmarks and validated customer outcomes remain incomplete. Use `docs/implementation-status.md` as the capability ledger and do not infer implementation from document detail or design imagery.

## Required reading and authority

Before planning or implementing product behaviour, read:

1. [Implementation master prompt](docs/implementation_master_prompt_v2.md), including Part A and the embedded Part B.
2. [Standalone product specification](docs/coordination_engine_master_v2.md) when reviewing product or architecture language.
3. [Version 2 changelog](docs/CHANGELOG_v2.md) for the intent behind revisions.
4. [GitHub workflow](docs/development/github-workflow.md) before creating branches, commits, issues or pull requests.

Part A is the implementation contract. The standalone specification is the authoritative Part B source and must remain byte-equivalent to the text between the embedded-specification markers in the implementation prompt. CI enforces this.

The DOCX is a formatted Version 2 snapshot, not an independently maintained source of truth. Regenerate and review it from the authoritative Markdown before external distribution; never copy newer policy from the DOCX back over the Markdown without comparison.

Use the document status labels precisely:

- **CONFIRMED:** founder-selected requirement.
- **DEFAULT:** reversible implementation starting point.
- **HYPOTHESIS:** proposition requiring validation.
- **OPEN:** unresolved policy or product decision.
- **EVIDENCE:** externally sourced fact within its stated scope.
- **TARGET:** proposed threshold, never an achieved result without measurement.

Ask only when an unresolved choice changes authority, privacy, commitments, external access, cost or material scope. Otherwise use the documented conservative default and record the decision.

The root `simulation/` directory is founder-managed reference material outside the application
implementation. Do not read, modify, format, test, move, delete or include it in repository-wide
commands. Scope searches and checks so they explicitly leave that tree alone.

## Product boundary

The initial customer hypothesis is a Microsoft-heavy Japanese software, delivery or operations team with recurring short-horizon changes and shared specialists. The connected demonstration uses software and HR operations teams in one synthetic company. HR work is internal onboarding coordination, not candidate ranking, hiring, payroll or an HR information system.

Human execution is P0. Optional AI execution is a disabled P1 extension limited to explicitly allowlisted tasks with scoped inputs/tools, a budget, timeout, kill switch, accountable human and required reviewer. Never represent agents as employees with unlimited capacity or authority.

Do not build or imply unrestricted autonomous workers, recruiting decisions, payroll, surveillance, personality/work-ethic scoring, global employee ranking, arbitrary shell/network access or universal enterprise ingestion.

## Non-negotiable trust boundaries

Treat source authenticity, source authority, model interpretation, constraint admission, solver feasibility, optimality, business approval, database commitment, external synchronisation and work acceptance as separate claims.

The required pre-solver trace is:

`SourceVersionRef -> CandidateTaskContract -> ValidatedConstraint -> PlanningSnapshot -> CompiledModel`

- Authorise access before retrieval and retain source/version/freshness/authority metadata.
- Retrieve bounded current structured facts and necessary excerpts. Summaries are optional caches, not approved facts.
- Models may propose schema-constrained task contracts, evidence links, assumptions and clarification questions. They may not generate executable Python, SQL, SMT-LIB or arbitrary solver expressions.
- Gemini is the confirmed model API. Route every Gemini call through the server-side typed model gateway; require structured output where applicable and still validate it as untrusted input.
- Trusted code validates tenant IDs, types, units, dates/timezones, cycles, evidence, authority, confidentiality, current permission and confirmation state.
- Unsupported or materially ambiguous hard constraints stop for clarification. Never guess a permissive fallback.
- Freeze an immutable planning snapshot with source, policy, permission, profile, estimate, compiler and company-revision versions plus a canonical digest.
- Compile only allowlisted typed constraint families to Z3 and preserve stable constraint IDs for diagnosis.
- Run pinned insertion before broader authorised repair. Failed local insertion is not global infeasibility.
- Independently validate every returned concrete schedule. Z3 status is not approval and never permits commitment by itself.

Never send raw private cross-team context merely because the planner needs a capacity boundary. Prefer reduced facts such as an unavailable interval and movement authority. Create viewer-safe projections before explanation generation, not after a model has seen all secrets.

## Architecture and data rules

- Desktop: Tauri 2, React, TypeScript and Vite from one codebase.
- Backend: Python, FastAPI and Pydantic; API and worker are separate processes using one domain package.
- Planning: native server-side `z3-solver` with deterministic interpretation validation, compilation and candidate validation boundaries.
- Model provider: Google Gemini API for interpretation, explanations, risk review and the optional bounded executor. Keep the exact model ID configurable and record the model, prompt and safety/configuration versions for each run.
- Platform: Supabase is the shared backend platform and system of record: Auth, Postgres, Vault, private Storage, Realtime and durable queue/job state. Business tables live in a non-exposed `app` schema behind FastAPI.
- Runtime boundary: the durable Python worker normally calls Gemini directly through the official Google Gen AI SDK and runs Z3. Supabase Edge Functions may provide short authenticated gateway operations, but must not own long-running planning, unconstrained optimisation or durable agent execution.
- Hosted-demo boundary: the selected free demo uses exactly one cloned laptop running `deploy/local-host/compose.yaml`. Installed clients authenticate through Supabase before resolving the current short-lived HTTPS endpoint lease. Keep host database credentials in ignored `deploy/local-host/.env`, persist the host instance ID, and never replace authenticated discovery with a user-supplied arbitrary endpoint.
- Credentials: each company administrator selects one Google credential mode: a Gemini Developer API key or a Vertex AI service-account JSON object. Validate it without company content, use explicit project/location/scoped service-account credentials for Vertex, store canonical secret material only in Supabase Vault, expose only non-secret status metadata, and permit plaintext resolution only to the durable worker under current tenant context. Never execute pasted credential-adjacent code. A process environment API key is a non-production fallback only. Never place provider credentials or Supabase privileged secrets in Vite variables, desktop code, client-readable rows, logs or fixtures.
- Supabase repository boundary: keep CLI configuration, migrations, seeds, database tests, Edge Functions, shared function modules, function tests and safe environment examples under the root `supabase/` directory. Do not create another migration/function tree under a service.
- Hosted migration boundary: repository migrations are authoritative. The founder applies them manually unless explicitly delegating a hosted change; record the repository commit and migration version, never credentials or secret values.
- Runtime roles are least-privileged, non-owner and non-BYPASSRLS. Migration credentials are separate.
- Tenant-owned relationships use composite tenant-aware integrity, not UUID uniqueness alone.
- Compute outside database transactions. Commit an exact approved proposal and its outbox intents atomically under a planning revision check.
- External writes are durable, idempotent where supported, reconciled after ambiguity and visibly partial when incomplete.
- Requested, agreed and forecast deadlines are distinct. Priority never silently grants overtime, access or deadline movement.
- Flexible task windows may overlap; exclusive human effort and fixed meetings may not. Passive waiting consumes elapsed time but not active capacity.
- Preserve immutable historical requests, evidence, proposals, approvals, submissions and accepted versions.

## Implementation order

Work in dependency-ordered vertical slices:

1. Native shell viability, repository tooling and architecture decisions.
2. Identity, company isolation, invitations, private storage and migrations.
3. No-model task, capacity, brief, submission and review workflow.
4. Typed scheduling, independent validation, priority policy and exact-version commitment.
5. Bounded source adapters and schema-constrained interpretation.
6. Evidence projections, approval, outbox, refresh and reconnect handling.
7. Connected software/HR scenario, failure recovery and concurrency tests.
8. One live authorised calendar/document path plus clearly labelled simulators.
9. Evaluation harness, native artifacts and honest release manifests.
10. P1 capability only after its P0 dependencies and gates pass.

Do not replace a working slice with a broad scaffold, duplicate domain logic between services or introduce microservices, a graph/vector database or an agent framework without measured need.

## Repository and GitHub workflow

`main` is releasable and changed through pull requests. Use short-lived branches:

- `feat/<issue>-<slug>` for user-visible capability.
- `fix/<issue>-<slug>` for defects.
- `docs/<issue-or-slug>` for documentation.
- `refactor/<issue>-<slug>`, `test/<issue>-<slug>`, `ci/<slug>`, `security/<issue>-<slug>`, `chore/<slug>` and `release/vX.Y.Z` for their named purposes.

Use lowercase kebab-case after the prefix. Do not create personal, vague or long-lived branches such as `dev`, `changes`, `john-work` or `final-final`.

Use Conventional Commit subjects: `type(optional-scope): imperative summary`. Allowed types are `feat`, `fix`, `docs`, `refactor`, `test`, `ci`, `build`, `perf`, `security`, `chore` and `revert`. Keep commits reviewable and never mix unrelated cleanup into a functional change.

Every non-trivial PR links an issue, states acceptance criteria, identifies risk, includes actual verification output and updates affected documentation. Squash merge is the default. Do not push directly to `main`, force-push shared branches, bypass a failing required check or claim review that did not occur.

## Coding, migrations and contracts

- Inspect existing code, migrations, configuration and tests before editing.
- Implement the smallest complete solution; preserve user changes and avoid speculative abstractions.
- Keep backend schemas, generated contracts, TypeScript types and migrations aligned. Contract drift must fail CI once contracts exist.
- Use additive, reversible migrations where feasible. Never reset an existing database to simplify a schema change.
- Keep secrets out of source, Vite variables, fixtures, logs, screenshots and release artifacts. Commit descriptive `.env.example` files only.
- Treat applied migrations as immutable and use a later migration for corrections. Reconcile recorded hosted migration state before authoring a dependent change.
- Validate at trust boundaries and preserve security controls, database constraints, idempotency, revision checks and audit history.
- Use explicit lifecycle transitions and permission-safe errors that do not reveal private object existence.
- New constraint families require a typed schema, semantic validator, compiler, independent candidate checks, diagnostic mapping and tests.

## Testing and evidence

Run only the strongest relevant tests for the change. Behaviour changes require regression coverage. At minimum consider tenant isolation, role forgery, source revocation, stale proposals, overlapping windows versus exclusive effort, dependencies/reviews, solver timeout/unknown, candidate mutation, competing commits, outbox recovery, duplicate provider events and native-platform boundaries.

Report commands actually run and their outcomes. Mark unavailable hardware, credentials, signing, external accounts or tests as **NOT RUN** with the exact prerequisite. A browser test is not a native desktop test; compilation is not installation; a fixture is not a live connector; zero observed failures is not a universal guarantee.

Before finishing a change:

1. Run `python scripts/check_repository.py`.
2. Run subsystem tests affected by the change.
3. Review the diff for secrets, unrelated edits, stale docs and false implementation claims.
4. Update requirements-to-evidence status where implementation state changed.
5. Provide changed files, test evidence, remaining limitations and follow-up risks in the PR.
