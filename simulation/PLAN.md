# Simulation 0.5.0 implementation plan

Scope: complete §13.1 harness acceptance as one orchestrator. All writes remain
inside simulation; Git, parent files, source prompt and DOCX remain read-only.
§13.2 product-connected results remain NOT_RUN. Preserve bootstrap-1 history.

## Current ordered milestones

1. [x] Run existing bootstrap before edits: 21 tests, replay and both guards pass.
2. [x] Read required handoff records and immutable source context; inspect code.
3. [x] Versioned benchmark contracts, coherent tiny fixture, separate gold,
   explicit grants/opaque capacity, independent validator and tiny oracle.
4. [x] Five simulated workspaces, scoped reads/writes/failures and actor trace.
5. [x] Full deterministic naive greedy/cascade comparator and reporting relays.
6. [x] SUT discovery/reset/seed/submit/respond/observe/project/export contract,
   exact mapping checks, authored replay and explicit unavailable real adapter.
7. [x] Connected A → B, complete primary scorecard and other automated metrics,
   evidence exports and local judge replay with safe captured POVs. Rendering QA
   remains a separate blocking check below.
8. [x] Eight manually inspected golden cases with arithmetic review notes, failure
   cases and mutation/oracle tests; run tiny before medium/demo generation.
9. [x] Medium/demo scale, privacy/fairness/architecture audits, full bootstrap,
   repository checks, final acceptance report and current documentation.
10. [x] Repository-user desktop Chrome review of the overview and manager,
    Security and Delivery POVs; loopback service executed at `127.0.0.1:8765`.
    Evidence is archived under `evals/browser-qa/`.
11. [x] Searchable complete synthetic-company inspector, derived relational
    coordination graph, projection-local persona graphs and optional wide-impact
    `portfolio` demo case. Primary A/B baseline remains unchanged.
12. [ ] **BLOCKED:** fresh desktop browser interaction for the new inspector and
    one narrow-viewport pass. Browser discovery still returns `[]`; automated
    syntax/data/DOM-double checks do not establish rendered layout.

For each milestone: implement → test → inspect artifacts → repair → document.
No product planner, interpretation, approval/commit/outbox, notification,
learning, ingestion or manager/employee application is built here. Missing
product capabilities are evidence, not permission to emulate the product.

## Exact continuation after the environment prerequisite is available

Run `sh scripts/bootstrap.sh`, then create the combined demo with
`.venv/bin/python -B -m coordination_sim benchmark --cases A B portfolio` and
serve the printed run using `.venv/bin/python -B -m coordination_sim serve --run
runs/<printed-id> --port 8765`. In a browser, use the scenario selector for
`portfolio`; inspect the complete directory, impacted/all-considered graph,
selected-node details and the projection-local manager graph. Confirm 12 owner
changes, 23 contacts, four teams and 80 considered tasks in the combined post-B
state. Repeat the key path at
a narrow viewport and archive screenshots under `evals/browser-qa/`. Update the
manifest and acceptance producer only from observed evidence before declaring
§13.1 PASS.

§13.2 remains NOT_RUN. Generated expansion and held-out cases are separate work;
no product-connected comparison is enabled by browser acceptance.
