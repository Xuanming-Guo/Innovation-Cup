# Requirements to evidence — specification 0.5.0

Current benchmark: **0.3.0**, `benchmark-2`, `greedy-cascade-1`, `neutral-2`,
`sut-1`. **§13.1 BLOCKED** on current-inspector and narrow browser QA;
**§13.2 NOT_RUN**.
`IMPLEMENTED` means only the stated harness behavior. `SIMULATED` is synthetic
fixture/replay evidence. `NOT RUN` identifies missing execution prerequisites.
`FUTURE PRODUCT` is deliberately outside the harness. Earlier bootstrap results
remain unchanged; their narrower claims and command history are in STATUS.

## Every product component in §4.6

Paths below are relative to `coordination_sim/benchmark/` unless stated otherwise.

| Product component | State and current evidence | Remaining gate / claim boundary |
|---|---|---|
| Identity, company isolation and scoped roles | IMPLEMENTED: `contracts.py`, `generation.py`, `workspaces.py`; tenant-aware relations, scoped grants/actors, unrelated second tenant reusing IDs; `test_service_privacy.py` | FUTURE PRODUCT authentication/RLS/native tokens; selector is an inspector |
| Manager request and disclosure brief | SIMULATED: separate request, commitment and approved brief sources; `sut.py` exact-version deterministic actor responses | FUTURE PRODUCT brief generation/disclosure decisions; actor cannot grant broader authority |
| Connected-source ingestion | SIMULATED: five provider environments with version/freshness/grants, bounded reads, pagination, revocation and failures; `test_benchmark.py` | FUTURE PRODUCT ingestion/OAuth; no live API result |
| Model interpretation | NOT RUN: `evidence.py` typed lineage observation contracts and missing-metadata states | Needs supported real product gateway/evidence; no harness Gemini call |
| Deterministic admission | IMPLEMENTED: finite benchmark schema and neutral invalid/ambiguous evidence checks; mapping semantic equality in `sut.py` | FUTURE PRODUCT admission/constraint compilation; benchmark checks do not execute them |
| Planning and diagnosis | IMPLEMENTED: mandatory deterministic naive greedy/cascade comparator and bounded refusal/UNKNOWN distinction; SIMULATED authored SUT outcomes | FUTURE PRODUCT pinned insertion, Z3, repair, objectives, diagnosis; absent internals NOT_AVAILABLE |
| Independent scoring | IMPLEMENTED: `validation.py`, mutation tests and independent 16-candidate oracle | Outcome checks only; no repair/global optimality proof; shared incorrect ground truth remains possible |
| Proposal and explanation | SIMULATED: stored exact schedules and safe POVs; IMPLEMENTED neutral before/after metrics and evidence links | FUTURE PRODUCT proposal/explanation generation, alternative plans and actual viewer capture |
| Approval | IMPLEMENTED response binding and neutral exact digest/revision/authority checks; replay acknowledgement exercises the port | FUTURE PRODUCT approval policy; no inferred business approval from a feasible schedule |
| Internal commitment | FUTURE PRODUCT: typed observation in `evidence.py`; concurrent golden explicitly UNKNOWN/NOT_MEASURED | Supported product transaction/concurrency evidence required; no commit service |
| External synchronisation | SIMULATED: provider conditional versions, idempotency, timeout-after-write, reconcile and visible partial failures | FUTURE PRODUCT durable outbox/recovery; environment tests do not prove it |
| Notification and reconnect | FUTURE PRODUCT: separate `StageStates` and notification observation schema | Needs product refresh/drop/refetch evidence; no notification service or successful-reconnect claim |
| Human execution lifecycle | SIMULATED: deterministic duration policy projects accepted slots for naive benchmark; SUT actor response contracts | FUTURE PRODUCT actual submission/review/acceptance; projection never reported as real human acceptance |
| Learning and correction | FUTURE PRODUCT: maturity-tagged fixture familiarity and optional workload/estimate/correction schemas | No inferred skill updates, hidden employee scores or measured learning |
| Memory, provenance, retention and threat cases | IMPLEMENTED: create-once runs, hashes, JSONL causality, secret-shape/architecture guards, revoked-source, tenant, path and HTML-injection probes | Local files are not tamper-resistant storage; no legal/deletion/production certification or comprehensive injection study |
| Optional AI executor | NOT RUN: disabled in company schema | Product-only future capability; no harness executor or agent capacity substitution |
| Manager/employee/judge experience | IMPLEMENTED judge comparison/trace UI, complete fictional-company directory and derived relational graph; SIMULATED stored manager/Security/Delivery POVs with projection-local graphs; five JS logic tests; archived pre-inspector desktop Chrome evidence | New inspector and narrow browser layout NOT RUN. Complete inspector is judge/developer-only, not authentication; product/native application remains FUTURE PRODUCT |
| Production platform | FUTURE PRODUCT: `ProductUnavailable` and `PRODUCT_ADAPTER.md` describe supported-API boundary | No FastAPI/Supabase implementation, sign-in, deployment, migration, native installer or product result |
| Automated evaluation | IMPLEMENTED: reproducible A → B, naive baseline, neutral checks, 48 metric definitions including all 20 primary rows, failure-preserving aggregates; optional wide-impact portfolio demonstration | Eight reviewed development goldens; portfolio is supporting/not primary; no generated expansion/held-out or real-product comparison; human studies outside scope |

## §13.1 acceptance checklist

| Criterion (in specification order) | Evidence / status |
|---|---|
| 1. Writes remain local; source DOCX unchanged; boundary recorded | PASS: `scripts/check_repository.py`, boundary tests; immutable prompt/DOCX hashes and unchanged Git HEAD/branch/index |
| 2. Local credential-free execution | PASS: CLI/offline artifact and repository-user loopback execution at `127.0.0.1:8765`; restricted automation may still deny bind |
| 3. Material approach evolution and new manifests | PASS: append-only CHANGELOG checkpoints, manifest method/code/input hashes, retained bootstrap and replay v1/v2 |
| 4. Deterministic reset/run A → B naive and labelled replay | PASS: `test_sut_metrics.py`; reset reproduces semantic hashes with runtime exclusions |
| 5. 5–10 reviewed goldens before expansion | Eight cases with explicit manual arithmetic/trace review by implementing orchestrator (`evals/golden-review.md`), tested in `test_golden.py`; no independent domain-human sign-off claimed; 0 expansion, 0 held-out |
| 6. Coherent separately permissioned cross-workspace evidence | PASS: source versions/authority, provider import trace and per-method canonical input manifests; five simulated workspaces |
| 7. Simulated connector labels and no live API claim | PASS: UI, manifests, traces, capabilities and tests |
| 8. Structurally coherent, non-sensitive scheduling profiles | PASS: tiny/medium/demo schema and initial validation, function/headcount totals, actual team managers, prohibited-field test; sparse workload realism limitation disclosed |
| 9. Judge comparison/trace and labelled safe POVs | IMPLEMENTED, logic tests PASS; archived desktop overview/POV Chrome evidence PASS. Fresh company/graph inspector browser pass and narrow viewport BLOCKED. No employee task app |
| 10. Every §4.6 component mapped honestly | PASS: all 19 rows above |
| 11. Step-level summary and append-only provenance | PASS: `trace.py`, trace/hash/causality tests, JSONL/text/CSV exports |
| 12. SUT/mapping/replay pass; replay excluded from product headline | PASS: exact input/output bindings, required actor response tests, mapping mutations and headline exclusion |
| 13. Reproducible mandatory naive baseline | PASS: `naive.py`, eligibility/familiarity/capacity assignment, dependency cascade, bounded iterations and reporting relays; no hand-tuned success replacement |
| 14. Neutral checks and every primary computation pass goldens | PASS: 20 primary rows, all eight reviewed case expectations, explicit A/B arithmetic, 16-candidate independent oracle and negative mutations |
| 15. Missing product/conditional evidence stays unavailable | PASS: real product cells NOT_RUN; model/provider/cost and unobserved internals null NOT_MEASURED/NOT_AVAILABLE; zero denominator remains null |
| 16. Scale is visible without rendering all entities | IMPLEMENTED: totals, paginated full fictional directory/task index, impact-filtered derived graph, affected-only POV cards and 100-event trace pagination; new inspector browser rendering BLOCKED |
| 17. No second product implementation | PASS: architecture/import tests and source inspection; no solver, product workflow, learning, ingestion or task-management UI |
| 18. Honest tests/actual commands | PASS: STATUS and generated acceptance report retain successful, failed and unavailable checks separately |

The available automated checks and archived pre-inspector browser evidence do
**not** close §13.1. Browser discovery for the updated UI returned `[]`; no fresh
inspector or narrow-layout screenshot exists. The exact resume procedure is in
STATUS and PLAN. Acceptance keeps those checks open until observed evidence is
retained.

## Measurement and validation limits

- Current counts: **8 development goldens**, **1 authored supporting wide-impact
  demonstration**, **0 generated expansion cases**, **0 held-out cases**, **0
  real product runs**, **0 live-provider runs**.
- Full canonical snapshot import is reported as full read scope. Local considered,
  replanned, moved and notified subsets have separate denominators. No model sees
  the data. Only reduced calendar fixture content is present in canonical inputs.
- Runtime milliseconds are actual observations; simulated durations and replay
  playback speed are separate. Source confirmation, schedule validity, approval,
  commitment, sync, acknowledgement and acceptance are independent fields.
- The demo has 3,000 employees, 117 teams, 150 projects and 8,000 tasks. It is sparse;
  thousands-of-source/calendar and 400–700 cross-team-edge narrative targets are
  not claimed, and no production throughput or general feasibility is established.
- Real adapter prerequisites are in PRODUCT_ADAPTER. §13.2 is NOT_RUN throughout,
  including when the authored replay has zero neutral violations.
