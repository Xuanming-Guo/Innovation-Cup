# Simulation approach changelog

This file records material changes to the proposed simulation method. It is separate from:

- `STATUS.md`, which records what currently works and the actual commands/checks run;
- `DECISIONS.md`, which records why current design choices were made; and
- runtime JSONL traces, which record simulated actor actions.

The entries below describe changes to the implementation specification only. They are not claims that the simulation, integrations, benchmark results or product backend have been implemented or validated.

## Unreleased

### Added

- A judge/developer synthetic-company inspector with searchable, paginated
  profiles for every employee plus complete team, project and task indexes.
- A derived coordination graph over the existing relational task, dependency,
  ownership, evidence and team links, including impact highlighting and an
  accessible record fallback. No dedicated graph database was introduced.
- Projection-local task graphs for the manager, Security and Delivery replay
  views; these are built only from each stored permitted projection.
- An optional `portfolio` supporting scenario that pulls forward 12 work
  packages, explicitly authorises a bounded response pool and produces 12 owner
  changes across four teams. It is excluded from the primary A/B comparison.
- Archived repository-user desktop Chrome evidence and a machine-readable browser
  QA manifest under `evals/browser-qa/`.

### Changed

- The UI formats schedule slots as Tokyo day/time labels instead of presenting
  raw JSON as the primary card display.
- Browser acceptance now distinguishes the archived pre-inspector desktop pass,
  successful user loopback execution, the new inspector pass and narrow-layout
  QA rather than treating browser/service evidence as a single binary check.
- The overnight boundary guard now permits reviewed commits after its recorded
  bootstrap point while continuing to reject non-simulation worktree changes,
  branch drift, staged mutations and immutable source changes.

### Validation impact

- Added inspector and wide-impact scenario tests plus a fifth JavaScript
  interaction-logic test. A fresh browser pass remains required for the new UI.
- The supporting portfolio case may demonstrate broad coordination cost, but it
  must not replace the mandatory transparent naive baseline or enter headline
  product-improvement claims.

## 0.5.0 — 2026-09-25

### Added

- A system-under-test adapter boundary so the harness can drive and observe the actual Coordination Engine without copying its domain workflow, Z3 planner, approval engine, commit logic or employee application.
- A non-claiming recorded-replay adapter for developing the harness before the product integration exists.
- An explicit mandatory scorecard containing every metric and comparison aspect from the simulation study's primary naive-coordinator baseline.

### Changed

- Reframed the deliverable from a second implementation of Coordination Engine into a reusable simulation environment, comparator and measurement harness.
- Manager and employee POVs are now captured product projections or clearly labelled replay projections, not duplicate task-management applications.
- Product workflow stages are observed and asserted through the adapter rather than reimplemented under `simulation/`.
- Human-study instruments and measures are removed from this simulation scope.

### Validation impact

- A recorded product replay can validate harness behavior but cannot produce a claim about current product correctness, latency or improvement.
- Product-result cells remain `NOT_RUN` until a real product adapter completes the scenario and exports the required evidence.
- Adapter contract, fairness, provenance and baseline-scorecard tests replace duplicated product-planner implementation tests.

### Open limitations

- Until the product exposes a compatible synthetic-tenant seed/reset, event, projection and evidence interface, only the environment, naive baseline, validator and replay plumbing can run end to end.
- Live provider and product deployment claims remain outside this harness.

## 0.4.0 — 2026-09-25

### Added

- A product-component coverage matrix derived from the latest Coordination Engine implementation master prompt.
- Full post-commit lifecycle coverage: durable external actions, private refresh/refetch, employee acknowledgement, execution, submission, review, acceptance, learning updates and later repair.
- A complete metric registry covering correctness, safety, disruption, coordination effort, latency, priority outcomes, locality/privacy, connector reliability, cost, estimation and optional human-study outcomes.
- Layered evaluation requirements for interpretation, retrieval, scheduling, stability, execution and end-to-end workflow behavior.
- A product-compatibility HR onboarding/shared-specialist case that remains outside the two-story judge demo.

### Changed

- The benchmark now distinguishes required automated synthetic metrics from metrics that require a real model, human timing, provider billing, live connectors or consenting participants.
- End-to-end success now requires a correctly committed and appropriately communicated plan, not merely a feasible solver result.
- Scenario development starts with a small high-quality golden suite, then targets 30–40 varied cases only after the harness is reliable.

### Validation impact

- Added metric provenance, unit, denominator, eligibility, exclusion and `NOT_MEASURED` checks.
- Added lifecycle, objective-vector, false-success, recovery, employee-comprehension and method-comparison checks.
- Existing `0.3.0` benchmark manifests, if any are later created, must not be relabelled as `0.4.0` results.

### Open limitations

- The overnight simulation cannot establish live connector reliability, human productivity, commercial ROI, native desktop support or user-experience outcomes without the corresponding external systems or consenting study.
- Optional LLM-only, full-context retrieval and unconstrained-rescheduling ablations must remain `NOT RUN` when credentials, reviewed expected labels or time are unavailable.

## 0.3.0 — 2026-09-25

### Added

- Required realistic synthetic company, tenant, team, employee, project, task and source-context profiles.
- Required simulated Microsoft Teams, Outlook/Exchange calendar, Microsoft Planner and SharePoint/OneDrive adapters, plus a selected development-work source.
- Required cross-workspace source manifests, connector capability/version/freshness metadata, revocation, duplicate delivery, unknown availability and partial-write cases.
- Added a second small synthetic tenant for automated isolation checks without expanding the judge-facing story.

### Changed

- The two main scenarios must now derive facts from separately permissioned workspace artifacts rather than a single omniscient fixture.
- Employee profiles must separate declared skills, confirmed qualifications, accepted evidence, familiarity, permissions, operational workload and estimate versions.
- Task fixtures must include complete executable contracts, source lineage, disclosure rules and realistic lifecycle state.

### Validation impact

- Added integrity, realism, tenant-isolation, connector-contract, privacy-reduction, deduplication, stale-source and partial-synchronisation test requirements.
- Future benchmark runs using this method require new versioned manifests; results from an earlier method must not be silently relabelled.

### Open limitations

- All workspace connectors remain required simulations until an explicitly authorised live path is separately implemented and tested.
- The exact live Microsoft tenant scopes and provider behavior remain external integration questions, not facts established by fixtures.

## 0.2.0 — 2026-09-25

### Added

- A strict requirement that implementation writes remain inside `simulation/`.
- Durable `PLAN.md`, `STATUS.md` and `DECISIONS.md` handoff files for a long-running implementation agent.
- A repeatable plan, implement, test, inspect, repair and document loop.

### Changed

- Git state is user-managed and read-only to the implementing agent.
- Files outside `simulation/`, the source DOCX and the implementation prompt are immutable during execution.

### Validation impact

- Added startup, checkpoint and final repository-boundary checks.

### Open limitations

- The coordination files are required deliverables but do not exist until implementation begins, other than this changelog.

## 0.1.0 — 2026-09-25

### Added

- Initial implementation specification for a deterministic Coordination Engine simulation.
- A reproducible naive-coordinator comparison, bounded Z3 path, independent validator, manager/employee/judge views and append-only action traces.
- The Hikari deadline-pull-in and Critical SSO incident scenarios derived from the simulation-study context.

### Validation impact

- Defined initial acceptance criteria and required synthetic benchmark metrics.

### Open limitations

- This version established the intended approach; it did not implement or execute the simulation.

## Specification 0.5.0 / harness 0.1.0 — 2026-09-26 — supervised bootstrap

This append begins implementation history. The earlier entries above remain
specification history; the governing specification stays at 0.5.0 unchanged.

### Added

- Simulation-local PLAN, STATUS, DECISIONS, README and requirements/evidence map.
- Pinned Python/uv/Pydantic manifest and lock, isolated environment/cache/temp
  paths, ignore rules and an offline bootstrap command.
- Versioned benchmark subset, deterministic tiny fixture (25 employees, 4 teams,
  75 tasks), one authored no-impact replay, independent concrete scoring and one
  provenance-backed metric definition/observation.
- Immutable per-attempt evidence directories, append-only event trace, timeline,
  schema export, input/artifact/code hashes and boundary/non-claim tests.

### Changed

- Previously only the implementation specification existed. The supervised
  bootstrap now executes a fixture → replay → scoring → observation path so
  subsequent unattended slices have a runnable starting point.
- Chose an explicitly authored synthetic replay for the first path; it is not a
  product recording and does not substitute for the still-unimplemented full
  naive comparator. Product results stay `NOT_RUN`.

### Fixed

- Corrected a test fixture variable named `run` that shadowed unittest's runner
  method during the first test execution. STATUS retains that failure.

### Validation impact

- Regression coverage includes deterministic hashes, malformed/cyclic/foreign
  references, mutated schedules, half-open capacity intervals, replay digest
  mismatch, missing evidence, retained failures, metric provenance and boundaries.
- Scope is explicitly `bootstrap-1` / `neutral-bootstrap-1`; a zero violation
  count does not claim complete §6.3 coverage or Coordination Engine correctness.
- Dependencies were downloaded with approval, then bootstrap was run offline.
  Actual commands, failures and final checks are recorded in STATUS.

### Open limitations

- One smoke case, no reviewed golden suite or held-out cases. Changes A/B,
  realistic permissions/review fixtures, complete neutral validation, full naive
  comparator, SUT contracts/mapping, workspace environments, scorecard and judge
  UI remain future harness slices.
- No product/model/provider execution, native app test or customer outcome.
- No specification/control input, parent file or Git state is modified.

## Specification 0.5.0 / benchmark-2 — 2026-09-26 — acceptance continuation

### Added

- Active §13.1 milestones and a separately versioned benchmark contract workstream.

### Changed

- Current authorised stopping point is harness-ready acceptance instead of the
  earlier supervised smoke slice. Existing bootstrap artifacts retain their
  original versions. New runs will name their exact methods and input digests.

### Validation impact

- Existing baseline ran first: 21 tests, smoke and repository guards passed.
  New fixture/validator/baseline/mapping/scorecard behavior requires regression
  and manually calculated golden evidence before scale expansion.

### Open limitations

- §13.2 remains NOT_RUN; no product, model, live provider or native result is
  created by this continuation. Remaining harness work is tracked in PLAN.

### Checkpoint 1 — Added / Fixed / Validation impact

- Added benchmark-2 typed facts, deterministic tiny organisation, scoped grants,
  five provider environments, append-only observer, greedy-cascade-1 and neutral-2.
- Fixed a generated Security background block overlapping opaque protected time.
- Added mutation and provider-contract coverage; 36 tests pass. Connected naive
  A/B outputs were inspected and independently scored, with no product claims.
- Previous smoke behavior remains intact. Full scorecard/replay/judge/golden and
  medium/demo validation are still pending; no previous manifest is relabelled.

### Checkpoint 2 — Added / Changed / Fixed / Validation impact

- Added sut-1 discovery/reset/seed/drive/respond/observe/capture/export contracts,
  strict semantic mapping checks, versioned authored connected replay, and a
  deliberately unavailable real-product adapter.
- Added a retained-attempt runner, JSONL/text/CSV traces, 20 primary scorecard rows,
  28 additional metric definitions, raw provenance and product-headline exclusion.
- Fixed deadline diffs to use pre-event snapshots and clarified read-versus-local
  scope. Future synthetic acceptance is a projected duration field, not a
  fabricated chronological product event. Historical run artifacts are retained.
- 43 tests pass; inspected tiny A/B attempts are valid. No product, model or
  live-provider execution is implied. Judge UI, golden review and scale remain.

### Checkpoint 3 — Added / Changed / Validation impact / Open limitations

- Added eight reviewed development golden manifests, explicit manual arithmetic
  notes, an independent 16-candidate oracle and primary-scorecard expectations.
- Added local judge comparison, captured persona panels, step/pause/resume/reset,
  trace filtering/pagination and metric provenance, plus a self-contained offline
  artifact after the sandbox rejected loopback binding.
- 45 Python tests pass. Browser discovery returned no available browser, so
  browser visual/interaction checks remain NOT_RUN. No substitute browser result
  is claimed. Exact case counts are eight golden, zero expansion, zero held-out.

### Checkpoint 4 — Added / Changed / Fixed / Validation impact

- Added second-tenant colliding-ID probes, optional product-observation schemas,
  registry export/drift checks, HTTP handler/path tests, four UI logic tests and
  `PRODUCT_ADAPTER.md`. Export command now emits 44 benchmark/SUT/evidence schemas.
- Extended bootstrap to test the working judge logic offline; added a local
  repository-check entrypoint so the required command stays inside simulation.
- Fixed medium fourth-round working windows. Tiny goldens ran before scale;
  medium and demo initial states and naive A/B now have zero observed violations.
- Added source-consistent manager deadline confirmation and generic authority
  checks; authored `tiny-connected.v2.json` under new input hashes. Retained v1.
  Fixed the independent oracle's matching source deadline after it caught the
  new check. Added direct ready-Critical priority inversion validation.
- 53 Python tests and 4 JavaScript logic tests pass. Browser visual/interaction
  QA and loopback listening remain NOT_RUN, with exact prerequisites in STATUS.
  Rich narrative background distributions remain a realism limitation, not a
  claimed production benchmark; no product/live/provider/native evidence exists.

### Checkpoint 5 — Changed / Fixed / Validation impact / Remaining blocker

- Published local package metadata 0.2.0 with unchanged dependency pins; retained
  bootstrap-1 behavior, replay v1 and every earlier result. Current benchmark-2
  methods remain explicitly synthetic, using source-confirmed replay v2.
- Corrected demo managers to belong to their teams, generalized declared Critical
  actor authority checks, tightened baseline connection-scoped grant checks and
  retained failed manifests for unknown programmatic cases. Added regression;
  CLI case choices are finite. No product service or planner was added.
- Updated README, adapter guide, replay guide, PLAN, STATUS, DECISIONS and the
  complete 19-row/18-criterion requirements ledger to reflect actual capabilities.
- Final bootstrap: 54 Python + 4 JavaScript logic tests PASS, smoke and repository
  guards PASS. Acceptance evidence:
  `runs/acceptance-625200b750eb487286853a9d49ce1be0/acceptance.json`; connected
  method manifest `runs/benchmark-ffcae065d1e74e509f97f6bdd57be13d/manifest.json`.
  Final demo manifest: `runs/benchmark-96e7053ec2084e5c95b83991e4e4406f/manifest.json`.
  No earlier benchmark is recomputed or relabelled as these newer method bytes.
- **§13.1 BLOCKED** on connected-browser visual/interaction QA and a permitted
  loopback listener. Both were attempted and unavailable; acceptance exits 1
  deliberately while all available checks pass. **§13.2 NOT_RUN**. Eight reviewed
  development goldens, zero expansion/held-out or product/live-provider cases.
