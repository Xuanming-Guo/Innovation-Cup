# Golden fixture arithmetic review — version 1

Reviewed by the implementing orchestrator, 2026-09-26, through explicit arithmetic,
source/trace inspection and mutations. This is not an independent human/customer
review. Eight development goldens; **0 generated expansion cases, 0 held-out cases**.
All use seed 17 and benchmark-2. Review precedes medium/demo execution. Expected
labels and this file are never supplied to either method or stored POV payloads.

Time is a 15-minute UTC-relative slot from Monday 2026-09-28 09:00 Asia/Tokyo.
Each day starts 96 slots later; working slots are 0–12 and 16–32 relative to that
day. The Security reservation is Tuesday slots 116–124. Frontend's already-started
commitment is Monday 0–8. These are fixture rules, not asserted legal requirements.

## A

The source request pulls the demo from Friday to Wednesday 15:00 (slot 216).
Five Hikari tasks each require four slots. Initial intervals are 16–20, 20–24,
96–100, 288–292, 404–408. Greedy ready selection gives 0–4, 8–12, 16–20, 20–24,
24–28. Frontend cannot use 0–8; lunch prevents QA beginning at 12. A review task
reserves QA capacity; dashboard acceptance occurs after QA, and Security follows.

All five owners remain. All five intervals and fixture-authorised agreed
deadlines change; no extension. Absolute start shifts are 16, 12, 80, 268, 380
slots = 756 × 15 = **11,340 minutes**. Seventy unchanged blocks make the median
zero; maximum 380 × 15 = **5,700**. These are shifted calendar minutes including
nights, not effort saved. Considered: 5 Hikari + 15 existing same-person background
commitments = 20. Preserved: 15/20 = **0.75**. Five planning attempts/versions,
no discovered collision, no approvals required beyond input movement authority.

Reporting paths from e0000 to owners e0004/e0005/e0007/e0006/e0008 have lengths
1,2,2,2,1 = 8. Initial request plus assignment notices traverse **16 hops**.
Eight unique recipients (five owners + three leads) each receive the same
normalised fact twice: **8 duplicate transmissions**. There are 75 assignments,
zero invalid ones, zero overload, zero hard/source/authority failures. Maximum
daily occupancy is 12/28 (frontend's 8 protected slots plus 4 dashboard slots).
Hikari synthetic accepted completion: 28 × 15 = **420 minutes**. The broad
considered set includes a background commitment ending slot 319: 4,785 minutes.
Read/import scope is the full 75-task snapshot; only 20 are considered, 5 replanned.
Incident service/collateral is NOT_APPLICABLE. Runtime is measured separately and
must be finite/nonnegative; no exact machine-time golden is appropriate.

## B

Begin with A's resulting schedule, not the initial snapshot. Incident injection
is slot 4. Fixed-duration incident sequence: 4–6, 6–10, 10–12, 16–18, 18–20.
The smoke test uses the same QA person as Hikari, displacing Hikari QA to 18–22;
then Security 22–26 and demo 26–30. All movements are unstarted and in-window.
The first two Hikari tasks and all unrelated background blocks remain unchanged.

Five new task choices plus three repairs = **8 attempts/versions**, **3 late
conflicts**. Three old blocks move two slots: **90 minutes total**, 30 maximum,
zero median, zero owner/deadline changes. Scope includes 15 pre-existing tasks;
12/15 = **0.8** preserved. Incident accepted duration (20−4)×15 = **240 minutes**;
latest blocking task i3 accepted at 18: **210 minutes**. Hikari (30−4)×15 = 390.
Three lower-priority commitments move; e0008 is newly affected outside the incident
owner set. A background end at 319 gives (319−4)×15 = 4,725 affected minutes.

Incident-owner reporting route lengths are 2,4,4,4,2: initial **16** hops. Eight
assignment routes (five incident + QA/Security/demo) total **27** hops. The
immediate QA collision adds **4** hops. Total **47**, with nine unique recipients;
one normalised incident change fact yields **38** repeats. 80 assignments,
zero invalid assignments, overload or neutral violations. Five relevant employees,
20 considered tasks, eight replanned. Full import is 80 tasks, not a claimed
small read footprint. Missing product/model size and stage evidence remain null.

## impossible

The first Hikari task needs four active slots, while the requested deadline is
slot 2 and release is 0. 0+4>2 proves infeasibility of this declared task scope
without relying on the heuristic's earlier choices. Refuse after one attempt;
retain the previous schedule, now late under the changed input. Do not count it
as accepted completion, remove it from denominators or extend its deadline.

## revoked

The exact requirement source is revoked before the attempt. Essential grants do
not make revoked content current. The first owner check fails; one required
clarification is logged. INVALID_INPUT / REFUSED; no acceptance. The neutral
report still records the invalidity of retaining the now-stale prior schedule.

## no-impact

No changed scheduling task: zero affected denominator, zero movements, zero
iterations/hops/contacts. Preservation is null, not 100%. Full initial concrete
schedule remains valid. Incident-only metrics are NOT_APPLICABLE.

## unavailable

Security's calendar availability is unknown. Local Hikari proposals can precede
the Security lookup, but no successful repair/acceptance is claimed. UNKNOWN,
one required clarification, no invented free capacity. Retain partial proposals
for scoring and include the failure in aggregate attempt counts.

## concurrent

This case probes the product's transactional boundary. The naive comparator
reports UNKNOWN with zero scheduling attempts and explains that it cannot
execute a competing commit. Replay does not simulate a transaction service.
`stale_concurrent` remains NOT_MEASURED. Schema/response tests separately mutate
revision/digest bindings; they are not product concurrent-commit evidence.

## HR

Internal induction preparation e0011 at 4–6, technical orientation e0006 at 6–8.
Two slots each, proper source grants and confirmed Security qualification. The
Tuesday private reservation stays opaque and untouched. Two new assignments,
77 total tasks, two local attempts, no previous commitments changed. This is a
supporting compatibility case, not a third judge-facing story. No recruiting,
payroll, ranking or HRIS behavior is present.

## Independent tiny oracle and negative review

`tests/test_oracle.py` enumerates every ordered one-slot pair in a four-slot
window with slot 2 unavailable: exactly (0,1), (0,3), (1,3) are valid. The oracle
uses set arithmetic and never calls a scheduler or neutral validator. All 16
candidates are then compared against the neutral validator. Separate schedule
mutations exercise missing owners, tenant/reference errors, wrong skills/access,
segment minimum/count, passive time, capacity, budgets, reviews, acceptance gates,
original deadlines, protected/started work, priority, bound approvals and disclosure.
