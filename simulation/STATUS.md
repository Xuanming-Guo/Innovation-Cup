# Simulation 0.5.0 status

Current harness: **0.3.0**, contract `benchmark-2`. **§13.1: BLOCKED** on fresh
browser interaction for the company/graph inspector and a narrow viewport.
Archived pre-inspector desktop Chrome and loopback evidence now PASS.
**§13.2: NOT_RUN**. No real product adapter, model, live-provider, native artifact
or customer result exists.
All implementation writes remain under simulation; no Git mutation was performed.

The available automated acceptance checks pass: **58 Python tests**, **5 JavaScript
logic tests**, eight manually reviewed development goldens, 16 tiny oracle
candidates, connected naive/replay A → B and both repository guards. Medium and
demo initial schedules validate; demo naive A → B completes with zero violations.
The updated inspector logic tests use a DOM double, not a browser. Goldens were reviewed through
explicit arithmetic/trace inspection by this orchestrator, not an external human.

Current evidence:

- [Acceptance report](runs/acceptance-56e3dd9f94bf4a249e7ba052502ff200/acceptance.json):
  nine checks PASS; current-inspector and narrow browser checks NOT_RUN; command
  exit 1 deliberately reflects the open blocker.
- [Combined A/B/portfolio replay](runs/benchmark-43329a535133469887a6e9517b1d8977/judge.html)
  and its [manifest](runs/benchmark-43329a535133469887a6e9517b1d8977/manifest.json).
- [Final bootstrap output](runs/final-bootstrap-0.2.0.txt).
- [Requirements evidence](REQUIREMENTS_TO_EVIDENCE.md) covers all 19 product rows
  and 18 acceptance criteria; [PLAN](PLAN.md) gives the exact continuation.

The repository user successfully served the replay at `127.0.0.1:8765` and
archived desktop overview plus manager/Security/Delivery POV screenshots under
`evals/browser-qa/`. During the current update an approved loopback listener also
started at port 8766, but supported browser discovery still returned `[]` after
the documented troubleshooting check. The newly added inspector and narrow
layout therefore remain untested in a real browser.

## Historical bootstrap record (0.1.0)

The following original bootstrap sections describe the earlier, narrower state.
They are retained for provenance, not current missing-feature claims. The current
continuation and final results appear after them.

## Starting repository state

Recorded 2026-09-26T07:04:13Z (2026-09-26 UTC; local calendar date was September 25).
Working directory: `/Users/sophiaji/Documents/Coding/Innovation-Cup/simulation`.
Repository root: `/Users/sophiaji/Documents/Coding/Innovation-Cup`.
Branch: `feat/13-simulation`. HEAD: `d0bf6fe30b48aab20047f4b254b97f4d6195a5bb`.

`git status --short --untracked-files=all` produced **empty output** (exit 0).
`git diff --stat` produced empty output. No pre-existing local changes were found.
No Git mutation is authorised or performed.

Initial simulation files: `.gitkeep`, `CHANGELOG.md`,
`simulation_implementation_prompt.md`, `coordination_engine_simulation_context_v2.docx`.

Immutable SHA-256 inputs:

- Prompt: `efd849f8e7064a2da3f91c43de17ad6ece6e999a57617f1ee246dc562fe7a8e8`.
- DOCX: `7fb753efa9a798855d3e5c56fa85e2e468cadff7139b47b8609be2e82dc72eae`.

Read `../AGENTS.md`, the entire simulation prompt and DOCX (via read-only
`textutil -convert txt -stdout`), `../docs/implementation_master_prompt_v2.md`
including Part B, `../docs/CHANGELOG_v2.md`, local CHANGELOG and the product
implementation ledger. The parent check confirmed embedded/standalone spec parity.
Existing backend consists of health/version/configuration and a worker foundation;
there is no scheduling product interface to exercise.

## Commands and actual results

- `pwd`, `git status --short --branch`, `git rev-parse --show-toplevel`,
  `git rev-parse HEAD`, `git diff --stat`: exit 0; state above.
- `git --no-optional-locks status --short --untracked-files=all`: exit 0, empty.
- `python3 --version`: 3.11.15; current shell points into an unrelated existing
  environment. Do not install there; create simulation-local `.venv`.
- `uv --version`: 0.11.24, Apple Silicon build.
- `uname -sm`; `sw_vers -productVersion`: Darwin arm64; macOS 15.7.3.
- `python3 -B ../scripts/check_repository.py`: exit 0,
  `Repository contract checks passed.` (pre-edit baseline).
- Read-only `rg`, `sed`, `cat`, `wc`, `ls`, `textutil`, `shasum` and uv help
  inspected source material, repository contracts, installed tools and locks.

## Dependency setup — approvals resolved

All commands below ran from `simulation/`. The dependency-command prefix was:

```sh
UV_CACHE_DIR=.cache/uv UV_PROJECT_ENVIRONMENT=.venv UV_PYTHON_DOWNLOADS=never TMPDIR="$PWD/.tmp"
```

| Command | Actual outcome |
|---|---|
| `mkdir -p .tmp` | Exit 0; simulation-local temporary directory |
| Prefix + `uv lock --project .` (sandboxed) | Exit 2 after 3 retries; PyPI DNS lookup failed |
| Same lock command, explicit network approval | Exit 0; resolved 6 packages, including virtual project |
| Prefix + `uv sync --project . --locked` (sandboxed) | Exit 1 after 3 retries; files.pythonhosted.org DNS lookup failed; local `.venv` created |
| Same sync command, explicit network approval | Exit 0; prepared/installed 5 packages |
| `sh scripts/bootstrap.sh` (offline, final code) | Exit 0; resolved 6/checked 5 packages, 21 tests pass, smoke and both repository guards pass |

Installed: Pydantic 2.13.5, pydantic-core 2.46.5, annotated-types 0.8.0,
typing-extensions 4.16.0, typing-inspection 0.4.4. Transitive versions and
distribution hashes are in `uv.lock`. `sys.prefix` was checked and is exactly
`/Users/sophiaji/Documents/Coding/Innovation-Cup/simulation/.venv`.
CPython 3.11.15's existing base installation is read-only. No global install.
No unresolved approvals or credentials are needed for this stack on this host.

## Implementation and verification commands

| Command/check | Actual outcome |
|---|---|
| `PYTHONPATH=. .venv/bin/python -B scripts/generate_replay_example.py` | Exit 0; generated one authored synthetic reference under `fixtures/replays/`; not product capture |
| First `.venv/bin/python -B -m unittest discover -s tests -v` | Exit 1 after first 5 fixture tests passed: `TypeError: 'PosixPath' object is not callable`; test class `run` shadowed unittest method |
| Same test command after renaming to `run_path` | Exit 0; 19 tests passed |
| First complete `sh scripts/bootstrap.sh` | Exit 0; 21 tests passed in 1.964s; Git's macOS tool lookup emitted nonfatal Xcode file-event/cache warnings; checks still passed |
| Final `sh scripts/bootstrap.sh` | Exit 0; **21 tests passed in 0.191s**, offline sync, successful replay smoke, boundary and parent checks passed; no warnings |
| `.venv/bin/python -B -m coordination_sim schemas` | Exit 0; six JSON Schemas exported to `runs/schemas-7272bfee041c4e72a3bd816c1f0c8f90/` |
| `.venv/bin/python -B -m coordination_sim smoke --seed 18` | Expected exit 1: `FAILED`, null `NOT_MEASURED` observation; input has no matching replay; evidence retained in `runs/smoke-bf64fb65275949efbf552862b2e660b9/` |
| `git --no-optional-locks diff --check` | Exit 0; no tracked whitespace errors |
| `git --no-optional-locks diff -- CHANGELOG.md` | Reviewed append-only compatible implementation entry; old entries unchanged |
| `shasum -a 256 simulation_implementation_prompt.md coordination_engine_simulation_context_v2.docx` | Both equal starting hashes above |
| Targeted `rg -l` scan over new code/tests/fixtures/docs/lock for Google/OpenAI key shapes and private-key headers | No matches (rg exit 1 means no matches); not a universal secret audit |
| `json.tool`, `cat` inspection of manifests, metric, validation and timeline | Actual counts/provenance/unsupported checks inspected; product remains `NOT_RUN` |

The regression suite covers input references/cycles/tenant mismatch, missing or
negative effort, naive timestamps, unknown schema fields, complete initial
schedule, forbidden product imports, hash-bound verbatim replay, separate gold
labels, changed seeds, trace causality, artifact hashes, output overwrite/escape,
missing evidence, nonzero mutation scores, half-open interval adjacency and
parent-change detection without mutating the parent. Dropping the first block
produces exactly **4** independent violation records (completeness, effort,
protection and successor dependency), and an `INVALID` run is retained.

## Last successful smoke evidence

Run: `runs/smoke-6cbaf73c02914b6596f5d243ed1c1e92/`.
Command output:

```text
REPLAY — NOT A PRODUCT RESULT
COMPLETED: bootstrap_schedule_violation_count=0 (MEASURED)
Coordination Engine: NOT_RUN
```

Fixture: **25 employees, 4 teams, 25 projects, 75 tasks, 50 dependency edges**,
75 effort blocks, five working days. One no-impact event; seed 17. Authored replay
provenance: `authored_synthetic_example_not_product_capture`. Every run uses
specification 0.5.0, contract `bootstrap-1`, validator `neutral-bootstrap-1`, and
separate harness/code/lock/input/artifact hashes. The five JSONL observations and
readable timeline describe harness actions, not invented product internals.

The measured **0 violation records** applies only to the listed bootstrap checks.
It does not measure complete hard-constraint validity, product performance,
accepted work or real-world productivity. The complete primary scorecard is
pending. Unchecked categories are listed in each validation report.

## Final repository boundary

`git -C .. --no-optional-locks status --short --untracked-files=all` returned only:

```text
 M simulation/CHANGELOG.md
?? simulation/.env.example
?? simulation/.gitignore
?? simulation/.python-version
?? simulation/DECISIONS.md
?? simulation/PLAN.md
?? simulation/README.md
?? simulation/REQUIREMENTS_TO_EVIDENCE.md
?? simulation/STATUS.md
?? simulation/coordination_sim/__init__.py
?? simulation/coordination_sim/__main__.py
?? simulation/coordination_sim/contracts.py
?? simulation/coordination_sim/generation.py
?? simulation/coordination_sim/replay.py
?? simulation/coordination_sim/runner.py
?? simulation/coordination_sim/scoring.py
?? simulation/coordination_sim/serialization.py
?? simulation/fixtures/replays/README.md
?? simulation/fixtures/replays/tiny-no-impact.v1.json
?? simulation/metrics/registry.v1.json
?? simulation/pyproject.toml
?? simulation/scripts/bootstrap.sh
?? simulation/scripts/check_boundary.py
?? simulation/scripts/generate_replay_example.py
?? simulation/tests/test_smoke.py
?? simulation/uv.lock
```

The boundary script passes: every changed path is under simulation, HEAD/branch
match the starting baseline, the index remains clean, source inputs have the
original SHA-256 values, and runtime paths resolve locally. Generated `.venv`,
`.cache`, `.tmp` and `runs` are ignored locally. No parent file or Git state was
intentionally modified; no branch, commit, stage, PR, deployment or external
message was created. The parent repository check also passes. New untracked
source files were reviewed directly; tracked `git diff` alone cannot review them.

## Historical bootstrap limitations and NOT RUN prerequisites

- **Full harness acceptance: incomplete.** One authored smoke case, zero reviewed
  golden-suite cases, zero held-out cases. Changes A/B and medium/demo generation
  require later fixture/scenario slices. The current profiles are deliberately simple.
- **Neutral scoring: partial.** Source permissions/authority, reviewers/acceptance,
  daily/weekly budgets, priority/displacement, approvals, split/passive work,
  commitment and synchronisation are not checked. Requires expanded typed
  ground truth, independent scoring and mutation/oracle tests.
- **Naive comparator / complete SUT port / product mapping / workspace environments /
  judge UI / full metrics: not implemented.** Requires the next PLAN slices.
- **Product conformance/comparison: NOT RUN.** Requires a real product build with
  supported synthetic seed/reset, drive/respond, observe/projection and terminal
  evidence-export interfaces plus verified input mapping. Product metadata is
  `NOT_AVAILABLE`; no harness stand-in is allowed to satisfy this prerequisite.
- **Model/provider/cost evidence: NOT RUN / NOT_MEASURED.** Requires authorised
  product execution and actual attributable evidence. No credentials are needed
  or requested for the offline bootstrap.
- **Native Windows/macOS application tests: NOT RUN.** Requires actual product
  artifacts and relevant hardware; Python tests on this Mac prove no desktop support.
- **Human productivity/customer outcomes: NOT RUN.** Outside this harness scope.
- No dedicated lint/type-check tool is installed or claimed. Behavioral checks
  use unittest and runtime Pydantic validation. Local hashes are not tamper-proof.

## Historical bootstrap next action (superseded by PLAN)

Read PLAN, STATUS and DECISIONS, then run `sh scripts/bootstrap.sh` from simulation.
Continue with **benchmark contract/ground-truth slice 1**: extend the tiny fixture
with one unrelated second tenant, explicit task/source grants, and one private
shared-specialist reservation projected only as opaque capacity. Add independent
scoring/mutation checks for tenant/grant integrity and a test proving private
titles and expected labels are absent from method inputs. Use no product code.

Acceptance for that next slice: deterministic input/projection hashes, unchanged
tiny totals, one capacity budget per shared employee, denied cross-tenant and
revoked-source references, retained failed runs, passing existing smoke tests and
boundary guard. Version changed contracts/fixtures; preserve this replay/run
history and append the change to CHANGELOG. Do not implement the product's
permission service. Then proceed through PLAN's full naive-baseline and SUT
contract slices. There is no need to expand to 8,000 tasks before those work.

## Continuation — 2026-09-26

The current user authorises completing §13.1, superseding the earlier bootstrap-
only scope. First command `sh scripts/bootstrap.sh`: exit 0, 21 tests passed in
0.228s; smoke `runs/smoke-a6acb7ceff2a4d1290901779d53bcd40`, boundary and repository
checks passed. Startup read-only Git status matches the earlier uncommitted
simulation additions and CHANGELOG edit; no parent changes. Sources read in full;
embedded/standalone product spec comparison returned True. No product API beyond
health/version is available. Current work: new versioned benchmark contract and
neutral validation, preserving bootstrap fixtures and old run formats.

### Checkpoint 1 — executable tiny environment / naive / neutral validator

`python -B -m unittest discover -s tests -v` via `.venv`: **36 passed**, 0.356s.
A direct tiny inspection found initial fixture overlap at Security's private
Tuesday 14–16 reservation; moved the background fixture block to 16:00 before
running benchmarks. Initial neutral report now has zero violations. Inspected A:
Hikari slots `(0,4),(8,12),(16,20),(20,24),(24,28)`; B retains first two, moves
last three by two slots, incident ends slot 20. A has 5 local iterations, B 8,
including 3 discovered conflicts. Both neutral reports have zero violations.
These are synthetic naive outcomes, not product results. Source/grant, effort,
review/acceptance, budget, deadline, protection, exact approval and disclosure
mutations pass. Five provider fixtures cover denial, stale/unknown, pagination,
duplicates, uncertain writes, idempotency and partial failure. Next: SUT mapping,
recorded replay, golden arithmetic/oracles and scorecard; no scale expansion yet.

### Checkpoint 2 — contract replay, primary scorecard and evidence runner

43 tests passed in 1.181s. Tiny connected run
`runs/benchmark-4f8d7489932b4c06a7c3b59bafb0e280` inspected: A/B naive and replay
all completed with zero neutral violations. Input mapping, exact response
binding, reset, captured POVs, replay refusal, per-artifact hashes and deterministic
trace tests pass. All 20 primary metrics exist in a 48-metric registry. Product
cells remain NOT_RUN; conditional metrics are null with reasons. Manual inspection
found deadline-diff scoring used post-event facts as its comparison baseline;
fixed it to compare against the separate pre-event snapshot, preserving Change A's
five pulled-in deadlines in the breakdown. New runs will contain that correction.
Full fixture input reads are now reported separately from the smaller considered/
replanned scope; no claim that an entire canonical import was never read.

### Checkpoint 3 — eight golden cases, oracle and judge replay

45 Python tests pass in 1.587s. `evals/golden.v1.json` has exactly eight development
cases; `golden-review.md` records the orchestrator's manual arithmetic and trace
review. No external human/customer review is claimed. Zero generated expansion
and held-out cases. The independent four-slot oracle agrees with the neutral
validator on all 16 candidates (three feasible). Every primary row has golden
checks; stage runtimes have nonnegative evidence checks, not fabricated constants.

Judge HTML/CSS/JS and the loopback service are implemented. Serving with
`.venv/bin/python -B -m coordination_sim serve --port 8765` failed at socket bind:
`PermissionError: [Errno 1] Operation not permitted`. No escalation attempted.
Added self-contained `judge.html` to each new run. Example offline artifact:
`runs/benchmark-6254cc12010749ceb739da84f5249f02/judge.html`.

Browser skill setup completed; `getForUrl(file://.../judge.html)` returned
`No browser is available`. Read bootstrap-troubleshooting and queried browser
list once: `[]`. **Browser visual/interaction QA: NOT_RUN**; prerequisite is a
connected supported browser (and permitted loopback listener for service tests).
Do not claim this gate passed from unit/static checks. Continue all independent
work: UI logic/handler tests, privacy audits, scale and final evidence ledger.

### Checkpoint 4 — scale, privacy, UI logic and final repairs

- `node --check ui/app.js`: exit 0. `node tests/ui.test.cjs <judge-data.json>`:
  **4 passed**, covering metric rows/provenance, step/pause/resume/reset, connected
  B selection, filtering and hiding judge-only material in employee panels.
  This uses a minimal DOM double and is explicitly not browser rendering QA.
- 53 Python tests passed in 1.827s after final source-lineage repair. Includes
  repository/architecture guards, registry drift, medium regression, path traversal,
  second-tenant ID collision, offline HTML injection safety and private POV probes.
- First medium generation had 3 working-window violations in its fourth background
  round. Corrected the constructive day placement; subsequent medium has 100
  employees / 10 teams / 30 projects / 350 tasks and zero initial violations.
- Demo generation: 3,000 / 117 / 150 / 8,000; zero initial violations.
- Medium A/B benchmark `runs/benchmark-7abb38afbee2445e91c01e581e1252d1`:
  both naive attempts COMPLETED, zero violations. Demo equivalent
  `runs/benchmark-0249603c0594496ea014d1694284e01d`: same result. Replay unavailable
  for these presets is visible; no generated replacement product output.
- `benchmark-schemas`: 44 schemas exported to
  `runs/benchmark-schemas-272533af42cf46d6baa9e246c3515313`.
- Deadline-source review found the updated Hikari task dates needed an explicit
  versioned manager-confirmation record. Added it and generic project-source
  consistency checks. Authored replay **v2** reflects those new source bytes;
  v1 remains untouched. The oracle initially failed because its custom deadline
  did not update its own authoritative source; repaired the oracle fixture too.
- `git diff --check`, boundary guard and parent repository check pass. No Git or
  parent/source-control-input mutations. Final comprehensive check remains below.

### Checkpoint 5 — final acceptance audit and documented blocker

- `sh scripts/bootstrap.sh` after final code changes: exit 0, **54 Python tests**,
  **4 UI logic tests**, preserved bootstrap smoke and both repository guards PASS.
  Complete output is `runs/final-bootstrap-0.2.0.txt`.
- `.venv/bin/python -B -m coordination_sim acceptance`: expected exit **1**,
  §13.1 **BLOCKED**, §13.2 **NOT_RUN**. Report and raw test/guard logs are in
  `runs/acceptance-625200b750eb487286853a9d49ce1be0/`. Seven available checks PASS;
  browser QA and listener execution are NOT_RUN with recorded prerequisites.
- Its connected run `runs/benchmark-ffcae065d1e74e509f97f6bdd57be13d/` has four
  completed A/B naive/replay attempts, each with zero neutral violations. These
  remain synthetic outcomes; every real-product scorecard cell stays NOT_RUN.
- `.venv/bin/python -B -m coordination_sim benchmark --preset demo`: exit 0,
  `runs/benchmark-96e7053ec2084e5c95b83991e4e4406f/`, naive A and B completed with
  zero neutral violations. Replay is visibly unavailable for this preset.
- Final inspection repaired demo manager membership, made priority authority
  validation use the declared actor action/scope rather than an actor-name
  shortcut, tightened naive connection-scoped grants, and retained an explicit
  FAILED manifest for unknown programmatic scenario IDs. CLI rejects unknown
  cases before running. Regression count rose from 53 to 54.
- Package metadata/lock now identify 0.2.0. Offline `uv lock --project . --offline`
  changed only local project version; no dependency version changed. The preserved
  legacy smoke command still declares its narrower bootstrap-1/0.1.0 method.
- The acceptance command references prior browser/listener probes explicitly; it
  does not pretend to have repeated them or infer a pass on another host. Actual
  browser evidence must be added to its checks after the prerequisite changes.
- `python -B scripts/check_repository.py`, tracked diff whitespace review and a
  scoped credential-pattern scan are recorded below. New untracked code was
  inspected directly and exercised by tests; tracked diff alone is insufficient.

No remaining approval request exists. Work stops at the genuine unavailable
execution gate after completing safe independent work. Resume from PLAN's final
browser/service checklist. Sparse workload/source density remains an explicit
fixture realism limitation; zero expansion/held-out, real-product and live-provider
cases remain. There is no basis for a product performance or productivity claim.

### Final boundary and artifact inspection

`python -B scripts/check_repository.py` exited 0 after documentation updates:
all changes are under simulation, HEAD/branch/index and source hashes are unchanged,
and the parent repository contract check passed. `git --no-optional-locks diff
--check` exited 0. The scoped `rg -l` credential-shape scan returned no paths
(exit 1 means no matches); it is not a universal secret audit.

An independent SHA-256 inspection rechecked all **60** artifacts listed in the
current connected manifest: PASS. Four A/B naive/replay outcomes are COMPLETED
with zero violations; medium/demo reports each contain zero initial violations.
The first ad-hoc inspection used the wrong manifest key `artifact_hashes` and
raised KeyError; rerunning against the actual `artifact_sha256` field passed.
No artifact was altered by that inspection. Final bootstrap Python duration was
1.961s; acceptance-run Python duration was 1.906s. Runtime measurements describe
this host, not product planning performance.

## Checkpoint 4 — synthetic company, relational graph and broad-impact demo

Implemented benchmark harness 0.3.0 without changing the `benchmark-2` scheduling
contract or the primary A/B comparator. `company-inspector.json` now indexes all
fictional employees, teams, projects and tasks for judge/developer browsing. The
UI provides profile/task search, team/role filtering and pagination. It clearly
states that the complete-company view is neither a user POV nor authorisation.

Each concrete method outcome also exports `coordination-graph.json`, derived from
the canonical relational task, dependency, source, assignment, project, employee
and team records. The UI renders impacted or all-considered nodes, typed edges and
an accessible record list. Stored persona views receive a smaller graph built
only from their already-permitted replay projection. No graph database, graph-
owned state or product behaviour was added.

Added optional case `portfolio`: an authorised multi-team launch pulls forward
12 existing work packages and permits an explicit two-person response pool for
each. On the tiny fixture, the naive comparator completes with zero neutral
violations, 12 owner changes, four affected teams, 23 contacted people and all 75
standalone tasks in considered scope (all 80 after B in the combined run). This
is an authored supporting demo, not a ninth golden, product replay, product
result or primary scorecard case. The primary A/B
baseline remains the same local greedy/cascade policy.

Browser evidence is now version-scoped. The repository user's eleven screenshots
establish pre-inspector desktop/POV rendering and loopback execution. Their
manifest records that narrow layout and the new inspector are NOT_RUN. An updated
local server started successfully on `127.0.0.1:8766`; browser discovery still
returned `[]`, so no visual claim was inferred from data/DOM tests.

Actual verification completed for this checkpoint before the final acceptance
rerun:

- `.venv/bin/python -B -m unittest discover -s tests -v`: **58 tests PASS**.
- `node --check ui/app.js`: PASS.
- `node tests/ui.test.cjs <combined judge-data.json>`: **5 tests PASS**.
- `.venv/bin/python -B -m coordination_sim smoke`: PASS; product NOT_RUN.
- Combined `run(cases=('A','B','portfolio'))`: five successful attempts (A/B
  naive + replay, portfolio naive), zero neutral violations; product NOT_RUN.
- Direct demo-preset inspector export: 3,000 employees, 117 teams, 150 projects
  and 8,000 task index rows produced successfully.
- `.venv/bin/python -B -m coordination_sim acceptance`: nine checks PASS; only
  current-inspector browser and narrow-layout checks NOT_RUN; §13.1 BLOCKED and
  §13.2 NOT_RUN in `runs/acceptance-56e3dd9f94bf4a249e7ba052502ff200/`.
