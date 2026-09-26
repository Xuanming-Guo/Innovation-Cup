# Coordination Engine — Version 2 change log

**Revised:** 25 September 2026  
**Baseline:** The original Version 1.0 Word and Markdown master specification of 23 September 2026.  
**Purpose:** Identify substantive changes, why they were made, and where they now appear. This is a clean revised edition, not a Word tracked-changes/redline file. The original source files remain unchanged for comparison.

The revision rewrites the relevant original sections, schema entries and acceptance criteria. It does not simply append a contradictory list of new suggestions. Original page references below identify the founder's comments; pagination changes in the revised Word edition. Use the numbered sections to locate the revisions.

## 0. Repository-foundation clarification

The master specification and implementation handoff now state the complete pre-solver trust boundary explicitly: authorised and versioned sources become bounded evidence, schema-constrained candidate task contracts, deterministically validated constraints, an immutable planning snapshot and finally a trusted compiled Z3 model. Raw source content and model-generated code never enter Z3. Z3 constructs or checks a schedule within the admitted model; a separate deterministic validator checks the concrete result before approval or commitment.

The repository guidance now also requires protected-main pull-request development, consistent branch and commit naming, issue and PR templates, automated repository checks, reviewable merges and honest capability documentation. These governance additions do not constitute application implementation or test results.

## 1. Page-by-page feedback incorporated

| Original passage / feedback | Version 2 decision | Main locations |
|---|---|---|
| Page 17: Where do approved summaries come from? Prefer current raw company data. | Read permission-filtered structured fields and necessary original excerpts first. Machine summaries are optional, versioned retrieval aids. They are not manager-approved facts. Human confirmation is required for material inferred decisions, not every summary. | Sections 7, 9.3a, 11, 12 Steps 3–6, 15 groups 26–31 and 47, 17, 20 |
| Page 18: What are invalidation hints? | Rename them private refresh signals: minimal notices telling a client to refetch current authorised records. Persistent notifications remain in the database. Signals do not cancel tasks or contain confidential plan details. | Sections 12 Step 16, 14, 15 groups 39–40, 16, 20 |
| Page 17: Employees need context but must not see restricted planning details. | Add manager-written or manager-approved briefs with exact versions, audiences and disclosure approval. Generate recipient explanations from an authorised fact projection. A second model check may escalate suspected leakage but cannot grant permission. Schedule approval and disclosure approval are separate. | Sections 7, 9.3a, 12 Steps 2 and 10, 15 groups 48–49, 16.1a, 17.5, 20 |
| Page 19: Employees multitask. | Permit overlapping ownership and completion windows. Allocate real effort within those windows; fixed meetings and exclusive effort cannot double-book a human. Passive waits consume no continuous human capacity. No invented fractional attention. | Sections 2, 8, 12, 13.2–13.3, 15 groups 22 and 56, 20 |
| Page 19: Make skill and other task-specific constraints explicit. | Requirements now include essential/preferred capability, accepted evidence, permissions, review, separation of duties, shared resources, dependencies and acceptance criteria. Incomplete or ambiguous material requirements are resolved before solver compilation. | Sections 8.2, 12 Steps 5–8, 13.3, 15 group 18, 17.2, 20 |
| Page 20: Priority is a product-wide issue, not only a Z3 detail. | Introduce explicit priority inheritance, authorised overrides, contested-capacity precedence, equal-priority parallelism where feasible, dependency urgency and displacement approval. Preserve requested/agreed/forecast dates separately. | Sections 8.5, 12, 13.4, 15 group 50, 16.1a, 17, 20 |
| Page 20: Use solver diagnoses to guide replanning. | Map tracked constraint IDs to structured, source-linked diagnoses. Bound repair attempts and revalidate proposed changes. Distinguish failed pinned insertion, full infeasibility, invalid inputs and timeout/unknown. The model cannot delete hard constraints or grant authority to get a green result. | Sections 12 Step 9, 13.5–13.7, 15 group 55, 17.5a, 20 |
| Page 30: Update employee profiles throughout work, and use recent relevant experience. | Separate operational workload, familiarity/exposure, accepted skill evidence and estimate snapshots. Update live state immediately. Only appropriately accepted evidence supports stronger capability conclusions. Recent familiarity can reduce estimated setup cost without becoming a qualification or secret ranking. | Sections 8, 12 Steps 17–20, 15 group 51, Section 18, 20 |
| Page 33: How will the human study actually run? | Add recruitment, realistic case preparation, practice/A/B conditions, counterbalanced order, timed sessions, event logs, observation, independent rubrics, employee comprehension, consent, pseudonymous storage, exports and analysis. A small exploratory sample is not a powered productivity trial. | Section 20.6; Section 15 group 52; build prompt A17 |
| Page 36: Could tasks also be performed by AI agents? | Replace the absolute exclusion with a human-led P0 baseline and a controlled optional P1 executor. Add shared resource identity, human accountability, capabilities, tools, concurrency, cost/time limits, runs, review and kill switch. Keep hybrid execution results separate from scheduling results. | Sections 0–2, 8, 12, 13, 15 groups 21, 41, 53–54; 18.6, 21, 23 |
| Latest request: Run on MacBook and Windows. | Require native Tauri delivery for Windows x64, macOS Apple Silicon and macOS Intel. Specify artifacts, native build hosts, signing, WebView2, secure storage, browser authentication, deep links, platform tests and honest release manifests. | Sections 2.2a, 9–10, 15 groups 57–58, 20.7a, 22; build prompt A3–A5, A20 |

## 2. Cross-platform scope: what is now required

The support targets are **Windows 11 x64** and **macOS 13+ on Apple Silicon and Intel**, subject to the actual minimum versions of the dependencies selected during implementation. These are recommended product defaults, not a claim about every possible Tauri deployment or the user's exact laptop model.

A Windows setup executable is not a Mac application. The implementation must produce a Windows NSIS setup `.exe` and native macOS `.app`/`.dmg` packages. Separate Mac architecture packages are the default; a universal bundle is optional. Windows ARM64 and Linux are not mandatory for this edition.

Native build and native operation are separately evidenced. Browser UI tests are insufficient to establish desktop support. The release manifest must name the OS, architecture, build version, signing/notarisation state, test environment and missing tests. An architecture that merely cross-compiles must not be labelled hardware-tested.

The application remains cloud-backed: the user does not install Python, Z3, Docker, Node or Rust to use a packaged client. Developer machines have their own build prerequisites. Credentials are stored through OS-protected facilities; privileged backend/provider keys never ship in the executable.

## 3. Schema and API changes

The revised logical dictionary contains **58 numbered entity groups**; several groups contain more than one physical table. This is an implementation schema contract, not a set of already tested SQL migrations.

Existing tasks, assignments, blocks, submissions, constraints, policies and profile records were revised. New groups cover source summaries; approved briefs/audiences; explanation projections; priority history; familiarity; research-study records; execution resources; optional agent profiles/runs; repair diagnoses; flexible work windows and attendance; authentication/connector handshakes; and release/test manifests.

Authoritative application data resides in a non-exposed business schema behind the API. The implementation must combine least-privilege runtime database roles, company-scoped relationships, RLS, private Storage access and restricted backend job scopes. A service credential that bypasses RLS is not an excuse to omit tenant checks.

API contracts now include brief approval, employee explanations, familiarity corrections, priority changes, repair diagnostics, study exports and optional agent execution. Database, OpenAPI and TypeScript contracts must stay aligned.

Where an existing application has data, use staged additive migrations and backfills, not a destructive reset. In particular, an agent resource is not automatically an employee account, and an overlapping task window must not be migrated as an exclusive work reservation.

## 4. Reliability and proof boundaries retained

The revision retains and sharpens the distinctions between source authenticity, authority, model interpretation, solver feasibility, optimality, database commitment, external synchronisation and work acceptance.

Z3 still runs in a hosted Python worker. It constructs/checks schedules from a restricted typed model compiled by trusted code. It does not accept arbitrary generated Python as the scheduling interface and does not judge deliverable quality.

Priority and disruption use an explicit versioned objective. Original deadlines remain immutable historical facts. Approved changes create revisions; current forecasts do not rewrite commitments.

A proposal is bound to an input snapshot, source/policy/profile versions and exact diff. Approvals bind that proposal. Concurrent changes require revalidation and may require renewed approval. The internal commit is atomic; cross-provider writes are durable, idempotent where possible, reconciled and visibly partial when incomplete.

Observations of real-world changes must not be rejected merely because they invalidate the old plan. Record the observation, mark affected work, and repair or explain the conflict.

## 5. What has not become a promise

No prototype, native installer, SQL migration test, provider connection, user study or benchmark result has been produced by updating these documents.

The following remain hypotheses or open decisions: measurable productivity benefit, commercial pricing, exact pilot buyer, hosting region, chosen model, production retention periods, customer priority vocabulary, permitted deadline movement and organisational approval policies.

The source register now contains **60 primary references**. Historical studies retain their dates, populations and limitations. They motivate investigation; they are not this product's results.

## 6. How the new build prompt differs from the specification

The specification explains the business reasoning, evolution, product rules, architecture, logical schema and validation approach.

The separate `implementation_master_prompt_v2.md` is a self-contained coding-agent handoff. Its Part A adds repository structure, implementation order, runtime command contracts, native packaging commands, APIs, tests, screen behaviour, integration modes and release acceptance. Its Part B embeds the entire revised specification verbatim.

Give the coding agent that one Markdown file. It should inspect the repository first and then build working vertical slices. It should not return another specification as the implementation or silently replace an existing application with a new scaffold.
