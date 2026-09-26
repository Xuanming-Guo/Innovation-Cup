# Simulation work

## Mission and scope

This directory contains the synthetic company, deterministic workspace fixtures, naive
coordinator, independent benchmark validator, system-under-test adapter, metrics and judge
replay. It evaluates ALTO; it must not become a second product implementation.

Use **ALTO** in current prompts, narration, captions, scripts and visible product labels.
Retain existing package names, schema identifiers, source filenames and historical run
artifacts for compatibility and provenance. Older reference documents may use the former
product name; their naming does not override ALTO in new material.

These instructions supplement the [root AGENTS.md](../AGENTS.md) for explicitly requested
simulation work. Follow the current user request. Reading a historical plan or implementation
prompt does not authorise resuming its unfinished milestones. A documentation or video task
does not authorise benchmark execution or harness changes.

All demo-video prompts, scripts, storyboards, assets, editing projects, renders and production
evidence belong in `simulation/demo/`. Read [demo/AGENTS.md](demo/AGENTS.md) for that work.
The harness's benchmark `demo` preset and judge UI remain harness features; their source code,
fixtures and benchmark artifacts retain their existing locations.

## Read before changing behaviour

- Read [README.md](README.md), [STATUS.md](STATUS.md), [PLAN.md](PLAN.md) and relevant
  [DECISIONS.md](DECISIONS.md) entries for the current implementation and outstanding work.
- Follow [simulation_implementation_prompt.md](simulation_implementation_prompt.md) and the
  [simulation context](coordination_engine_simulation_context_v2.docx) for scenario, baseline
  and evaluation requirements. These are immutable control inputs unless the user explicitly
  requests their revision. Existing status notes may describe older product capabilities.
- Use the current [product implementation ledger](../docs/implementation-status.md) and
  inspect published product contracts when assessing integration readiness. Follow the
  [product specification](../docs/coordination_engine_master_v2.md) and
  [implementation contract](../docs/implementation_master_prompt_v2.md) for product boundaries.
- Before adapter changes, read [PRODUCT_ADAPTER.md](PRODUCT_ADAPTER.md). Before scoring or
  fixture changes, inspect [the metric registry](metrics/registry.v2.json),
  [golden review](evals/golden-review.md) and affected tests.

## Repository and execution boundaries

- Keep simulation implementation writes, dependencies, environments, caches, temporary files
  and generated artifacts under `simulation/`. Product files outside this directory are
  read-only for simulation implementation unless the user separately authorises changes.
- Preserve user edits and historical artifacts. Git state is user-managed; do not branch,
  commit, stage, stash, merge or rebase without explicit authorisation. If authorised, follow
  the [GitHub workflow](../docs/development/github-workflow.md).
- Keep searches and checks scoped to the requested simulation files. Ordinary application
  and repository-wide checks must continue to exclude this tree.
- Use the existing local environment and pinned dependencies. Do not register a root
  workspace, install global dependencies or change external services for a harness task.
- Keep source prompts, fixtures and recordings versioned. Never overwrite an old run to
  reflect a new method; create a new run ID and preserve its original inputs and manifest.

## Architecture and fair comparison

- Own environment generation, scripted actors, the documented greedy/cascade comparator,
  independent scoring, observation and presentation here. Do not duplicate the product's
  Gemini interpretation, Z3 planner, approval, commitment, outbox, notifications, learning or
  manager/employee application. The harness must not call Gemini directly.
- Connect through supported product APIs and the versioned system-under-test port. Validate
  semantic input mapping; do not write undocumented product tables or manufacture product
  events. Missing product capabilities remain `NOT_RUN` or `NOT_AVAILABLE`.
- Give both approaches equivalent authorised facts, estimates, policies, deadlines and
  movement freedoms. Inject Change B into each approach's actual Change A result state.
- Preserve the declared baseline: local greedy choices, bounded cascade repair and reporting
  relays. Do not deliberately assign ineligible people, leak context or globally reshuffle
  tasks to make the product look better. Keep optional ablations/supporting cases separate.
- Keep gold labels inaccessible to planners and simulated actors. The neutral validator
  scores terminal results independently; it must not repair plans or guide baseline retries.
- Derive graphs from canonical relational records. The company inspector is a judge view,
  not authentication. Manager/employee views use only their permitted projections.
- Preserve company isolation, source authority, reduced private capacity, one shared human
  capacity budget, protected work and acceptance gates. Do not weaken these for a demo.

## Evidence and metrics

- Label synthetic environments and authored replay explicitly. Replay is not a product run
  and cannot populate product-improvement headlines. Fixture APIs are not live connectors.
- Record metric definitions, units, denominators, evidence classes, source artifacts, method
  versions and missing reasons. Null is not zero; retain failed, unknown and partial cases.
- Separate imported/read scope from considered, replanned, moved and notified scope. Separate
  new tasks, changed commitments, owner changes, plan attempts and committed revisions.
- Keep simulated work duration, measured harness runtime, actual product/model/solver time
  and human productivity distinct. Do not turn shifted calendar minutes into labour savings.
- Version claims to the actual evidence. DOM or data tests do not establish browser layout;
  browser checks do not establish native operation. Zero observed violations is run-scoped.
- Preserve actual sources, actions and checks; never invent internal reasoning or traces.

## Verification and handoff

- For behaviour changes, run the strongest relevant tests using the commands in README.
  Check small deterministic cases and affected goldens before larger presets; inspect traces,
  validation and metrics as well as process exit codes. Do not regenerate all runs by default.
- For documentation-only work, verify links and instructions without running benchmarks or
  the acceptance suite. For video work, use the narrower checks in `demo/AGENTS.md`.
- The existing boundary guard contains historical branch/index assumptions. Report a mismatch
  against the current authorised task; never discard user edits, change Git state or weaken
  the guard merely to obtain a pass.
- Update STATUS and the requirements-to-evidence map when capability/evidence changes; update
  PLAN, DECISIONS and CHANGELOG when their scope is affected. Governance-only edits do not
  establish new benchmark results or require rewriting historical reports.
- Report commands actually run, results, limitations and remaining prerequisites. Keep all
  unavailable product, live-provider, browser or native checks explicitly unverified.
