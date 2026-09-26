# Implementation status

This ledger distinguishes repository evidence from intended scope. Update it in every PR that
changes capability state.

| Capability | State | Evidence | Remaining gate |
|---|---|---|---|
| Repository governance | Implemented | Repository contract workflow and development guide | Protect `main` in GitHub settings |
| Desktop manager, employee and Connections UI | Implemented and Windows build-tested locally | Connected Tauri/React surfaces, Supabase session integration, private refresh, authorised workflow APIs and administrator-only company Gemini configuration with no key readback | Hosted connected smoke test and installed Windows/macOS tests |
| API foundation and company context | Implemented locally | FastAPI health/version/session endpoints, asymmetric Supabase JWT verification, current-membership tests and durable-schema readiness | Hosted deployment and live Supabase evaluation |
| Durable worker and notifications | Implemented and repository-tested locally | Postgres queue/leases, exact attempt fencing, renewal, retry/dead-letter/review/cancel states, heartbeats, structured events, internal outbox delivery, recipient notifications, private constant Realtime refresh and 34 pgTAP assertions | Hosted crash/restart and Realtime evaluation; real malware scanner remains unconfigured |
| Supabase identity/tenant/storage/interpretation/planning/approval/employee/durable/BYOK schema | Implemented and repository-tested | Eleven ordered migrations and 181 passing pgTAP assertions, private ticket Edge Function, immutable ledgers, atomic commitment/outbox, Vault-encrypted company keys and worker-only plaintext resolution | Founder applies migrations/functions; live hosted isolation/concurrency test |
| Gemini interpretation and company BYOK | Implemented and fixture-tested locally | Pinned official SDK adapter, strict candidate schema, bounded projection, deterministic admission/run ledger, administrator verify/rotate/remove API, Supabase Vault storage and tenant-resolved durable dispatch | Live company credential/provider evaluation remains **NOT RUN** |
| Z3 planning/validation | Implemented and fixture-tested locally | Trusted candidate materialisation, typed allowlist, canonical snapshots/model digests, finite limits, bounded repair, independent validator, immutable result ledger and durable snapshot jobs | Hosted performance/evaluation evidence in #13 |
| Approval/commitment | Implemented and fixture-tested locally | Exact bindings, current-authority rechecks, separate disclosure, manager API, exclusion-protected schedule blocks, atomic revision commit, audit/outbox writes and durable internal notification delivery | Hosted migration/application test; live desktop workflow data in #13 |
| Employee submission/review | Implemented and fixture-tested locally | Permission-safe views, exact brief binding, versioned lifecycle/review, correction privacy, accepted evidence, API endpoints, desktop preview and durable quarantine dispatch | Live desktop workflow data and real scanner/object movement; hosted application test |
| Connected demo/evaluation | In implementation | Deterministic software/HR seed, fixture Gemini boundary, trusted materialisation and connected workflow surfaces | Finish evaluation runner, failure evidence and cross-OS hosted exercise in #13 |
| Windows installer | Produced locally, not published | NSIS build command completed for version 0.1.0; build output is intentionally untracked | #13 signed CI artifact and installed-app smoke test |
| macOS app/DMG | Not produced | Release workflow not yet implemented | #13 native builds and hardware tests |

The interface image under `docs/design/` remains a design reference. Connected surfaces render
only authorised API data; deterministic provider fixtures are labelled at their source boundary
and do not become hard-coded UI records. Nothing under `simulation/` is part of this
implementation ledger.
