# Future product adapter — contract, not a deployed integration

**§13.2: NOT_RUN.** The product currently exposes health/version only. A real
adapter must consume supported product interfaces; direct writes to undocumented
Supabase tables are forbidden. The harness has no product planner, interpreter,
approval engine, transaction/outbox/notification service or employee task app.

`coordination_sim/benchmark/sut.py` defines `SystemUnderTestPort` and a failing
`ProductUnavailable` implementation. `evidence.py` defines optional observed
product evidence records, not executable workflows. JSON Schemas are exported by
`python -B -m coordination_sim benchmark-schemas` in the local environment.

| Port operation | Required supported product behavior |
|---|---|
| `discover()` | Build/commit, product version, API/schema version, enabled capabilities, observable states; absent fields NOT_AVAILABLE |
| `reset(company_id)` | Reset only an explicitly authorised synthetic tenant; never arbitrary customer data |
| `seed(snapshot)` | Supported synthetic import API with immutable source/policy/permission/profile/estimate versions and receipt |
| `submit(event, manifest)` | Authenticated manager/incident event; idempotent request identity and exact fixture/environment references |
| `respond(response)` | Version-bound answers to product-issued clarification/disclosure/schedule approval/acknowledgement/submission/review requests |
| `observe(cursor)` | Native event IDs/provenance or clearly marked state polls; never fabricated solver or commit actions |
| `capture(viewer)` | Current-authority manager/employee projection, optionally screenshot/deep link; never rebuild from ground truth |
| `export()` | Concrete final task/segment state and exact versions; approvals/commit/actions/notifications/acceptance plus available stage metadata |

The local mapper is `exact-canonical-1`: it requires complete semantic equality.
A future mapper can translate slot offsets to UTC timestamps or renamed product
fields, then reverse-map the product import receipt into this canonical envelope.
Call `check_mapping(canonical, round_trip)` before scoring. Missing, broadened,
changed or extra facts invalidate the comparison. Preserve requested/agreed/
forecast dates, source versions, action grants, unknown availability, qualifications,
review gates, protected work, capacity budgets, priority origin, movement freedom
and disabled AI execution. Never infer that a field was imported from HTTP 200.

The baseline gets equivalent authorised canonical facts. Provider-specific
payloads stop at `workspaces.py`; all providers are **simulated**. The product
performs its own ingestion. Record exact source/import manifests for both sides.
Full canonical imports currently include the complete structured company; metrics
report that honestly, separately from local considered/replanned scope.

A then B is a connected experiment: B enters each method's actual A result state,
not a reseed. Initial inputs and exogenous B facts/freedoms must match; A-result
state differences must be preserved and reported, not normalised away to favour
either method. Mapping checks within each method prove faithful import; any
cross-method state difference needs an explicit, versioned comparison rationale.

Observe separately: interpretation, source freshness, solver classification,
product validation, disclosure/schedule approval, exact commitment, external sync,
notification/refetch, acknowledgement and accepted work. The trace chain is
`SourceVersionRef → CandidateTaskContract → ValidatedConstraint → PlanningSnapshot
→ CompiledModel` only when real product evidence supplies it. Missing solver
bounds/objectives/timing remain NOT_AVAILABLE.

Use `ProductEvidence` only for real observed records. Record compiler/solver/
validator versions and actual Gemini model/prompt/configuration/token/cost metadata
when exposed. No harness Gemini call is permitted. Do not put credentials in
fixtures, API payloads, logs, screenshots or frontend configuration.

`RecordedReplay` is an authored, hash-bound local recording. It supports contract
and presentation tests, requires exact issued actor responses, and returns its
stored output verbatim. It does not optimise or repair. A recording has no product
commit and cannot populate any product performance cell or percentage headline.
Only seed 17 / tiny / A → B has the connected authored recording; other seeds and
presets report replay unavailable rather than adapting recorded outputs.

A real adapter integration must add compatibility tests for reset isolation,
role/source revocation, stale versions, missing capabilities, malformed evidence,
controlled concurrency, exact approval/commit binding, ambiguous provider writes,
duplicate delivery, refetch and role projection. Provider fixture expectations
may be configured with observed committed digests to test exact external writes;
that expectation is not a harness-built commitment service. Native/live-provider
and real-model results require their own actual execution evidence.
