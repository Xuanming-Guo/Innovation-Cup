# Employee workflow boundary

Issue #11 implements the human-led path from an approved committed task through acknowledgement,
work, versioned submission and accountable review. The repository implementation is complete at
the API/database and desktop-preview boundaries. It is not evidence that the migration is applied
to hosted Supabase or that the desktop has a live authenticated session.

## Authorised employee projection

`GET /v1/companies/{company_id}/me/tasks?view=...` resolves the bearer token to one active company
membership and employee profile. The query returns only:

- the employee's active owner assignments;
- committed task identity, title, lifecycle version and timing;
- the exact review policy relevant to the current submission;
- the exact employee-brief version bound when the task was committed, and only while its separate
  disclosure approval and audience grant remain current.

It does not read candidate contracts, raw constraints, solver diagnostics, other teams' task
content or unrestricted plan context. Company administrative roles are not task-content grants.
Task managers, participants, reviewers and employees receive explicit task-scoped relationships.

## Lifecycle and concurrency

The task lifecycle is:

`ready -> assigned -> acknowledged -> in_progress <-> blocked -> submitted -> accepted`

`submitted -> revision_requested -> submitted` creates a new immutable submission version.
Employee commands bind the expected task row version, an actor-scoped idempotency key, a canonical
command digest and a correlation ID. Database advisory locks serialize same-key retries. Identical
retries return their original recorded result; changed payloads using the same key fail. Estimate,
skill, input and availability flags create correction records without treating an objection as
work-ethic evidence. General task events omit the private correction detail.

Assignment changes update `employee_workload_state` immediately. Starting work records exposure,
but assignment alone is not evidence of skill. Submission evidence is provisional. A revision
request disputes that provisional evidence without increasing the employee profile revision.
Acceptance creates accepted familiarity and effort evidence and increments only the submitting
employee's profile revision.

## Submission and file boundary

`POST /v1/companies/{company_id}/tasks/{task_id}/submissions` accepts narrative, bounded external
references, optional active minutes and private-file IDs. A file is attachable only when it:

- belongs to the submitting employee and has purpose `submission`;
- passed the quarantine scanner with matching declared/detected MIME type and observed size;
- has a recorded SHA-256 checksum, nonblank scanner version and final private object path;
- is in the `available`/`clean` state and has not been used by another submission.

Submission files do not inherit source-reader access and company administration alone does not
grant access. The uploader and task-scoped authorised readers may request a short signed download
through the existing Storage gateway. Issue #12 owns durable scanner dispatch and object movement;
the migration in this slice defines and tests the worker-only scan-result transition.

## Exact review

Managers set a versioned review policy before submission. The policy change is idempotent, advances
the task version and is auditable through correlation metadata and an outbox refresh intent. A task
owner cannot be named as an ordinary reviewer; self-certification requires an explicit deterministic
rule.

Each submission stores the exact review-policy ID used at submission time. Reassigning the reviewer
later cannot change who reviews that version. A reviewer first reads
`GET /v1/companies/{company_id}/submissions/{submission_id}`, which returns the immutable version,
digest, narrative, clean file metadata and policy version. The review command must repeat that exact
version and digest. Acceptance or revision applies once to that submission; later uploads never
inherit an earlier decision.

## API surface

- `GET /v1/companies/{company_id}/me/tasks`
- `POST /v1/companies/{company_id}/tasks/{task_id}/events`
- `PUT /v1/companies/{company_id}/tasks/{task_id}/review-policy`
- `POST /v1/companies/{company_id}/tasks/{task_id}/submissions`
- `GET /v1/companies/{company_id}/submissions/{submission_id}`
- `POST /v1/companies/{company_id}/submissions/{submission_id}/review`

All commands require the authenticated company context. Mutating operations that may be retried use
`Idempotency-Key`; lifecycle, policy and submission operations also bind the current task version.
Not-found responses do not distinguish absent objects from objects outside the actor's scope.

## Current delivery boundary

The desktop provides a professional, responsive employee-workspace preview covering Today,
Upcoming, Blocked and Submitted states. Preview records are explicitly labelled sample/read-only,
and mutation controls stay disabled until issue #12 connects the authenticated native session,
refresh signals and durable worker/outbox processing. Hosted migration, live file scanning and
installed Windows/macOS smoke tests remain separate deployment evidence.
