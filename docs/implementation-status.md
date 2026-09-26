# Implementation status

This ledger distinguishes repository evidence from intended scope. Update it in every PR that
changes capability state.

| Capability | State | Evidence | Remaining gate |
|---|---|---|---|
| Repository governance | Implemented | Repository contract workflow and development guide | Protect `main` in GitHub settings |
| Desktop manager and employee UI | Implemented and Windows build-tested | Tauri/React source, draft-safe plan review plus read-only employee Today/Upcoming/Blocked/Submitted workspace, frontend tests, Rust tests, native CI and local Windows release build | Authenticated desktop/API wiring in #12; installed Windows/macOS smoke tests |
| API foundation and company context | Implemented locally | FastAPI health/version/session endpoints, asymmetric Supabase JWT verification and current-membership tests | Hosted deployment and live Supabase evaluation |
| Worker foundation | Implemented locally, queue disabled | Separate worker command and tests | Durable queue/lease implementation in #12 |
| Supabase identity/tenant/storage/interpretation/planning/approval/employee schema | Implemented and repository-tested | Eight ordered migrations, migration manifest, pgTAP isolation tests, private ticket Edge Function, immutable planning/approval/submission ledgers and atomic commitment/review boundary tests | Founder applies migrations/functions and provisions runtime secrets; live hosted isolation/concurrency test |
| Gemini interpretation | Implemented and fixture-tested locally | Pinned official SDK adapter, strict candidate schema, bounded projection, deterministic admission, run ledger and failure tests | Live credential/provider evaluation; durable worker dispatch in #12 |
| Z3 planning/validation | Implemented and fixture-tested locally | Pinned native solver, typed allowlist, canonical snapshots/model digests, finite limits, pinned insertion, one bounded authorised repair, stable diagnostics, independent validator and immutable result ledger | Durable worker/API orchestration in #12; hosted performance/evaluation evidence in #13 |
| Approval/commitment | Implemented and fixture-tested locally | Exact proposal/source/snapshot/base/policy bindings, current-authority rechecks, separate disclosure domain, manager API, exclusion-protected schedule blocks, atomic revision commit, audit/outbox writes and stale competing-commit tests | Hosted migration/application test; authenticated desktop wiring and durable outbox processing in #12 |
| Employee submission/review | Implemented and fixture-tested locally | Permission-safe employee task projection, exact approved brief binding, versioned lifecycle/idempotency, immediate workload state, quarantined-file scan contract, exact reviewer-policy/submission binding, correction privacy, accepted-evidence rules, FastAPI endpoints and desktop preview | Hosted migration/application test; durable scanner/outbox and authenticated desktop wiring in #12 |
| Connected demo/evaluation | Not implemented | Specification only | #13 |
| Windows installer | Produced locally, not published | NSIS build command completed for version 0.1.0; build output is intentionally untracked | #13 signed CI artifact and installed-app smoke test |
| macOS app/DMG | Not produced | Release workflow not yet implemented | #13 native builds and hardware tests |

The interface image under `docs/design/` remains a design reference; the manager-review screen is
now implemented as a clearly labelled, non-mutating preview until authenticated runtime wiring is
added. Nothing under `simulation/` is part of this implementation ledger.
