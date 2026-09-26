# Implementation status

This ledger distinguishes repository evidence from intended scope. Update it in every PR that
changes capability state.

| Capability | State | Evidence | Remaining gate |
|---|---|---|---|
| Repository governance | Implemented | Repository contract workflow and development guide | Protect `main` in GitHub settings |
| Desktop foundation | Implemented and Windows build-tested | Tauri/React source, frontend tests, Rust tests, native CI, and local Windows release build | Installed Windows/macOS smoke tests |
| API foundation | Implemented locally | FastAPI health/version endpoints and tests | Hosted deployment and dependency readiness |
| Worker foundation | Implemented locally, queue disabled | Separate worker command and tests | Durable queue/lease implementation in #12 |
| Supabase schema/auth/storage | Not implemented | Specification only | #7 and founder-applied migrations |
| Gemini interpretation | Not implemented | Configuration boundary only | #8 plus real credential evaluation |
| Z3 planning/validation | Not implemented | Specification only | #9 tests and solver evidence |
| Approval/commitment | Not implemented | Specification only | #10 |
| Employee submission/review | Not implemented | Specification only | #11 |
| Connected demo/evaluation | Not implemented | Specification only | #13 |
| Windows installer | Produced locally, not published | NSIS build command completed for version 0.1.0; build output is intentionally untracked | #13 signed CI artifact and installed-app smoke test |
| macOS app/DMG | Not produced | Release workflow not yet implemented | #13 native builds and hardware tests |

The interface image under `docs/design/` is a design reference, not a working screen or test
result. Nothing under `simulation/` is part of this implementation ledger.
