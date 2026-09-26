# Implementation status

This ledger distinguishes repository evidence from intended scope. Update it in every PR that
changes capability state.

| Capability | State | Evidence | Remaining gate |
|---|---|---|---|
| Repository governance | Implemented | Repository contract workflow and development guide | Protect `main` in GitHub settings |
| Desktop manager and employee UI | Implemented and Windows build-tested; live workflow still partial | Tauri/React surfaces plus cached Supabase session integration, private user-topic refresh, authorised API refetch on reconnect/focus/online and frontend tests | Sign-in/company selection and replacing preview records with live workflow data in #13; installed Windows/macOS smoke tests |
| API foundation and company context | Implemented locally | FastAPI health/version/session endpoints, asymmetric Supabase JWT verification, current-membership tests and durable-schema readiness | Hosted deployment and live Supabase evaluation |
| Durable worker and notifications | Implemented and repository-tested locally | Postgres queue/leases, exact attempt fencing, renewal, retry/dead-letter/review/cancel states, heartbeats, structured events, internal outbox delivery, recipient notifications, private constant Realtime refresh and 34 pgTAP assertions | Hosted crash/restart and Realtime evaluation; real malware scanner remains unconfigured |
| Supabase identity/tenant/storage/interpretation/planning/approval/employee/durable schema | Implemented and repository-tested | Nine ordered migrations, migration manifest, pgTAP isolation/state-machine tests, private ticket Edge Function, immutable ledgers and atomic commitment/outbox boundaries | Founder applies migrations/functions and provisions runtime secrets; live hosted isolation/concurrency test |
| Gemini interpretation | Implemented and fixture-tested locally | Pinned official SDK adapter, strict candidate schema, bounded projection, deterministic admission/run ledger plus durable worker dispatch | Live credential/provider evaluation; trusted candidate-to-snapshot materialisation in #13 |
| Z3 planning/validation | Implemented and fixture-tested locally | Pinned native solver, typed allowlist, canonical snapshots/model digests, finite limits, bounded repair, independent validator, immutable result ledger and durable snapshot jobs | Candidate-to-constraint/snapshot materialisation; hosted performance/evaluation evidence in #13 |
| Approval/commitment | Implemented and fixture-tested locally | Exact bindings, current-authority rechecks, separate disclosure, manager API, exclusion-protected schedule blocks, atomic revision commit, audit/outbox writes and durable internal notification delivery | Hosted migration/application test; live desktop workflow data in #13 |
| Employee submission/review | Implemented and fixture-tested locally | Permission-safe views, exact brief binding, versioned lifecycle/review, correction privacy, accepted evidence, API endpoints, desktop preview and durable quarantine dispatch | Live desktop workflow data and real scanner/object movement; hosted application test |
| Connected demo/evaluation | Not implemented | Specification only | #13 |
| Windows installer | Produced locally, not published | NSIS build command completed for version 0.1.0; build output is intentionally untracked | #13 signed CI artifact and installed-app smoke test |
| macOS app/DMG | Not produced | Release workflow not yet implemented | #13 native builds and hardware tests |

The interface image under `docs/design/` remains a design reference; the manager-review screen is
now implemented as a clearly labelled, non-mutating preview. An existing Supabase session can
refresh authorised state, but preview records are not represented as live API data. Nothing under
`simulation/` is part of this implementation ledger.
