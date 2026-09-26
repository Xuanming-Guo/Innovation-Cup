# Planning and Z3 boundary

This document describes the implemented planner boundary. It supplements the authoritative
master specification; it does not redefine product policy.

## Input and trust boundary

Z3 never receives source text, Gemini prose, JSON expressions, Python, SQL or SMT-LIB. Trusted
code accepts only the discriminated, allowlisted `ValidatedConstraint` families in
`coordination.planning.contracts`. Every constraint has a stable ID, company, hard/preferred
status, typed payload, evidence or authority references, confidentiality, negotiability and a
confirmed state.

`PlanningSnapshot.freeze` sorts those constraints, binds the company/request/candidate and base
company revision, finite UTC horizon, slot size, source-manifest digest, permission/profile/
estimate/compiler versions and planning policy, then computes a canonical SHA-256 digest. A
changed fact or policy creates a different snapshot; the solver does not edit a snapshot.

The implemented families cover task/resource definitions, effort, eligibility, working windows,
fixed attendance, dependency lag, acceptance review and reviewer separation, requested/agreed/
forecast and hard deadline fields, priority tiers, immutable reservations, shared resources,
segmentation and explicit movement authority. Unknown or incomplete families fail before Z3.

## Compilation and solving

The compiler normalises and rejects duplicate definitions, missing task contracts, cycles,
unknown resources, empty eligibility, inconsistent fixed work, stale/out-of-horizon slots and
models above configured task/resource/slot/Boolean-variable limits. It then creates only finite
integer and Boolean variables:

- one eligible owner per active task;
- exact active-effort slots inside current resource availability and the task window;
- exact fixed attendance for every participant;
- no human or shared-resource capacity overflow, including immutable reservations;
- daily active budgets, minimum segment length and maximum fragmentation;
- actual start/finish derived from occupied slots;
- dependency lag, review order and reviewer separation;
- hard deadlines and authorised deadline envelopes; and
- exact pinning for protected commitments.

Objectives are lexicographic: service/lateness and completion by priority tier, owner changes,
slot displacement, fragmentation, then deterministic task-level tie breakers. The result is
reported as optimal only when Z3 exposes equal lower and upper objective bounds. The solver
version, compiler/model/snapshot digests, objective vector, timeout, resource limit and runtime
are recorded.

The first attempt is `pinned_insertion`: locked and authorised existing commitments are fixed. A
failed attempt means only that insertion scope is infeasible. If policy permits and at least one
commitment explicitly carries movement authority, the engine runs one `authorized_repair`
attempt against the same hard constraints. It does not retry an unchanged scope, delete a hard
constraint, invent capacity, change effort or grant deadline/access authority.

## Status and diagnosis

Application classifications are `OPTIMAL_WITHIN_MODEL`, `FEASIBLE`,
`INFEASIBLE_WITHIN_SCOPE`, `UNKNOWN_OR_TIMEOUT` and `INVALID_INPUT`. Native status remains
separate (`sat`, `unsat`, `unknown`, `invalid`), and termination records completed, timeout,
resource-limit, other unknown or invalid-input causes. An UNSAT diagnostic solve tracks stable
constraint IDs; its core is described as a sufficient conflicting subset, never automatically as
the smallest explanation.

## Independent validation

`coordination.planning.validator` imports no Z3 API. It expands the returned concrete blocks and
recomputes task effort, owner eligibility, availability, fixed attendance, segmentation,
deadlines, dependency and review order, reviewer separation, movement protection, shared and
human per-slot capacity, daily budgets and snapshot membership. A SAT model is not selectable
when this report fails. Tests deliberately corrupt solver output and confirm rejection.

## Persistence and current limitation

Migration `20260926015000_planning_solver_ledger.sql` stores immutable constraints and source
links, snapshots, snapshot membership, solver attempts, validated plan proposals, placements and
schedule blocks behind company RLS. The API role is read-only for these records; the worker may
insert but cannot update or delete frozen artifacts.

The planner is currently a tested backend domain capability and persistence boundary. Issue #12
will connect it to durable job dispatch and API status retrieval. No hosted migration, production
solve, performance benchmark, live customer schedule or approval/commitment is claimed here.
