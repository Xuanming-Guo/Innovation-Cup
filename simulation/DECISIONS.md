# Simulation decisions

Chronological record. D007 and later supersede the original bootstrap-only scope;
current implementation and execution status are in STATUS.

## D001 — 2026-09-26 — CONFIRMED: bootstrap boundary

The current user request limits this session to supervised preparation and one
smoke path. Specification 0.5.0 governs future slices; its entire acceptance
suite is not claimed complete by this bootstrap. Parent files and Git state are
read-only. Preserve the source prompt and DOCX byte-for-byte. Parent capability
ledger updates are represented in a simulation-local requirements/evidence map.

## D002 — 2026-09-26 — DEFAULT: minimal local stack

Use existing CPython 3.11.15 with a new `.venv` under simulation; uv 0.11.24
creates the local lock. Pydantic 2.13.5 matches the parent backend's pinned
contract dependency without importing backend code. Standard-library unittest,
argparse, hashlib and JSON/JSONL provide testing, CLI and persistence. No frontend,
web server, database, model SDK or solver is needed for the smoke path. Caches,
temporary files and outputs are local. A future judge UI can be added when its
slice is selected. No secrets or external service configuration are required.

## D003 — 2026-09-26 — DEFAULT: authored example replay first

Use the explicitly allowed replay route, with a checked-in versioned synthetic
example schedule and exact expected input digest. It is authored harness test
data, never a capture from a real product. Label every run
`REPLAY — NOT A PRODUCT RESULT`. A digest mismatch fails instead of adapting the
schedule. Do not implement an incomplete naive coordinator and present it as the
full Section 6.1 comparator. Real product status stays `NOT_RUN` with an explicit
missing-adapter reason; missing metrics have null values.

## D004 — 2026-09-26 — DEFAULT: narrow scoring and fixture claims

Use the exact tiny headcounts (25 employees, 4 teams, 75 tasks), coherent
three-task workflows and a fixed five-working-day horizon in Asia/Tokyo. The
no-impact event is a supporting smoke case, not Change A or Change B. Initial
fixture realism and neutral validation cover only the explicitly supported
contract subset. Unsupported review, access, approval, priority and lifecycle
semantics must remain unavailable until implemented. Score one explicitly scoped
metric; never call it full product validity or accepted work. Keep generator-owned
expected labels separate from replay input. One smoke case is not a hand-reviewed
golden suite or held-out benchmark.

## D005 — 2026-09-26 — EVIDENCE: dependencies prepared; offline continuation

Both initial sandboxed PyPI operations failed on DNS. Explicitly approved retries
locked the dependency graph and installed five packages under `.venv`, with all
package downloads cached under `.cache/uv`. `uv sync --locked --offline` then
succeeded. The bootstrap script disables interpreter downloads and exports local
environment/cache/temp locations. No outstanding dependency or network approval
is required for the selected stack on this host. Adding future dependencies may
require new network authority; no speculative frontend packages were installed.

## D006 — 2026-09-26 — DEFAULT: honest reproducibility and diagnostics

Store an immutable run directory per attempt, retain the exact replay input and
metric registry, and hash each artifact. Record both the existing Git HEAD and
a content digest of working-tree runtime code/manifest/lock/registry, since Git
mutations are forbidden. Deterministic fixture/outcome/validation/event hashes
exclude declared observational run IDs and timestamps. This is local integrity
evidence, not tamper-resistant storage. A missing/mismatched replay exits nonzero
and yields `NOT_MEASURED` with null. A structurally valid but bad schedule produces
measured violations and an `INVALID` run, never a repaired or approved plan.

## D007 — 2026-09-26 — CONFIRMED: harness acceptance continuation

The current user replaces D001's bootstrap-only stopping point with §13.1.
Continue offline as one orchestrator, no Git mutations or writes outside this
directory. §13.2 remains NOT_RUN. Existing bootstrap schema and fixture history
remain readable. New work uses benchmark-2 and separately versioned methods.

## D008 — 2026-09-26 — DEFAULT: explicit finite fixture time and no product emulator

Use 15-minute UTC-relative slots anchored to an aware timestamp, preserving the
company IANA timezone for date/budget calculations. Canonical scheduling facts
are fixture data. The naive comparator owns only its documented greedy/cascade
algorithm. Replay loads authored, input-hash-bound outputs; it cannot schedule,
repair, infer product transitions or populate product headlines. Deterministic
human responses are scripts against issued requests, not an approval service.

## D009 — 2026-09-26 — DEFAULT: naive failure and synthetic completion semantics

Greedy ready ordering is priority/deadline/release/task ID. Eligible-owner ties use
accepted/submitted/exposure project familiarity, then stable ID. Local choices
may evict authorised lower-priority work and queue successors. Cap 200 iterations.
No neutral validator is imported or called during repair. Failure to find a local
slot is UNKNOWN; only an individual release-plus-effort contradiction is a bounded
infeasibility proof. Synthetic acceptance uses fixed fixture durations and real
review reservations; it is a comparator clock, not a product lifecycle service.
Concurrent internal commitment remains unavailable to the naive comparator.

## D010 — 2026-09-26 — DEFAULT: local judge and evidence clocks

Keep the judge inspector in the existing dependency-free Python/HTML stack;
Sites building/hosting guidance was read, but this task explicitly forbids
external deployment, Git changes and writes outside simulation. No site account,
remote repository, package scaffold or social-card worker is created. Only
stored replay POVs feed persona panels. Synthetic duration-policy evaluation is
logged at the scenario observation clock; projected acceptance slots remain
separate fields, so future workload completion does not backdate Change B.

## D011 — 2026-09-26 — DEFAULT: honest scorecard denominators

Changes compare pre-event commitments to terminal evidence, including the
fixture-authorised deadline pull-in itself. Score original deadlines separately
from forecasts. Publish full canonical import size as read scope and the local
considered/replanned/moved/notified subsets separately. Replay with no observed
planning/communication metadata has NOT_MEASURED, not zero attempts or messages.

## D012 — 2026-09-26 — EVIDENCE: browser/listener unavailable

The sandbox denies loopback socket binding. Supported browser discovery returns
no browsers. Preserve these failed attempts and do not bypass either boundary.
Provide an offline self-contained replay artifact and test JavaScript logic plus
HTTP handler behavior without claiming browser rendering. Final §13.1 acceptance
must explicitly retain the browser QA prerequisite if it remains unavailable.

## D013 — 2026-09-26 — DEFAULT: source confirmation and preserved history

A deadline event supplies a fixture-authorised manager confirmation in a new
provider version as well as the requested date. It is source data, not a harness
approval workflow. Preserve Friday in the before snapshot and Wednesday in the
post-event confirmed record. Generic neutral project-source checks reject a
mismatched deadline. Connected replay v2 is newly authored against these inputs;
v1 and all prior run artifacts remain unchanged.

## D014 — 2026-09-26 — EVIDENCE: scale and validation limits

Medium and demo generation and naive A/B runs passed after repairing medium's
fourth-round working windows. These are deterministic sparse scheduling fixtures,
not a load-saturated real company or evidence of production capacity. The demo
matches organisation/project/task totals; richer thousands-of-source/calendar
and 400–700 cross-team-edge narrative targets are not claimed. Eight goldens are
manually reviewed by this orchestrator; external domain-human review and browser
QA are separate unavailable evidence. Do not enlarge the dataset merely to mask
those limitations.

## D015 — 2026-09-26 — EVIDENCE: final gate remains blocked

All available harness acceptance checks pass, including the 54-test Python suite,
four UI logic tests and eight reviewed goldens. Actual browser rendering/control
execution and an HTTP listener are unavailable on this host. Keep §13.1 BLOCKED
and §13.2 NOT_RUN; do not equate DOM doubles or handler tests with browser/server
execution. The acceptance producer names the original probes as recorded evidence.
A future continuation must execute and record the missing checks, not merely
change a status flag. PLAN identifies exactly what remains. This is an environment
prerequisite, not a request for user permission or missing product credentials.

The specification requires a working judge surface; treating actual rendering and
control execution as evidence for criteria 9 and 16 is this implementation's
verification judgment, not a claim that §13.1 literally names a separate browser
certification. The unavailable listener likewise limits verification of the live
reset/run flow, while the documented CLI and offline artifact work without it.

## D016 — 2026-09-26 — DEFAULT: relational graph, derived visualisation

The product specification's “knowledge graph” is a set of typed relational links
among people, tasks, skills, evidence, decisions and constraints. Keep those
records in the canonical relational model and derive graph nodes/edges for
inspection; do not add Neo4j, a second graph store or graph-owned authority. The
complete synthetic-company graph is a judge/developer inspector. A manager or
employee graph must be constructed only from that viewer's authorised projection.

## D017 — 2026-09-26 — DEFAULT: fair baseline plus separate broad-impact case

Do not make the mandatory naive comparator globally reschedule work merely to
make the product look better. A/B continue using the predeclared local greedy/
cascade policy and identical authorised inputs. Add `portfolio` as an explicitly
supporting demo: 12 existing packages receive a confirmed deadline and bounded
two-person response pools, producing 12 owner changes, four affected teams and 23
contacted people. Its scope is all 75 standalone tasks or all 80 tasks after B.
It is excluded from primary A/B headlines
and has no recorded/product result. A future global-replanning ablation, if added,
must be separately labelled and cannot replace the primary baseline.

## D018 — 2026-09-26 — EVIDENCE: archived browser pass is version-scoped

The repository user successfully served the replay at `127.0.0.1:8765`, reviewed
its desktop overview and stored manager/Security/Delivery POVs in Chrome, and
supplied eleven screenshots. Preserve that as real pre-inspector desktop and
loopback evidence. It does not establish a narrow viewport or the subsequently
added company/graph inspector. Browser discovery for the updated pass still
returns `[]`; §13.1 therefore remains BLOCKED on those two precise checks.
