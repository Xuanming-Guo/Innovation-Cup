# Approval and commitment boundary

This boundary turns an independently validated proposal into shared work only after the exact
required authorities approve it. It does not run Z3, reinterpret source material or allow an
approval to follow a changed proposal.

## State model

`plans` remains an immutable proposal ledger. Approval and commitment are additive records:

```text
validated plan proposal
  -> approval requirements for exact digests and base revision
  -> immutable approve/reject decisions with expiry
  -> current-authority recheck
  -> short atomic commit under company planning-revision lock
  -> work items + assignments + committed blocks + approval uses + audit + outbox
```

A proposal is displayed as `proposed`, `approved`, `rejected`, `stale` or `committed`. These are
derived review states, not rewrites of the immutable solver proposal. A draft or approved plan is
never presented as applied; only a `plan_commitments` row proves database commitment.

## Exact approval binding

Every requirement and decision binds all of the following:

- proposal digest;
- planning-snapshot digest;
- source-manifest digest;
- base company planning revision;
- policy revision and named planning-policy version;
- the requirement's separately hashed artifact; and
- decision time, expiry, actor membership and idempotent command digest.

The database rechecks source freshness, company/policy revisions and the actor's current
membership and authority both when recording the decision and when consuming it. Changed state
returns an explicit stale/replan result. It never transfers the old approval to regenerated work.

The baseline planning requirement needs a company manager. Deadline changes need their explicit
planning requirement. Cross-team displacement requirements name each affected team and accept
only a current manager of that team or a company administrator. Trusted policy code derives these
requirements; model output is advisory and cannot mint authority. If an admitted movement lacks a
typed affected-team mapping, commitment fails closed to a company-administrator requirement rather
than guessing which manager may approve it.

## Planning versus disclosure

Planning approval and employee-brief disclosure are separate approval domains. A planning
approval can authorize the plan commit, but it cannot authorize an employee-facing brief or
audience. A disclosure requirement binds the brief digest and audience scope separately. The
commit path emits no brief-publication intent merely because planning approval exists.

## Atomic commit and concurrency

`app.commit_approved_plan` acquires a row lock on the company, compares the current planning
revision with the proposal's base revision, revalidates every exact binding and approval, then
writes one transaction containing:

- the commitment and consumed-approval links;
- work items and assignments copied from the validated candidate;
- timestamped committed schedule blocks;
- a durable outbox intent; and
- a structured audit event with actor, policy, digests, outcome and correlation ID.

It advances the company planning revision exactly once. A concurrent proposal based on the same
old revision waits for the lock and then receives `stale`, so it must be replanned. Replaying the
same idempotent commit returns the original commitment.

Active exclusive owner/participant blocks use half-open UTC ranges and a PostgreSQL exclusion
constraint. Overlapping flexible task windows are harmless, while overlapping committed human
effort is rejected. Passive waiting and shared-capacity blocks are not treated as exclusive human
effort.

## API and UI

Manager endpoints are:

- `GET /v1/companies/{company_id}/plans/{plan_id}`;
- `GET /v1/companies/{company_id}/plans/{plan_id}/evidence`;
- `POST /v1/companies/{company_id}/plans/{plan_id}/approve`;
- `POST /v1/companies/{company_id}/plans/{plan_id}/reject`; and
- `POST /v1/companies/{company_id}/plans/{plan_id}/commit`.

High-impact POST operations require `Idempotency-Key` plus the exact binding in the request body.
The desktop includes the manager review, schedule, evidence, assumption and diagnostic surfaces.
Until authenticated runtime wiring is added, the repository UI is explicitly labelled as a
non-mutating design preview and keeps approval/commit controls disabled.

## Evidence limits

Repository tests cover policy derivation, API role/error behavior, exact database binding,
idempotent replay, stale competing commits, exact candidate materialization, revision advancement,
audit and outbox creation. They do not prove hosted migration application, production concurrency
throughput, an authenticated desktop session or an external connector delivery.
