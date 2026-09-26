# Simulation approach changelog

This file records material changes to the proposed simulation method. It is separate from:

- `STATUS.md`, which records what currently works and the actual commands/checks run;
- `DECISIONS.md`, which records why current design choices were made; and
- runtime JSONL traces, which record simulated actor actions.

The entries below describe changes to the implementation specification only. They are not claims that the simulation, integrations, benchmark results or product backend have been implemented or validated.

## Unreleased

No unreleased approach changes are currently recorded.

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
