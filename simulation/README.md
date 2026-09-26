# Coordination Engine simulation harness

Specification **0.5.0**; current benchmark harness **0.3.0** (`benchmark-2`).
The original `bootstrap-1` smoke path remains compatible. **Section 13.2: NOT_RUN.**
This package evaluates synthetic work; it contains no Coordination Engine backend.

The offline core runs: coherent fixtures → five simulated workspaces → mandatory
naive greedy/cascade comparator or authored replay → independent neutral checks →
20-row primary scorecard, provenance and judge replay. Eight development golden
cases have explicit arithmetic/trace review notes. No real product, model, live
provider, native app or measured human productivity result is claimed.

**Section 13.1 remains blocked on a fresh browser pass for the new company/graph
inspector and a narrow viewport.** The repository user supplied desktop Chrome
screenshots that establish the earlier replay/POV views and loopback execution.
Automated Python, handler and JavaScript logic checks cover the new inspector, but
they do not establish its rendered layout. Exact evidence is in [STATUS](STATUS.md).

## Run locally

From this directory, with the prepared CPython 3.11.15 / uv 0.11.24 environment
and Node 24.12.0 (used only for dependency-free UI logic checks):

```sh
sh scripts/bootstrap.sh
.venv/bin/python -B -m coordination_sim benchmark
```

The benchmark prints its fresh `runs/benchmark-…` path. Open **`judge.html`** inside
that directory for a self-contained offline replay. No network, browser storage,
Gemini or backend credentials are needed. The HTML contains synthetic judge
artifacts, so the persona selector is an inspector, not authentication.

On a host permitting loopback listeners, the local evaluation service can rerun
from the immutable fixture through the UI:

```sh
.venv/bin/python -B -m coordination_sim serve --port 8765
```

Open `http://127.0.0.1:8765`. `--run runs/benchmark-…` serves an existing result.
The service binds only loopback and exposes an allowlisted artifact reader and a
synthetic-only reset/run command. It never writes product data. The restricted
automation sandbox may reject socket binding, while the repository user has
successfully run the service locally. Archived desktop QA is in
`evals/browser-qa/`; the updated inspector and narrow layout remain NOT_RUN.

Other commands:

```sh
.venv/bin/python -B -m coordination_sim benchmark --cases A B portfolio
.venv/bin/python -B -m coordination_sim benchmark --cases portfolio
.venv/bin/python -B -m coordination_sim benchmark --cases HR
.venv/bin/python -B -m coordination_sim benchmark --cases impossible revoked no-impact unavailable concurrent
.venv/bin/python -B -m coordination_sim generate --preset medium
.venv/bin/python -B -m coordination_sim generate --preset demo
.venv/bin/python -B -m coordination_sim benchmark --preset demo
.venv/bin/python -B -m coordination_sim benchmark-schemas
.venv/bin/python -B -m coordination_sim acceptance
.venv/bin/python -B scripts/check_repository.py
```

`acceptance` retains full command output and an explicit `acceptance.json`; it
exits **1 while §13.1 is blocked**, even when all available automated checks pass.
`bootstrap.sh` is the repeatable offline regression baseline, separate from that
unavailable browser gate. Test failures and unknown/failed attempts are retained.

On another machine, use these installed prerequisites and resolve the existing
lock with any network access your environment requires:

```sh
mkdir -p .tmp
UV_CACHE_DIR=.cache/uv UV_PROJECT_ENVIRONMENT=.venv UV_PYTHON_DOWNLOADS=never TMPDIR="$PWD/.tmp" uv sync --project . --locked
```

No global installation, parent workspace registration or dependency downloads are
performed by routine bootstrap. Environment/cache/temp and all generated artifacts
remain under this directory. Git history and branch/index are user-managed.

## What is measured

The naive comparator sorts ready tasks by priority, deadline, release and stable
ID; chooses eligible owners by accepted/submitted/exposure familiarity then ID;
checks aggregate capacity; places earliest local segments; discovers collisions,
evicts authorised lower-priority work one at a time, propagates successors and
stops at a declared 200-iteration cap. Hierarchical relays use the explicit
reporting graph, which grants no content access. It never calls the neutral
validator as a repair oracle. Failed greedy placement is UNKNOWN, not a global
infeasibility claim. Individual release/effort contradictions can justify a
bounded refusal. This is a synthetic comparator, not a measured manual workplace.

The neutral validator independently recomputes tenant/references, eligibility and
source access, effort/segments, capacity/windows/budgets, dependencies/lags/reviews/
actual acceptance gates, deadlines, protected/started movement, direct ready-work
priority inversions, required exact approvals, source authority and disclosure.
It scores only; it never repairs. An independent four-slot oracle checks all
16 candidates. Common bad source assumptions remain outside arithmetic proof.

Synthetic acceptance times follow fixed-duration actor policies with explicit
review reservations. They are projected workload outcomes, not human execution
measurements. Observation clocks, schedule slots, harness monotonic runtime and
missing product/provider/model timings are separate. The original requested and
agreed dates stay in immutable before snapshots; deadline moves are reported.

[metrics/registry.v2.json](metrics/registry.v2.json) contains 20 primary rows and
28 additional automated/conditional definitions. Every observation carries its
version, unit, eligibility, evidence class, denominator/artifact references and
missing reason. Null is not zero. Failed/unknown/timeout/partial attempts remain
in aggregate counts. Exact A/B expectations are in
[the golden review](evals/golden-review.md). No percentage product improvement is
computed from replay.

## Fixtures, permissions and replay

| Preset | Employees | Teams | Projects | Initial tasks |
|---|---:|---:|---:|---:|
| tiny | 25 | 4 | 12 | 75 |
| medium | 100 | 10 | 30 | 350 |
| demo | 3,000 | 117 | 150 | 8,000 |

The judge/developer company inspector exposes all fictional employee profiles,
teams, projects and task records with search and pagination. Its graph is a
derived view over relational task, dependency, ownership, source and team links;
it is not a graph database or product authorisation surface. Persona graphs are
built only from each stored safe projection.

The five-day calendar uses explicit 15-minute slots anchored to an aware UTC
instant, with Asia/Tokyo display policy. Flexible windows overlap; active effort
and meetings cannot. At least 20 employees have multiple explicit memberships
(120 at demo scale) and one shared capacity budget. An unrelated tenant reuses
object IDs to exercise composite scoping. Calendar private content is reduced to
opaque occupancy. Profiles contain scheduling facts, not personality or global
employee rankings. Background packs use coherent delivery/onboarding/security/
migration templates; the fixtures are sparse, not representative workload data.

Teams, calendar, Planner, SharePoint/OneDrive and GitHub environments are all
**simulated**. They provide separately versioned source records, scoped grants,
bounded reads, freshness, pagination, throttle/unavailable states, revocation,
duplicate delivery and scripted partial/uncertain writes with idempotency and
conditional versions. Such tests do not validate live APIs or product recovery.

A is the Hikari deadline pull-in. B follows its resulting state and introduces a
Critical incident competing for QA and Security. The other six goldens cover
impossible deadline, revoked source, no impact, unavailable calendar, concurrent
commit capability and internal HR induction. HR is a supporting case, not a third
main story. A separate `portfolio` demo case pulls forward 12 work packages,
permits bounded reassignment, changes 12 owners across four teams, contacts 23
people and expands the naive considered scope to all 75 standalone tiny-fixture
tasks (all 80 tasks when run after A → B, which adds five incident tasks). It is
explicitly excluded from the primary A/B scorecard and is not a product replay.
Eight golden cases were manually reviewed by the implementing orchestrator; no
external domain-human review is claimed. **0 generated expansion and 0 held-out
cases**; the portfolio case is an authored supporting demonstration, not a held-out
evaluation case.

Connected authored replay is available only for `tiny`, seed 17, A → B. Its input
and prior-state hashes must match. It returns stored evidence verbatim, including
explicitly authored POVs and missing product stages. Other presets/seeds show
replay unavailable, never a regenerated stand-in. The source-confirmed **v2**
recording supersedes v1 for current runs while preserving the earlier file and
all prior artifacts. **REPLAY — NOT A PRODUCT RESULT.**

## Architecture and artifact inspection

`coordination_sim/benchmark/` owns contracts, generator, external fixture
behaviors, naive comparator, neutral validation, trace, SUT adapter, metrics,
runner, derived relational inspector and local presentation. `ui/` is a judge inspector, not a manager/employee
application. `evidence.py` defines optional observed product schemas without
executing product workflows. [PRODUCT_ADAPTER.md](PRODUCT_ADAPTER.md) specifies
the exact future supported API boundary and mapping gate.

Each attempt preserves the pre-state, event, canonical input, separate gold,
input manifest/mapping, outcome, validation, raw metrics and applicable captured
POVs. Run exports include append-only JSONL, text timeline, CSV, registry,
capabilities, aggregates, judge data/HTML and hashes. Manifests pin seed, method,
source/code/lock digests, hardware, limits and runtime exclusions. Historical
artifacts are create-once; hashes identify local bytes, not tamper-resistant storage.

The full structured company is currently imported into the harness. Scope metrics
separate that read/import size from considered, replanned, moved and notified
subsets. No model receives full company data because no model runs here. Background
source/calendar density and cross-team-edge counts are not claimed to match all
narrative targets; more realistic saturation needs separately reviewed fixtures.

Current work/evidence: [PLAN](PLAN.md), [STATUS](STATUS.md),
[DECISIONS](DECISIONS.md), [CHANGELOG](CHANGELOG.md),
[REQUIREMENTS_TO_EVIDENCE](REQUIREMENTS_TO_EVIDENCE.md).
