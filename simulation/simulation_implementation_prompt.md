# Coordination Engine simulation — implementation prompt

**Purpose:** Build a deterministic, inspectable simulation environment and evaluation harness that can drive the real Coordination Engine product when it becomes available, compare its observed outcomes with a reproducible naive coordinator, and demonstrate task-management impact under the synthetic workload defined in `simulation/coordination_engine_simulation_context_v2.docx`.

**Status:** This is an implementation prompt, not a claim that the simulation, product backend, solver, integrations, benchmarks, or measured efficiency results already exist.

**Simulation specification version:** `0.5.0`. Record this value in scenario and benchmark run manifests. If the user later authorises a material specification change, update this value and `simulation/CHANGELOG.md` together; an implementation run must not silently rewrite its own governing contract.

## 0. Read before implementation

Before writing code, read these sources in this order:

1. `AGENTS.md`.
2. `simulation/coordination_engine_simulation_context_v2.docx` in full.
3. `docs/implementation_master_prompt_v2.md`, including Part A and the embedded product specification.
4. `docs/coordination_engine_master_v2.md` when checking product or architecture language.
5. `docs/development/github-workflow.md` before creating a branch, commit, issue, or pull request.

The simulation context controls the synthetic company, scenario, comparison baseline, ground truth, and benchmark metrics. The implementation master prompt controls the intended product boundaries and future architecture. If they appear to conflict, preserve the product's authority, privacy, grounding, approval, and evidence boundaries and record the specific decision instead of silently weakening either document.

Inspect the current repository before scaffolding. Existing files outside `simulation/` may be read to understand product contracts, but they are read-only for this task. If working product code now exists, consume or mirror its published contracts through simulation-local adapters; do not modify, move, or overwrite that product implementation.

### 0.1 Strict repository write boundary

**All changes made while executing this prompt must stay inside the repository's `simulation/` directory.** This is a hard constraint, not a preference.

- The agent may read files anywhere in the repository, including `AGENTS.md` and `docs/`, but may create, edit, rename, move, or delete files only below `simulation/`.
- Do not change root configuration, package manifests, lockfiles, workspaces, `.gitignore`, CI workflows, application packages, backend packages, database migrations, documentation, or any other path outside `simulation/`.
- Git history and branch state are user-managed for this run. Read-only Git inspection is allowed, but do not create or switch branches, commit, stash, tag, merge, rebase, or otherwise modify `.git` state.
- Do not modify or replace `simulation/coordination_engine_simulation_context_v2.docx`; treat it as immutable source material. Treat this implementation prompt as immutable control input too unless the user explicitly asks to revise it.
- Put all simulation manifests, lockfiles, source code, UI code, test configuration, virtual environments, dependency directories, caches, generated artifacts, and ignore rules under `simulation/`. If a tool would update a repository-level file, do not run it in that mode.
- System temporary directories and normal user-level tool caches may be used only when unavoidable and must not contain committed project state. No external repository, service, deployment, or account may be changed.
- Preserve every pre-existing user file. Do not perform destructive cleanup to make the boundary check pass.
- If a required implementation step truly needs a change outside `simulation/`, do not make that change. Record it as a blocker or future integration step in `simulation/STATUS.md` and continue with a simulation-local adapter or stub when that remains honest.
- At startup, record `git status --short --untracked-files=all` in `simulation/STATUS.md` as the baseline. At every checkpoint and before finishing, run it again and verify that every path changed by this implementation begins with `simulation/`.

### 0.2 Long-running orchestration contract

Run this as an iterative implementation job, not a one-shot code generation request. The orchestrating agent must continue until all in-scope acceptance criteria pass or a genuine blocker prevents further safe progress.

Maintain these durable, simulation-local coordination files so another agent or a resumed session can continue without relying on chat history:

- `simulation/PLAN.md`: ordered milestones and acceptance checks.
- `simulation/STATUS.md`: current state, commands run with actual outcomes, failing checks, next action, and the repository-boundary baseline/checks.
- `simulation/DECISIONS.md`: consequential assumptions and reversible design decisions, including backend-adapter choices.
- `simulation/CHANGELOG.md`: append-only history of material changes to the simulation approach, scenario design, baseline, planner, metrics, schemas, connector assumptions, and judge-facing claims.

Keep these purposes separate: `STATUS.md` says what currently works, `DECISIONS.md` explains why the current design was chosen, `CHANGELOG.md` records how the approach changed over time, and runtime JSONL traces record what simulated actors did. Each changelog entry must include a date and version plus **Added**, **Changed**, **Fixed**, **Validation impact**, and **Open limitations** as applicable. State the previous behavior, the new behavior, why it changed, and which scenarios, contracts, metrics, fixtures, or claims are affected. Record compatible implementation changes in the changelog and manifests. Record a proposed contract-changing deviation under **Unreleased** and wait for user authorisation instead of silently changing this prompt. Never rewrite old benchmark results under a new method; retain their original manifest/version and rerun them under a new run ID.

For each iteration:

1. Re-read the current plan and status.
2. Select the smallest unfinished vertical slice that creates testable user-visible or benchmark behavior.
3. Implement it entirely inside `simulation/`.
4. Run the strongest relevant tests, type checks, builds, and deterministic replay checks.
5. Inspect the resulting trace, calculated metrics, and affected manager/employee/judge views rather than trusting a successful process exit alone.
6. Repair failures and repeat until the slice passes.
7. Update `PLAN.md`, `STATUS.md`, and `DECISIONS.md` before beginning the next slice, and append to `CHANGELOG.md` whenever the approach or externally visible behavior changed materially.

Do not stop after writing a plan or broad scaffold. Do not report success while required checks are failing, skipped without a recorded prerequisite, or replaced by hard-coded favorable outputs. Stop only for a real authority, privacy, external-access, cost, destructive-action, or material-scope decision that this prompt does not authorise; record the precise blocker and the best next action in `simulation/STATUS.md`.

## 1. Mission

Build a runnable, product-independent simulation environment and evaluation harness that lets judges observe, step by step, how the same organisational changes are handled by:

1. A transparent naive coordinator using local greedy assignment, conflict-by-conflict cascade repair, and hierarchical communication relays.
2. The actual Coordination Engine system under test, connected through a stable adapter and expected to use its product implementation of bounded authorised context, typed constraints, affected-subgraph planning, Z3 schedule construction, independent validation, approval, commitment, synchronisation and permission-safe communication.

The simulation owns the synthetic environment, scenario injection, fixture workspaces, deterministic actors, naive baseline, independent scoring validator, observation/trace capture, metrics and judge replay. It must **not** implement a second Coordination Engine inside `simulation/`. In particular, do not duplicate the product's interpretation pipeline, trusted constraint compiler, Z3 planner, approval policy, transaction/commit service, outbox worker, notification service, learning service or manager/employee task application.

Until the product integration exists, provide a clearly labelled recorded-replay or contract-stub adapter so the environment, baseline, validator, metrics and judge interface can be developed. Stub/replay output is plumbing evidence only and may not be shown as measured Coordination Engine performance. Product metrics remain `NOT_RUN` until a real product build executes the scenario through the adapter.

Both approaches must start from semantically equivalent immutable initial state and receive the same authorised facts, effort estimates, skills, permissions, priority policy, deadlines, and allowed flexibility. Preserve a canonical input manifest and product-mapping report proving equivalence. Do not disadvantage the baseline by withholding facts or granting Coordination Engine freedoms the baseline does not have.

The simulation must demonstrate efficiency in the narrow, defensible sense defined by the study: fewer unnecessary changes, replans, coordination relays, duplicate transmissions, invalid delegations, overload minutes, dependency violations, and lower-priority collateral changes, plus faster service to Critical work where the shared constraints permit it. These are synthetic benchmark outcomes, not measured human productivity, customer value, or real-world time savings.

## 2. Locked story and scope

Use the fictional company **SoraWorks Japan**, a synthetic Japanese B2B enterprise-software and implementation-services company.

Narrative scale:

- 3,000 employees.
- 117 teams.
- Approximately 150 active projects.
- Approximately 8,000 active tasks and commitments.
- Approximately 400–700 cross-team dependency edges.
- Approximately 120 shared specialists.
- A five-working-day planning horizon.
- All people, customers, projects, messages, calendars, and documents are synthetic.

The judge-facing story contains exactly two connected changes:

### Change A — Hikari deadline pull-in

Hikari Manufacturing moves a customer reporting demonstration from Friday to Wednesday afternoon. The existing dependency chain is:

`Reporting API -> Reporting dashboard -> QA validation -> Security review -> Customer demo`

The change should require a non-trivial but small repair. The system must first test whether the request can be inserted without disruption, then move only work that is movable and authorised. The fixture target may resemble 37 commitments checked, one moved, no owner changes, no deadline extensions, and 36 preserved, but the implementation must calculate the actual result. Never hard-code the target as a benchmark result.

### Change B — Critical production incident

An authorised incident commander declares a Sev-1 SSO failure affecting multiple enterprise customers to be Critical under the company incident policy. The incident creates a dependency chain such as:

`Triage -> Diagnosis/hotfix -> Security review -> Smoke test -> Deploy/verify`

It competes with the Hikari work for shared Security and QA/Release specialists. Critical ready work receives contested capacity according to policy, but priority does not grant overtime, access, deadline movement, or permission to move protected work. If both commitments cannot be preserved, surface the conflict and required approvals rather than inventing feasibility.

Supporting automated or backup cases may include an impossible deadline, source revocation, unavailable calendar lookup, concurrent manager commits, a no-impact change, and the master product specification's software/HR compatibility case in which internal onboarding work needs a shared technical specialist. The HR case concerns induction preparation and technical orientation only—not recruiting, candidate ranking, payroll or an HR information system. It proves that the same contracts support the product's planned connected scenario, but it is not a third main-demo story.

## 3. Product boundary represented by the simulation

The simulation is not an autonomous-agent workforce. Human work remains the P0 product baseline. Simulated “agents” are observable actors with bounded roles and deterministic or explicitly versioned policies. They exist to replay coordination behavior, not to impersonate employees or claim general autonomy.

Required actors include:

- Requesting manager.
- Incident commander or other authorised priority source.
- Affected team managers or approval authorities.
- Shared Security specialist.
- QA/Release specialist.
- Other affected employees needed by the Hikari and incident chains.
- Required reviewers.
- Naive coordinator.
- Scenario driver and deterministic human-response policy for clarifications, approvals, acknowledgements and review.
- Coordination Engine system-under-test adapter and observer; product-internal planner/orchestrator actions are imported when exposed, not recreated.
- Neutral benchmark validator, independent of both the naive baseline and product validator.
- Simulated workspace providers/delivery environment for source reads and external-action outcomes.
- Benchmark observer/collector.

Each actor has an explicit identity, role, company/team/project scope, accessible facts, permitted actions, and deterministic policy or configured implementation version. Reporting relationships do not grant source access.

Do not use one omniscient agent. Do not expose unrestricted shell, arbitrary network, or mutable authority to any simulated actor. If Gemini is used, it is the confirmed server-side interpretation/explanation provider through a typed gateway; its output remains untrusted and cannot assign authority or generate executable solver code.

## 4. Backend-independent implementation requirement

The production backend does not exist yet. Build a stable benchmark schema and system-under-test contract rather than guessing and implementing that backend. The harness must survive changes to FastAPI/Supabase and product internals by mapping canonical scenario inputs and observable outputs at the adapter boundary.

### 4.1 Stable domain boundary

Define versioned **benchmark** contracts for at least:

- Company, team, employee, membership, and scoped role.
- Execution resource, accountable human, resource kind, capability/capacity version, and disabled optional-agent configuration.
- Project, task, requirement, dependency, reviewer, and acceptance gate.
- Working rules, availability, busy interval, schedule block, and protected commitment.
- Source record, source version, access grant, evidence reference, and approved brief.
- Optional source-summary cache with derivation/access/invalidation metadata; summaries are never canonical approved facts.
- Priority assignment/history, effective dependency urgency, policy version, movement authority, requested/agreed/forecast deadline, and approval requirement.
- Interpretation/clarification state, planning snapshot, candidate schedule, validation report, proposal diff, approval, exact internal commitment, external-action intent, synchronisation result, durable notification, private refresh signal, and acknowledgement.
- Submission, review, acceptance/revision, operational workload event, familiarity evidence, estimate snapshot, correction and dispute.
- Change event, benchmark case, run manifest, metric observation and benchmark result.
- Actor action event and viewer-safe trace projection.

These contracts describe fixtures, expected invariants, inputs, observable outputs and scoring—not a competing source of product business logic. Use explicit schema versions. Prefer Pydantic models and exported JSON Schema for Python-facing contracts. Keep timestamps timezone-aware and serialize stable IDs rather than display names as identity. When product-generated contracts become available, add a thin mapper and contract-compatibility tests instead of copying or forking them.

### 4.2 Ports and adapters

Keep simulation logic behind interfaces such as:

- `ScenarioRepository`
- `WorkspaceEnvironmentPort`
- `SystemUnderTestPort`
- `SystemUnderTestContractMapper`
- `NaiveCoordinatorPort`
- `NeutralScoringValidatorPort`
- `RunObserverPort`
- `RoleProjectionCapturePort`
- `TraceSink`
- `MetricsSink`
- `Clock`
- `IdGenerator`

The `SystemUnderTestPort` must support capability/version discovery, synthetic-tenant seed or import, reset, scenario-event submission, deterministic clarification/approval/acknowledgement responses, progress/event observation, role-safe projection capture and terminal evidence export. It must never require the harness to write directly into undocumented product tables.

Provide two SUT adapters:

1. A contract/recorded-replay adapter for harness development. It replays explicitly versioned captured example outputs, is always labelled **REPLAY — NOT A PRODUCT RESULT**, and cannot populate product-performance headline cells.
2. A real product adapter, initially `NOT IMPLEMENTED`, that later calls the product's supported API/test harness or imports its shared contracts. It must record product commit/version, API/schema version, enabled capabilities and mapping decisions.

Provide local file/in-memory adapters for scenario and fixture data. Design the real SUT adapter for the planned FastAPI/Supabase product boundary without requiring that backend now. The judge UI calls the simulation/evaluation service, while manager and employee product behavior is captured from the SUT rather than rebuilt.

The current local implementation may persist JSON, JSONL, and CSV artifacts. Do not make file layout the domain API. A later real-product adapter must be replaceable without changing scenario logic, deterministic actor policies, metric definitions or captured-POV contracts.

### 4.3 System-under-test and planner boundary

The product specification assigns Z3 planning and independent product-side candidate validation to the real Coordination Engine. Do not implement Z3 compilation, solving, diagnostic repair or product candidate validation in this simulation package.

When the connected product exposes the required trace, observe and preserve:

`SourceVersionRef -> CandidateTaskContract -> ValidatedConstraint -> PlanningSnapshot -> CompiledModel`

The adapter records product-reported compiler/solver/validator versions, model status, objective vector, affected scope and constraint IDs. The harness independently scores the final concrete output against generator-owned ground truth; this neutral scoring validator must not import or reuse the product compiler/validator implementation. It checks outcomes but does not repair the product plan.

If the product later replaces or supplements Z3 with CP-SAT, only the adapter metadata and output mapping should change. Scenario generation, naive baseline, neutral scoring and metrics remain stable.

### 4.4 Offline and credential-free mode

The environment, naive baseline, neutral validator, metric engine and recorded replay must run without Supabase or Gemini credentials.

- Do not implement a separate Gemini gateway in the harness. The real product owns model calls.
- A product-connected run records the product-reported model, prompt/schema/configuration, input manifest hashes, tokens/cost, latency and outcome when exposed. The current master-prompt default is `gemini-3.8-flash`, but the recorded actual configuration controls the result group.
- Fixture/recorded interpretation is explicitly simulated and excluded from model-extraction accuracy or product-performance claims.
- Never place secrets in the repository, frontend, trace export, fixture, screenshot, or benchmark artifact.

### 4.5 Product and connected-workspace fidelity

The real product is intended to coordinate work that is already distributed across communication, calendar, task-management, document, and development workspaces. The simulation must provide deterministic external-workspace environments that the product can connect to, or that the SUT adapter can translate into supported product imports, without implementing the product's connector/ingestion layer twice.

Implement a common, versioned **workspace fixture/environment** contract that supports:

- capability discovery;
- company-, connection-, principal-, and resource-scoped authorisation;
- bounded reads of only the fields or excerpts required for the scenario;
- external IDs, provider versions, retrieval time, freshness/expiry, classification, and live/simulated mode;
- polling or incremental-change events, revocation, pagination/throttling, unavailable/unknown states, and duplicate delivery handling;
- an explicit list of supported writes; and
- deterministic write responses, provider idempotency/conditional-version behavior, uncertain outcomes and visible partial failure so the product's own durable-action logic can be exercised.

Provide realistic simulated adapters and artifacts for at least:

| Workspace | Scenario-relevant fixture behavior |
|---|---|
| Microsoft Teams | Authorised channel/chat excerpts, decisions and incident coordination events. Do not ingest an entire workspace or treat any recent message as approval. |
| Outlook/Exchange calendar | Working hours, meetings and free/busy intervals. Reduce private events to opaque occupancy before planning; do not expose subjects or personal reasons. |
| Microsoft Planner | Assigned tasks, status, due dates, checklist/acceptance references and provider versions. Distinguish imported work from work exported by this simulation. |
| SharePoint/OneDrive | User-selected briefs, requirements, policies and review artifacts with version, classification, owning scope and access grants. |
| GitHub or an equivalent development source | Selected issue/PR status and references when relevant to software work; never simulate autonomous code changes as part of P0 coordination. |

Every workspace environment must be visibly labelled **simulated** in the UI, manifests and trace. A fixture must never present a fake OAuth success or be counted as proof of live API support. Keep provider-specific payloads inside environment adapters. The naive baseline receives an equivalent canonical permission-filtered fact projection; the real product performs its own authorised ingestion through the SUT mapping. Record both input manifests so fairness can be checked.

The two main scenarios must use coherent cross-workspace evidence rather than a single omniscient input. At minimum:

- Hikari's requested deadline, current commitment and disclosure-approved employee brief come from separately versioned, appropriately authoritative records.
- Current task state and acceptance gates are represented in a task workspace fixture.
- employee capacity comes from working rules plus calendar/free-busy and existing internal or imported reservations;
- relevant requirements and review policy come from selected document versions;
- the incident priority declaration is linked to an authorised incident commander and policy version, while incident conversation remains access-scoped; and
- the environment accepts proposed external updates only when the connected product reaches its exact approved/committed stage, then returns scripted success, timeout, stale-version or partial-failure outcomes for the product to reconcile.

Include at least one stale source, unavailable connector or revoked grant, duplicate provider event, and partial external-write outcome in automated supporting cases. Unknown availability is not free time. Newer chat text does not silently override an approved requirement. A calendar block does not reveal its subject. Being able to read one Teams channel does not grant access to a SharePoint document, another team, or the whole tenant.

### 4.6 Product-component coverage and claim boundary

The simulation is an evaluation harness for the product workflow, not a second production backend or desktop application. Represent every consequential product component below through stable contracts, executable local behavior or an explicit non-claim. Track each row in the requirements-to-evidence matrix as **IMPLEMENTED**, **SIMULATED**, **NOT RUN**, or **FUTURE PRODUCT**.

| Product component | Harness responsibility and required SUT evidence | Claim boundary |
|---|---|---|
| Identity, company isolation and scoped roles | Generate synthetic companies, memberships, grants, actor credentials/claims and second-tenant probes; seed them through the SUT adapter and assert observed isolation | Harness persona switching is not authentication, RLS or native secure-token proof |
| Manager request and disclosure brief | Inject the versioned request, selected sources, restricted context and separate employee brief; deterministic actors answer product clarification/approval requests | The harness does not implement brief generation or disclosure policy |
| Connected-source ingestion | Serve versioned provider fixtures with authority/freshness/access, omissions and revocation; record exactly what the product imports | Fixtures are simulated and are not OAuth/provider validation |
| Model interpretation | Observe product contract/clarification outputs and metadata when exposed; replay examples only develop the harness | The harness has no separate Gemini gateway and replay is not extraction evidence |
| Deterministic admission | Assert that unsupported/ambiguous inputs do not reach a successful plan and capture product constraint/evidence references when exposed | The harness does not compile product constraints |
| Planning and diagnosis | Observe snapshot, pinned insertion, repair, objective, scope and result classifications through product evidence | The harness does not implement Z3 or diagnostic repair |
| Independent scoring | Neutral harness validator recomputes concrete assignment, segment, capacity, eligibility, review, date, authority and protection outcomes against generator ground truth | It scores outcomes and never repairs the SUT plan; common bad ground truth remains a limitation |
| Proposal and explanation | Capture exact product before/after diff, unchanged commitments, evidence links, viewer projections and alternatives | Feasibility, optimality, explanation and authority remain separate claims |
| Approval | Deterministic actors approve/reject only through supported product actions; capture exact digest/revision and affected authorities | The harness does not decide product approval policy |
| Internal commitment | Observe committed version and final authoritative schedule after competing/stale attempts | This does not duplicate the product transaction service or prove production RLS |
| External synchronisation | Provider environment returns scripted success, timeout, stale version, duplicate and partial failure; observe product reconciliation | The harness does not implement the product outbox/worker |
| Notification and reconnect | Drop or deliver fixture refresh signals and capture the product's authorised refetch/projection | Signal delivery is not the source of truth and carries no confidential body |
| Human execution lifecycle | Deterministic actors invoke supported acknowledge/flag/start/block/submit/review/accept actions and the observer captures product state | The harness does not build a second employee task workflow |
| Learning and correction | Inject corrections and observe versioned workload/familiarity/estimate outputs if implemented | No harness-invented skill update, waiting-as-effort or hidden score |
| Memory, provenance, retention and threat cases | Maintain immutable scenario/run evidence, serve revoked/malicious sources and assert secret-safe exports | Fixture policy is not legal review, real deletion proof or production certification |
| Optional AI executor | Provide disabled/enabled scenario inputs and observe product capability/budget/review behavior only when the product exposes it | Do not build an executor inside the harness or mix its speed with scheduling gains |
| Manager/employee/judge experience | Capture product manager/employee projections when connected; use clearly labelled replay screenshots/data only for harness development; build only the judge comparison/replay surface | Replay is not a duplicate task app or evidence of Tauri/macOS/Windows support |
| Production platform | Thin adapter for supported FastAPI/product test APIs and exported contracts | Do not build or claim Supabase, Cloud Run, migrations, sign-in or installers inside this folder |
| Automated evaluation | Reproducible scenarios, naive baseline, neutral scoring, metric registry and honest results manifests | Human studies are outside this simulation scope |

The SUT observation contract should expose interpretation, solver, product validation, approval, internal commitment, external synchronisation, notification/refetch, acknowledgement and work-acceptance states separately when the product supports them. Missing observability is recorded as `NOT_AVAILABLE`, never inferred from a single “done” flag.

## 5. Deterministic company and scenario generation

Build a generator rather than hand-authoring thousands of unrelated rows.

Required presets:

| Preset | Employees | Teams | Active tasks | Purpose |
|---|---:|---:|---:|---|
| `tiny` | 25 | 4 | 75 | Unit tests and exhaustive/oracle cases |
| `medium` | 100 | 10 | Approximately 350 | Integration and repair regression tests |
| `demo` | 3,000 | 117 | Approximately 8,000 | Main company-scale narrative |
| `stress` | 10,000 | 300+ | Approximately 30,000 | Optional; never block P0 |

Generation requirements:

1. Accept an explicit seed and configuration version.
2. Generate coherent projects from the workflow templates in the simulation context rather than independent random tasks.
3. Produce acyclic intended dependency graphs.
4. Generate confirmed skills, qualifications, working windows, calendars, reviewer requirements, access grants, source versions, protection state, and movement authority.
5. Include at least 20 cross-team employees with one company-wide capacity budget and non-transitive source access.
6. Include capacity-only opaque reservations that hide the underlying private project.
7. Ensure every material constraint has a source version or explicit human confirmation in the ground truth.
8. Validate the initial committed schedule before scenario injection.
9. Emit immutable starting snapshots and scenario manifests for exact reset/replay.
10. Keep expected labels and ground truth outside any model or planner retrieval bundle.

Use a deterministic clock and ID generator in benchmark mode. Re-running the same version, preset, seed, and scenario must reproduce equivalent fixture and event hashes, apart from explicitly declared runtime measurements.

### 5.1 Realistic synthetic organisation and employee profiles

Do not generate anonymous interchangeable workers or uniform random rows. Build internally coherent, fully fictional profiles that make the scheduling problem believable while avoiding real personal data and prohibited employee scoring.

The primary SoraWorks company profile must define:

- company ID, fictional legal/display name, industry and business model, primary locale/timezone, planning horizon, working-rule and holiday-calendar references, and versioned priority/deadline/displacement policies;
- a plausible organisation of engineering, product, design, QA/release, security, customer delivery, HR/people operations and corporate-support teams whose counts reconcile to the selected preset;
- projects with owning teams, responsible managers, customers or internal sponsors, confidentiality classes, authorised audiences, requested/agreed deadlines and cross-team participation;
- explicit workspace connections, owning scopes, simulated capabilities and access grants; and
- coherent distributions of workload, shared specialists, protected commitments, fixed meetings, flexible work and current lifecycle states rather than an artificially empty schedule.

Also generate a small unrelated second synthetic tenant in automated isolation fixtures. It is not a third judge-facing story; it exists to prove that IDs, searches, traces, sources and connector objects cannot cross company boundaries.

Each employee profile must use a stable fictional ID and contain only scheduling-relevant, non-sensitive attributes:

- fictional display name, company membership, one or more explicit team memberships, scoped role relationships, manager where applicable, timezone and preferred locale;
- effective-dated working windows, breaks, daily/weekly active-effort budgets and declared exceptions;
- current task commitments, meetings, leave/unavailable intervals without medical or personal reasons, and opaque reservations from restricted work;
- declared skills kept separate from confirmed skills/qualifications and their accepted evidence;
- task-specific permissions, project/source access grants, reviewer or approval authority and expirations;
- recent component/project familiarity with provenance and maturity such as exposure, submission or accepted contribution;
- optional transparent task-area preferences and correction/dispute state; and
- profile, skill, familiarity, availability and estimate revision identifiers frozen into each planning snapshot.

Profiles must contain plausible variation: specialists and generalists, junior and senior scope without using age, new and established team members, single-team and authorised cross-team contributors, different working patterns and sparse versus well-supported evidence. Scarce skills and review authority must follow the company structure instead of being randomly universal. Never generate personality, work-ethic, loyalty, health, salary, demographic, hidden productivity or global employee-ranking fields. Assignment, elapsed time and calendar density are not competence scores.

### 5.2 Realistic projects, tasks and source context

Projects and tasks must form coherent workflows with shared terminology and causality. Each task contract should include:

- owning project/team, purpose, concrete deliverable, task class and lifecycle state;
- acceptance criteria, required reviewer/acceptance gate and separation-of-duties rule where relevant;
- active-effort estimate and labelled uncertainty, allowed work window, split/exclusive/passive-wait behavior, release time, and distinct requested/agreed/forecast dates;
- hard versus preferred skills, qualifications, information permissions, tools/resources and location requirements;
- dependencies, lag, readiness/acceptance requirements, priority origin and effective planning urgency;
- current owner or eligible owner domain, protection/started state, movement authority and required approvals;
- confidentiality and employee-shareable brief version; and
- links to the exact source versions and workspace objects supporting material requirements.

Create realistic, non-sensitive synthetic context artifacts rather than filler text: customer-change records, project briefs, approved decisions, Teams excerpts, Planner task cards, SharePoint requirements, incident reports/policies, calendar free/busy responses, QA/security review checklists, submissions and acceptance records. Give every artifact a believable author/owner, audience, timestamp, provider version, freshness state, authority status, classification and access policy. Include bounded ambiguity, corrections, stale versions and disagreements that test clarification without making most data dirty.

Use Japanese and English names/content where appropriate to the declared bilingual company, but never copy real employees, customers, confidential documents or identifiable schedules. Do not infer legal working rules from nationality; encode the fixture's explicit company policy and label any policy assumption. Validate referential integrity, team/project counts, lifecycle consistency, access paths, skill evidence, source lineage, schedule feasibility and aggregate distributions before a generated fixture may be used in a benchmark.

## 6. Required planning approaches

### 6.1 Primary naive coordinator baseline — mandatory

Implement this comparator in the harness exactly enough to be fair and reproducible. These components come directly from the simulation study and must not be omitted or quietly replaced:

| Baseline component | Required behavior |
|---|---|
| Affected work | Start from the changed project/employee and expand through immediate dependencies and assigned shared resources; discover additional conflicts only after local choices where applicable |
| Task ordering | Sort ready work by declared priority, then deadline/readiness; use no global objective over the entire affected model |
| Assignment | Greedily choose the highest-ranked eligible or familiar employee who appears to have enough aggregate capacity; do not intentionally select an ineligible person |
| Scheduling | Place work in the earliest locally available slot/window and resolve discovered collisions one at a time |
| Replanning | Move/reassign the conflicting task, propagate downstream consequences and repeat until stable or a declared iteration cap |
| Coordination | Relay through the reporting/project graph from originator to leads to affected employees, with extra relays as conflicts and approvals appear |
| Verification | Use no global Z3 proof or minimal-disruption optimiser; submit the terminal result to the same neutral scorer used for the product |
| Privacy | Receive the same permission-filtered facts as the product-equivalent manifest and never deliberately leak private content |

Do not let the baseline call the neutral validator iteratively as a repair oracle. Record deterministic tie-breakers, iteration cap and version. Do not portray this synthetic comparator as a complete measured representation of a customer's current manual process.

### 6.2 Coordination Engine system-under-test path

Implement the driver/observer, not the product workflow:

1. Discover the connected product version, supported adapter capabilities, schema/API versions and observable event/status fields.
2. Reset only the authorised synthetic tenant and seed/import the canonical starting snapshot through supported interfaces.
3. Configure the deterministic workspace environments and record the exact product-versus-baseline input mapping.
4. Submit Change A as the requesting manager through the product interface.
5. Observe product progress and answer only product-issued clarification, disclosure-approval, schedule-approval or acknowledgement requests using versioned deterministic actor policies.
6. Capture product-generated source/evidence references, affected scope, interpretation, insertion/repair, solver/product-validation, proposal, approval, commitment, synchronisation and notification states when exposed. Mark missing fields `NOT_AVAILABLE`; never manufacture internal events.
7. Capture the product manager and employee projections for the declared personas and assert privacy/required-context invariants.
8. Drive configured employee submission/review actions only through product-supported endpoints when the scenario requires an accepted terminal state.
9. Export the final authoritative schedule/tasks, proposal diff, approvals, notifications, external-action states and product trace/evidence bundle.
10. Inject Change B into the actual product state resulting from Change A and repeat without reseeding or substituting a harness-computed product plan.
11. Pass the exported concrete outcome to the neutral scorer and metric engine.

Expected product behaviors—pinned insertion before authorised repair, truthful timeout/infeasibility, exact approval/commit binding, minimal disruption, private projections and durable synchronisation—are assertions against observed product output. They are not implementation instructions for the harness.

Record the product's declared lexicographic objective vector when exposed: hard feasibility; service outcomes by authorised priority; protected continuity/owner stability; authorised deadline extensions/displacement; fragmentation/balance/familiarity. If it is not exposed, mark it `NOT_AVAILABLE` and score only observable outcomes. Never reconstruct a favorable internal objective from the final plan.

### 6.3 Neutral validator

The neutral validator scores both approaches and must not depend on the baseline or Z3 compiler implementation. It must recompute at least:

- Tenant and entity-reference integrity.
- Owner eligibility, required qualifications, and required source access.
- Effort totals and valid segment construction.
- Segment starts, minimum run length, maximum segments and owner consistency.
- Human capacity, working windows, fixed meetings, and exclusive overlap.
- Daily/weekly budgets.
- Dependencies, lags, reviews, and acceptance gates.
- Requested, agreed, and forecast deadlines.
- Protected and started-work movement.
- Priority/displacement authority.
- Required approvals and disclosure boundaries.

For tiny cases, add a brute-force or otherwise independent oracle where practical.

### 6.4 Evaluation layers and product-controlled variants

The required judge comparison remains the reproducible naive coordinator versus Coordination Engine. Build the runner and manifests so the following master-spec evaluation layers can also be measured without contaminating the main comparison:

| Layer | Required or conditional comparison |
|---|---|
| Interpretation | Generator-authored expected constraints versus observed product interpretation; score only when the product exposes the necessary evidence and a real model/fixture mode is identified |
| Retrieval | Bounded product retrieval versus full **permitted** context only if the product exposes a controlled evaluation mode; never build a second interpreter or create an unrestricted-secret condition |
| Scheduling | Required naive greedy/cascade baseline versus the actual Coordination Engine on equivalent inputs; optional LLM-only or other planner ablations exist only if the product itself exposes them |
| Stability | Product stability-aware repair versus an unconstrained-rescheduling product mode only if supported with identical hard constraints/freedoms |
| Execution | Inject stale revisions, competing commits, duplicate jobs/provider events, timeouts, human edits and partial provider failure; measure wrong/duplicate effects and recovery |
| End to end | Naive synthetic coordination versus the connected product path, including clarification, approval, commit, communication and terminal failure |

Optional product-controlled variants must never delay the required comparison. Label absent variants **NOT RUN**, not zero. The LLM-only planner is an ablation of the verification stack, not a market competitor. Do not implement it in the harness.

Build 5–10 hand-reviewed golden cases first, consistent with the simulation-study document. Once the runner is reliable, target roughly 30–40 varied cases across no-change insertion, tight feasible repair, infeasible scope, insufficient horizon, split work, shared review, ambiguous deadlines, conflicting sources, revoked access, task overrun, changed evidence, busy lookup failure, privacy and concurrent managers. Separate development and held-out cases by workflow structure, not by renamed people. Random seeds and repeated product/model runs measure variability; they are not independent companies.

## 7. Fully traceable action model

Every harness-controlled actor action, environment response and observable SUT transition must create an append-only event. Product-native events are imported with their identity/provenance when exposed; polled state changes are recorded as observations. Do not invent unobservable product-internal actions to make the trace look complete.

### 7.1 Canonical action-event schema

Each event must include at least:

```text
schema_version
event_id
run_id
scenario_id
approach                    # naive | coordination_engine_product | product_replay
event_origin                # harness | workspace_fixture | product_native | product_observation | replay
sequence_number
simulated_at
recorded_at
correlation_id
causation_event_id
actor_id
actor_type
actor_role
actor_scope_refs
action_type
phase
status                      # started | succeeded | failed | skipped | awaiting_input
summary                     # short factual summary of what the actor did
input_refs
output_refs
source_version_refs
constraint_refs
authorization_basis_refs
affected_entity_refs
state_before_hash
state_after_hash
duration_ms
error_code
error_summary
visibility_labels
```

Use normalized action types such as:

- `change_received`
- `source_authorized`
- `source_retrieved`
- `context_projected`
- `candidate_contract_loaded`
- `interpretation_validated`
- `clarification_requested`
- `brief_approved`
- `brief_revoked`
- `planning_scope_expanded`
- `constraint_admitted`
- `snapshot_frozen`
- `insertion_solve_started`
- `insertion_solve_finished`
- `repair_solve_started`
- `repair_solve_finished`
- `candidate_validated`
- `conflict_discovered`
- `task_assigned`
- `schedule_block_moved`
- `approval_requested`
- `approval_decided`
- `revision_rechecked`
- `proposal_committed`
- `outbox_action_enqueued`
- `external_action_attempted`
- `external_action_reconciled`
- `external_action_failed`
- `notification_relayed`
- `notification_delivered`
- `refresh_signal_emitted`
- `authorized_state_refetched`
- `task_acknowledged`
- `task_started`
- `task_blocked`
- `task_unblocked`
- `task_submitted`
- `task_reviewed`
- `task_accepted`
- `revision_requested`
- `workload_updated`
- `familiarity_updated`
- `estimate_corrected`
- `metric_recorded`
- `run_completed`

### 7.2 Event summaries

Every event shown in the UI must have a concise factual summary, for example:

> “Security reviewer availability checked for Tuesday–Wednesday; one protected private-team reservation imported as an opaque capacity block.”

> “Pinned insertion failed because the Wednesday review window overlaps a protected commitment; no existing task has been moved.”

> “Manager approved proposal `plan-004` at revision 18; one Hikari QA block moved by 60 minutes.”

Summaries describe inputs, actions, outputs, and status. Do not store or display hidden chain-of-thought, private scratch reasoning, or fabricated internal monologue. For model calls, record the permitted input manifest, template/model/schema versions, structured output reference, validation result, and usage/latency metadata—not private reasoning tokens.

### 7.3 Log storage and export

- Persist the canonical run log as append-only JSONL.
- Produce a human-readable timeline projection.
- Support CSV export for metric-relevant events.
- Include run manifest, simulation specification/harness commit, product build/commit when connected, seed, scenario version, product-reported solver/compiler/validator versions when available, configuration, input hashes, start/end times, and failure state.
- Hash immutable snapshots and material output artifacts.
- Preserve failed, infeasible, unknown, timed-out, and cancelled runs; do not keep only successes.
- Provide filters by actor, role, phase, action type, affected entity, approach, and visibility.

The full benchmark/judge trace may contain restricted synthetic details, but manager and employee POVs must come from product-authorised projections or labelled replay projections. “Full log” does not mean every simulated user may read every private event.

## 8. Manager and employee points of view

Do not build replacement manager and employee task-management applications. The real product owns those experiences. The harness must capture structured role-safe product projections, screenshots/deep links where supported and corresponding trace evidence, then present them inside a judge-facing replay/comparison surface. Before product integration, use visibly labelled replay projections only.

A development-only POV selector chooses which captured projection the judge inspects; it does not mint credentials, bypass product authorisation or imply production impersonation. Never reconstruct a richer employee view from the full benchmark ground truth.

### 8.1 Manager POV

The captured manager POV/judge panel must show, when the product exposes it:

- Existing commitments before the change.
- Change request and authorised source.
- Current affected subgraph relative to company scale.
- Agent/action timeline with live step summaries.
- Questions requiring clarification.
- Pinned insertion outcome.
- Proposed before/after schedule.
- Preserved commitments and every moved owner/time/deadline.
- Source-linked constraint and policy basis.
- Required approvals and their state.
- Interpretation, source freshness, feasibility, candidate validation, disclosure approval, schedule approval, internal commitment, external synchronisation, notification/refetch, employee acknowledgement and work-acceptance states separately.
- Side-by-side naive versus Coordination Engine metrics.
- Metric definitions, evidence class, numerator/denominator, source trace links and `NOT_MEASURED` reasons.
- A trace/log inspector with filtered and raw-event views.

### 8.2 Employee POV

The captured employee POV/judge panel must show only the employee’s product-authorised projection:

- Today, Upcoming, Blocked, and Submitted tasks.
- Approved employee brief and task purpose.
- Deliverable, acceptance criteria, expected active effort, work window, suggested segments, deadline, dependencies, and reviewer.
- What changed, what remained unchanged, who authorised it, and what the employee must do next.
- Privacy-safe assignment reason.
- Opaque protected or higher-priority reservations where underlying context is restricted.
- Notifications, acknowledgement, blocker/estimate correction, submission, and review actions.
- Current internal versus external synchronisation state when an approved task update has not yet reached its workspace.
- That employee’s action timeline and summaries.

The employee view must not expose raw planning snapshots, another team’s project title, confidential incident details, restricted sources, or manager-only diagnostics without a grant.

### 8.3 Judge/benchmark view

Provide a concise presentation view that can:

1. Reset to the initial snapshot.
2. Run or step through Change A.
3. Switch between manager and affected employee views.
4. Show the same change under the naive baseline.
5. Inject Change B into the committed Change A state.
6. Pause on contested capacity, priority policy, privacy projection, and approval.
7. Display the calculated comparison and scope labels.
8. Separate synthetic scheduled outcomes, recorded replay, actual product/harness runtime and live-model/provider measures.
9. Open the metric definition/provenance and complete trace for questions.

Support step, pause, resume, and deterministic replay. Avoid animations or artificial delays that make the benchmark appear slower or faster.

## 9. Metrics and comparison outputs

Compute metrics from canonical events, immutable snapshots, source/ground-truth manifests, concrete schedules, approval/commit/synchronisation records and neutral validation reports. Never hand-enter headline numbers or derive a success metric from a UI label.

### 9.1 Metric registry and measurement discipline

Define a versioned registry. Every metric observation must include:

```text
metric_schema_version
metric_definition_version
metric_id
run_id
scenario_id
approach_or_condition
evidence_class                 # synthetic | product_runtime | live_model | live_connector | recorded_replay
unit
direction_if_any
eligibility_rule
numerator_and_denominator_refs
source_event_or_artifact_refs
value
status                         # MEASURED | NOT_APPLICABLE | NOT_MEASURED | INVALID
missing_or_invalid_reason
```

Apply these guardrails:

- Keep deterministic simulated schedule time, product/harness wall or monotonic runtime, and model/provider latency separate.
- A missing source is not zero. A metric requiring a connected product, credentials, billing data or a live connector is `NOT_MEASURED` unless that evidence was actually collected.
- Preserve raw counts and units before calculating rates or percentage differences. Define eligibility, denominator and exclusions before the run.
- Include invalid, infeasible, unknown, timed-out, abandoned and failed-sync cases in the appropriate denominator unless a predeclared exclusion applies; publish exclusions and reasons.
- Report deadline movement separately from on-time completion. Do not count an unauthorised or hidden extension as efficiency.
- Do not convert messages, relay hops, synthetic duration or calendar density into salary, ROI, stress reduction or real productivity.
- Record dataset hash, split, seed, scenario/method versions, model/prompt/compiler/solver/validator versions, hardware, limits, connector modes, failures and uncertainty with every aggregate.

### 9.2 Mandatory primary-comparison scorecard

The following is the required judge-facing scorecard from the simulation study's **primary comparison baseline**. Every row must be implemented, computed for both the naive baseline and a real product-connected run, and linked to raw evidence. A replay may exercise rendering but leaves the product value `NOT_RUN`.

| Primary metric/aspect | Mandatory output |
|---|---|
| Existing commitments changed | Distinct pre-existing tasks/blocks changed; owner, start/end, deadline, protection and cancellation breakdown |
| Owner churn | Pre-existing owners changed; started-work and cross-team breakdown |
| Schedule displacement | Total, median and maximum absolute shifted minutes plus distribution |
| Preservation rate | Pre-existing affected commitments unchanged divided by affected commitments considered |
| Replan iterations/plan versions | Planning attempts, cascade cycles and regenerated versions before terminal outcome |
| Late conflict discoveries | Conflicts first detected after a downstream assignment/change was proposed |
| People contacted/interrupted | Unique employees/managers receiving coordination, clarification, approval or changed-task notices |
| Coordination relay hops | Reporting/project edges traversed by each normalised material change fact |
| Duplicate information transmissions | Repeated forwarding/delivery of the same normalised fact before action |
| Clarifications/approvals | Manager clarifications and approval decisions, separating required approvals from avoidable reconstruction questions |
| Invalid task delegations | Hard-check failures and invalid assignments divided by all assignments |
| Capacity overload | Overloaded active minutes, overlapping full-attention blocks and maximum daily load ratio |
| Dependency/deadline violations | Precedence violations, missed hard deadlines and total lateness minutes; deadline movement remains separate |
| Priority service time | Change B injection to accepted incident resolution and highest-priority blocking-task completion |
| Lower-priority collateral damage | Lower-priority commitments moved, deadlines changed and people newly affected |
| Scenario/key-work completion | Simulated time to terminal accepted state for affected work, Hikari and incident separately |
| Hard-constraint violations | Neutral-validator count by capacity, eligibility, dependency, authority and protection |
| Source/authority failures | Unsupported material constraints, unapproved priority/deadline changes and out-of-authority actions |
| Affected-scope size | Employees, teams, projects and tasks read/replanned/notified versus full company size; percentage excluded |
| Planning latency and model size | Retrieval, interpretation, planning and validation runtime by exposed stage plus affected variables/constraints when available |

### 9.3 Correctness, safety and terminal outcome metrics

| Metric | Required definition/output |
|---|---|
| Correct replan rate | Eligible cases ending in an accepted, authorised, independently valid, correctly committed and appropriately communicated repair divided by all eligible cases. Report feasible repair, correct no-change, correctly refused/infeasible, unknown/timeout and failed execution classes separately. |
| Terminal classification accuracy | Agreement with ground truth for `FEASIBLE`, `INFEASIBLE_WITHIN_SCOPE`, `INSUFFICIENT_SCOPE`, `INVALID_INPUT` and `UNKNOWN`; include a confusion matrix. |
| False-success rate | Runs reported complete/successful whose terminal plan, approval, commit, communication or synchronisation state fails an independent requirement. |
| Commit safety | Committed plans with any independently checked hard-constraint violation; show count/rate by capacity, eligibility, permission, dependency, review, deadline, protection, authority and tenant integrity. Zero observed is a bounded test result, not a universal guarantee. |
| Invalid task delegation | Assignments failing skill/qualification, access, reviewer/separation, capacity/window, protected-work or dependency checks; report count and rate over proposed assignments. |
| Dependency/acceptance violations | Precedence, lag, review, acceptance-gate and actual-release violations. |
| Deadline performance | Hard deadlines missed, total/median/max lateness, and key deadline attainment, using requested, agreed and forecast dates without rewriting history. |
| Source grounding and accuracy | Material constraints with valid source/version lineage or explicit confirmation; missed expected constraints, false constraints, wrong source/version attribution, stale evidence and unsupported claims. |
| Authority/privacy failures | Unauthorised retrievals, citations/disclosures, approvals, priority/deadline changes, schedule moves, commits and external writes; break down by failure type and viewer. |
| Clarification behavior | Required ambiguities correctly escalated, unnecessary questions, material ambiguities missed and unsupported assumptions admitted. |
| Stale/concurrent commit safety | Stale proposals correctly rejected, incompatible plans committed from the same base revision, and authority/revision rechecks performed. |
| Communication correctness | Required recipients correctly notified, missed recipients, unauthorised recipients, materially incorrect messages and content-free refresh/refetch correctness. |
| Partial-failure honesty | Partial external failures represented as partial, not success; internal commitment and per-action synchronisation states remain distinguishable. |

### 9.4 Stability, workload and scheduled-outcome metrics

| Metric | Required definition/output |
|---|---|
| Existing commitments changed | Distinct pre-existing tasks/blocks whose owner, start/end, agreed deadline, protection or cancellation changes; report each change type. |
| Owner churn | Pre-existing task owners changed; report started-work and cross-team owner changes separately. |
| Schedule displacement | Absolute minutes shifted for pre-existing blocks; report sum, median, maximum and distribution. |
| Preservation rate | Pre-existing affected commitments unchanged divided by pre-existing affected commitments considered; publish the affected-set definition. |
| Deadline movement | Requested-to-agreed, prior-agreed-to-new-agreed and agreed-to-forecast movement; separate authorised extensions, unapproved movement and forecast-only movement. |
| Protected-work violations | Started, locked or otherwise protected commitments moved without the required authority. |
| Fragmentation and continuity | Segment count, additional segment starts, minimum-run violations, handoffs and task owner continuity. |
| Capacity overload | Active minutes above capacity, overlapping full-attention blocks, people affected and maximum daily/weekly load ratio. |
| Workload balance | Distribution of scheduled active minutes/load ratios across eligible affected employees; treat this as operational balance, never a performance score. |
| Priority service time | For Change B, simulated elapsed time from incident injection to accepted resolution and to completion of the highest-priority blocking tasks. |
| Lower-priority collateral damage | Lower-priority commitments moved, deadlines changed, owners changed and people newly affected while serving higher-priority work. |
| Scenario/key-work completion | Simulated elapsed time to terminal accepted state for all newly required/affected work and for Hikari/incident separately. This is scheduled/simulated time, not measured human productivity. |
| Objective vector | Recorded lexicographic service, continuity, deadline/displacement, fragmentation/balance and familiarity components, plus solver result/bounds when genuinely available. |

### 9.5 Coordination, disruption and locality metrics

| Metric | Required definition/output |
|---|---|
| Replan iterations/versions | Planning attempts, local conflict-repair cycles and regenerated proposal versions before terminal outcome. |
| Late conflict discoveries | Conflicts first found after a downstream assignment/change was already proposed. |
| People contacted/interrupted | Unique employees/managers receiving a coordination message, clarification, approval request or changed-task notice. |
| Coordination relay hops | Human/reporting edges traversed for each normalised material change fact before reaching the responsible actor; direct authorised system delivery counts once per target. |
| Duplicate information transmissions | Repeated delivery/forwarding of the same normalised fact to intermediaries or the same recipient before action. |
| Clarifications and approvals | Required clarification questions, avoidable reconstruction questions, required approval decisions, approval escalations and approval renewals after staleness. |
| Coordination action burden | Counts of deterministic actor clarifications, approvals, reviews, corrections, coordination actions and failed attempts; do not convert these counts into real human minutes. |
| Affected-scope size/compression | Employees, teams, projects, tasks and sources read, replanned, moved and notified; compare each with full company state and report the percentage excluded. |
| Boundary-fact use | Reduced availability/eligibility/protection constraints imported from adjacent/private work, with zero protected titles/content leaked. |
| Relevant-evidence retrieval | When reviewed labels exist: relevant-evidence recall/precision, permitted records/excerpts retrieved, omitted required evidence and unnecessary context volume. |

### 9.6 Latency, execution reliability and resource/cost metrics

| Metric | Required definition/output |
|---|---|
| Primary end-to-end replanning latency | Product/harness elapsed time from authorised change submission to a correctly committed and appropriately communicated terminal plan, using deterministic actor responses and excluding simulated task-duration advancement. |
| Stage latency | Retrieval, interpretation/model, semantic admission, snapshot/compile, insertion solve, repair solve, candidate validation, explanation, clarification, approval, revision recheck, commit, external execution/reconciliation, notification/refetch and acknowledgement. |
| Machine planning latency | Retrieval through independent validation wall/monotonic time on declared hardware/configuration, separate from simulated task completion. |
| Planner scale | Affected-model variables, constraints, employees/tasks/slots, memory if available, solver status, objective bounds if valid, retries and timeout/cancellation. |
| Execution safety | Wrong writes, duplicate external effects, stale overwrites, lost intents and actions applied without exact approval. |
| Recovery correctness | Durable jobs/actions recovered after injected crash/timeout, duplicates suppressed, uncertain writes reconciled and later human edits preserved. |
| Recovery time/attempts | Machine time and retry/reconciliation attempts to reach a truthful terminal synchronisation state. |
| Refresh/reconnect reliability | Persisted notifications recovered after lost signal/offline period; missed, duplicate and stale refresh outcomes. |
| Cost per accepted replan | When actual price/configuration data exist: model, retrieval/embedding, retries, solver/worker compute, storage and connector costs attributable to accepted outcomes. Synthetic operation counts are not currency. |
| Resource usage | Model request/token counts, permitted input bytes/excerpts, solver CPU/wall time, peak memory when available, storage writes/bytes, connector calls, pages, retries and emitted events. Fixture operations are counts, not fake currency cost. |

### 9.7 Estimation, learning and employee-control metrics

| Metric | Required definition/output |
|---|---|
| Estimate quality | On chronologically held-out comparable accepted work: active-effort error and uncertainty coverage with sample counts; report elapsed time separately. At minimum show MAE/median absolute error and the declared treatment of missing active effort. |
| Estimator comparison | Task-class prior versus skills-only versus skills-plus-recent-context on identical held-out cases. Do not let later evidence leak into earlier predictions. |
| Evidence maturity correctness | Exposure, submission and accepted contribution remain distinct; assignment or elapsed waiting never becomes confirmed proficiency. |
| Profile correction integrity | Corrections/disputes create superseding versions while historical planning snapshots remain reproducible. |
| Employee-control events | Estimate/access/input objections, unavailable-time reports, corrections and their resolution; counts are workflow behavior, not a worker-quality score. |

### 9.8 Conditional product/model metrics

Do not fabricate these during a credential-free overnight run:

- **Interpretation:** precision/recall for material constraints, false/missed constraints, authority error, correct clarification, source attribution, schema/semantic rejection, variability across repeated calls, model latency, tokens and actual cost.
- **Retrieval ablation:** full permitted versus bounded context relevant-evidence recall, privacy failures, token/byte reduction, downstream correctness and cost using the same model/configuration.
- **Product-internal scale:** compiler/solver variables, constraints, memory, objective bounds and detailed stage timings only when the product exposes trustworthy run metadata.
- **Actual provider cost:** model, storage, compute and connector currency cost only when the connected product supplies attributable usage and an explicit price configuration.

### 9.9 Benchmark procedure, aggregation and headline calculations

For every method/scenario pair:

1. Reset to the same immutable starting snapshot.
2. Inject the same event, source versions, policies, estimates, permissions and authorised freedoms.
3. Run the method and persist its complete action/communication log, including terminal failures.
4. Reset before the next method.
5. Score every terminal output with the same neutral validator and ground-truth manifest.
6. Compute raw observations before aggregates and retain all source artifact references.

Before comparing, verify the canonical baseline input manifest and product seed/import mapping are semantically equivalent. If required product fields cannot be mapped without changing facts or freedoms, classify the comparison `INVALID` and report the mismatch. Recorded replay runs never enter the product side of headline calculations.

Required main comparison:

```text
fewer_changed_commitments = 1 - system_changed / naive_changed
fewer_replans = 1 - system_iterations / naive_iterations
fewer_relay_hops = 1 - system_relay_hops / naive_relay_hops
fewer_invalid_delegations = naive_invalid_rate - system_invalid_rate
capacity_overload_difference = naive_overload_minutes - system_overload_minutes
critical_work_time_difference = naive_incident_completion - system_incident_completion
preservation_rate_difference = system_preservation_rate - naive_preservation_rate
correct_replan_rate_difference = system_correct_replan_rate - naive_correct_replan_rate
```

Handle zero denominators explicitly. For Changes A and B, show exact raw numbers and trace links. For multiple generated cases, report eligible case count, success/failure-class counts, median and distribution/IQR or declared percentiles; do not present seeded variants as independent customers or infer population-wide causal effects. Report method/configuration changes as different result groups. Label every automated result **synthetic benchmark** or **simulated workload**.

## 10. Suggested project organization

Adapt to working code if the repository has evolved. Otherwise prefer a contained structure similar to:

```text
simulation/
  .gitignore
  README.md
  PLAN.md
  STATUS.md
  DECISIONS.md
  CHANGELOG.md
  REQUIREMENTS_TO_EVIDENCE.md
  pyproject.toml
  src/coordination_sim/
    contracts/
    generation/
    scenarios/
    actors/
    workspace_environment/
    baselines/naive/
    sut/
      replay/
      product/
      mapping/
    observation/
    validation/
    tracing/
    metrics/
      registry/
      analysis/
    service/
  ui/
    src/
      judge/
      pov_replay/
      trace/
  fixtures/
    organisations/
    profiles/
    company/
    work/
    sources/
    connectors/
    scenarios/
    expected/
  evals/
    manifests/
    interpretation/
    retrieval/
    scheduling/
    stability/
    execution/
  runs/                  # ignored generated output
  tests/
```

If root workspaces, the planned backend package, or the desktop app already exist, treat them as read-only references. Implement every required integration adapter below `simulation/`; do not update a root workspace or product package to register the simulation. Generated run artifacts must be ignored through `simulation/.gitignore` unless intentionally committed as small, reviewed golden fixtures.

## 11. Implementation sequence

Work in vertical slices:

1. Inspect the repository and record what exists versus what is only specified.
2. Define versioned benchmark, workspace-environment, SUT-adapter, trace, scenario, validation and metric-registry contracts plus the product-component requirements-to-evidence matrix.
3. Implement deterministic clock/IDs, append-only trace storage, and replay.
4. Generate and validate the `tiny` fixture, including realistic profiles and minimal Teams/calendar/Planner/SharePoint/development-source adapters.
5. Implement the neutral validator and tiny oracle cases.
6. Implement the naive coordinator with complete action/communication logging.
7. Define the SUT capability/seed/reset/drive/observe/export contract and implement the non-claiming recorded-replay adapter.
8. Implement product contract mapping scaffolding and contract tests without implementing product planning or workflow logic.
9. Run Change A and Change B through the naive baseline and recorded replay to verify orchestration, POV capture, validation, metric computation and judge presentation; keep product results `NOT_RUN`.
10. Add the complete primary-comparison scorecard, metric provenance and judge trace inspector.
11. Complete 5–10 hand-reviewed golden cases, including infeasible, revoked-source, concurrent-commit, no-impact and software/HR shared-specialist compatibility cases.
12. Scale the generator to `medium`, then `demo`, while preserving a small affected subgraph.
13. After the runner is reliable, expand toward 30–40 varied/held-out case manifests without blocking the core demo.
14. Document the exact future FastAPI/product adapter requirements and how actual product contracts replace replay mappings.
15. Audit generated profiles, sources, metrics and POV projections for coherence, privacy, fair comparison and non-surveillance boundaries.
16. Run tests and record actual outputs, `NOT RUN` prerequisites and limitations.

Do not spend the first half of the hackathon generating 8,000 rows before a tiny environment → naive/replay adapter → neutral score → metrics → judge replay run works. Do not start implementing missing product functionality to make the harness appear complete; record the adapter capability as `NOT_AVAILABLE` and continue with harness work.

## 12. Required tests

### 12.1 Mandatory harness tests — no product required

- Repository-boundary checks detect any implementation-created change outside `simulation/` and confirm the source DOCX/prompt remain byte-identical.
- Material method, scenario, metric, schema and adapter changes append a versioned changelog entry without relabelling older manifests.
- Identical seed/configuration reproduces equivalent company, scenario, naive-run and replay hashes.
- Generated organisation totals, memberships, roles, capacity, task lifecycles, lineage, grants and second-tenant separation satisfy declared invariants.
- Workspace environments implement capability/version/freshness/revocation behavior, redact calendar subjects/private reasons, deduplicate exported blocks and expose stale, unavailable, duplicate-event, uncertain and partial-write outcomes.
- Canonical fixture-to-product mapping validation detects missing, broadened or changed facts, policies, permissions, estimates, deadlines and freedoms before comparison.
- The naive coordinator implements every Section 6.1 component with deterministic tie-breakers/iteration cap, receives the equivalent authorised input and cannot use the neutral scorer as a repair oracle.
- The neutral scorer independently checks tenant/entity integrity, eligibility/access, effort/segments, capacity/windows/budgets, dependencies/reviews, deadlines, protection, priority authority, approvals and disclosure.
- Tiny brute-force/oracle cases and deliberately mutated candidate schedules detect errors without importing any product planner/compiler/validator code.
- Change A, Change B and the software/HR compatibility case contain the declared ground truth, privacy boundaries and primary-scorecard expectations.
- Every harness action/environment response and observed/replayed transition has monotonic, causally valid provenance; no product-internal action is fabricated.
- The recorded-replay adapter is visibly labelled and cannot populate product-result headline cells, product latency or product correctness claims.
- SUT adapter contract tests cover capability discovery, mapping, reset/seed, event submission, deterministic actor response, observation, POV capture, terminal export and unsupported-capability reporting.
- Missing product connectivity or capability produces `NOT_RUN`/`NOT_AVAILABLE`, never a replayed success.
- Manager and employee replay projections contain only their declared permitted synthetic facts.
- Every mandatory primary-comparison metric and remaining automated metric agrees with hand-checked tiny golden observations, including zero denominators and terminal failures.
- Metric observations record definition version, evidence class, unit, eligibility/denominator, artifact references and status; simulated schedule time, product/harness runtime and provider latency remain separate.
- Failed, infeasible, unknown, timed-out and failed-sync cases remain in declared outcome denominators; deadline movement cannot improve on-time results invisibly.
- Missing product/model/connector/cost evidence yields `NOT_MEASURED` rather than zero.
- Gold labels/expected answers are inaccessible to the naive coordinator, SUT input projection and replayed product payloads.
- Invalid JSON/source formats, unknown IDs, cycles, negative effort and timezone/DST boundaries fail safely.
- No secret, bearer token, raw private calendar subject, hidden model reasoning, fabricated chain-of-thought or forbidden source body appears in logs, exports or judge projections.
- An architecture-boundary test prevents imports or implementations of product Z3 compilation/solving, approval policy, commit/outbox, notification, learning or employee-workflow modules inside the harness.

### 12.2 Connected-product conformance tests — run when supported

Drive these through `SystemUnderTestPort`; do not implement their behavior in the harness. Each unsupported case records the exact missing product capability:

- Tenant isolation, forged role/company claims and an administrator without content grants cannot broaden access.
- Restricted brief drafts, audience expansion, revoked access and malicious source instructions do not grant disclosure, authority, tools or arbitrary solver expressions.
- Product source ingestion preserves versions/freshness and permission boundaries from Teams, Planner, calendar, SharePoint/OneDrive and development fixtures.
- Overlapping flexible windows with non-overlapping effort are feasible; exclusive meetings conflict; passive waits consume no active capacity.
- Missing qualification/reviewer/access is rejected; equal-priority independent work can proceed; Critical work receives contested capacity without moving protected/unrelated work.
- Change A exposes pinned-insertion outcome; failed insertion, full infeasibility, insufficient scope and timeout/unknown remain distinct.
- Exposed objective/solver metadata is preserved exactly; absent metadata remains `NOT_AVAILABLE`.
- Stale/competing commits, changed memberships and revoked sources revalidate or reject safely.
- Approval, commitment, external synchronisation, notification/refetch, acknowledgement and acceptance remain separate under partial failure.
- Injected worker/provider failure recovers durable actions without duplicates or overwriting a later human edit; lost refresh signals recover current persisted state.
- Planned completion does not release an acceptance-gated successor before product-recorded acceptance.
- If product learning is enabled, assignment/start/submission/acceptance and corrections remain versioned and waiting does not become effort or proficiency.
- If optional agent execution is enabled, product permission, budget, timeout/cancellation, accountable-human and independent-review gates hold.

## 13. Acceptance criteria

### 13.1 Harness-ready acceptance — product not required

- All implementation-created, modified, renamed, and generated files are below `simulation/`; the source DOCX is unchanged and the final repository-boundary check is recorded.
- It runs locally from documented commands without product-backend or Gemini credentials.
- `CHANGELOG.md` explains every material evolution of the implemented approach and links each new benchmark method to new manifests rather than relabelling old results.
- It can generate, reset and run Changes A and B deterministically through the naive baseline and labelled replay adapter.
- It has 5–10 hand-reviewed golden cases before generated case expansion; any progress toward the 30–40-case master-spec target is reported as an exact actual count.
- The main scenarios derive their authorised facts from coherent, separately permissioned Teams, calendar, Planner, SharePoint/OneDrive and development-source environments.
- All connector fixtures are visibly labelled simulated, and no result is presented as evidence that live Microsoft or other provider APIs were tested.
- Synthetic company, employee, project, task and context profiles are structurally coherent, scheduling-relevant, non-sensitive and free of prohibited personality/productivity ranking fields.
- It provides the judge comparison/trace surface and clearly labelled manager/employee replay POVs without duplicating a task-management product.
- Its requirements-to-evidence matrix covers every product-component row in Section 4.6 with honest `IMPLEMENTED`, `SIMULATED`, `NOT RUN` or `FUTURE PRODUCT` evidence.
- Every harness actor/environment action and observable/replayed transition has a step-level factual summary and append-only provenance.
- The SUT contract, mapping validator and replay adapter pass; replay output cannot enter product headline results.
- The naive baseline is reproducible and not intentionally crippled.
- The neutral validator and every mandatory primary-scorecard computation pass hand-checked golden cases.
- Product-side values remain `NOT_RUN` until a real product adapter runs; conditional model/provider/cost metrics remain `NOT_MEASURED` when evidence is absent.
- The UI shows company scale without attempting to render all people/tasks at once.
- No product Z3 planner, approval/commit/outbox service, connector ingestion pipeline, learning service or manager/employee application is reimplemented in the harness.
- Tests and actual command outputs are documented honestly.

### 13.2 Product-connected comparison gate

A side-by-side Coordination Engine result may be shown to judges only when:

- A real adapter identifies the exact product commit/build, API/schema versions and supported capabilities.
- The semantic input-mapping check proves the product and naive baseline received equivalent facts, permissions, estimates, policies, deadlines and freedoms.
- The product—not replay or harness code—processes Changes A and B, with Change B injected into the actual resulting Change A state.
- Product manager/employee projections and terminal schedule/proposal/approval/commit/notification evidence are captured through supported interfaces.
- The neutral validator scores the exported concrete product outcome, and every primary-comparison metric links to product or harness evidence.
- Failed, unavailable, partial, unknown and timed-out states remain visible; unexposed internal fields are `NOT_AVAILABLE` rather than inferred.
- Every comparison is labelled **synthetic benchmark** and does not claim measured employee productivity, live provider validation or guaranteed real-company performance.

## 14. Deliverables

Deliver:

1. Runnable deterministic company/workspace generator and scenario runner.
2. Reproducible naive coordinator implementing every primary-baseline component.
3. Neutral independent scoring validator and tiny oracle cases.
4. Versioned `SystemUnderTestPort`, product mapping contract, non-claiming recorded-replay adapter and real-product adapter scaffold/integration guide.
5. Judge/benchmark UI with step/pause/resume/replay, captured manager/employee POV panels, metric provenance and trace inspection.
6. Append-only JSONL trace plus human-readable and CSV exports.
7. Scenario, input-mapping, product-capability, run and benchmark manifests with versions and hashes.
8. Calculated naive metrics now; product comparison cells remain `NOT_RUN` until the real adapter runs.
9. Tiny golden fixtures/tests; medium/demo generated fixtures or generation commands.
10. README covering setup, commands, architecture boundary, product-adapter contract, workspace environments, trace schema, metric definitions and limitations.
11. Requirements-to-evidence matrix identifying implemented, simulated, not run, and future-backend capabilities.
12. Durable `PLAN.md`, `STATUS.md`, and `DECISIONS.md` handoff files containing the final checks, actual results, limitations, and next action.
13. Append-only `CHANGELOG.md` documenting approach versions and their validation/benchmark impact.
14. Versioned synthetic organisation, employee, project, task, source and connector fixtures with schema/integrity validation.
15. Versioned metric registry, raw observation export, aggregate analysis and provenance drill-down covering the mandatory scorecard and remaining automated metrics.
16. Product-component requirements-to-evidence matrix with explicit simulation and non-claim boundaries.
17. Five to ten hand-reviewed golden cases plus exact generated/held-out case counts; never claim the 30–40 target unless those manifests exist and run.

## 15. Final implementation directive

Build the smallest complete and inspectable environment that can evaluate the product rather than recreating it. The harness must generate realistic authorised conditions, run the fixed naive comparator, drive and observe the real Coordination Engine through a thin adapter, independently score both outcomes and explain every reported number. Make no change outside `simulation/` while doing so.

The simulation should make this claim—and only this claim:

> Under the declared synthetic company, policies, inputs and workload, the identified Coordination Engine product build produced the recorded outcomes relative to the reproducible naive coordinator.

This claim may be made only after a real product-connected run. Replay mode must instead state that the harness is ready and product results are not yet measured. Neither mode may claim measured human productivity, customer validation or guaranteed performance in a real company.
