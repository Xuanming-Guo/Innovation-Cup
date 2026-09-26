# GitHub development workflow

## Operating model

Use trunk-based development with a protected `main` branch and short-lived topic branches. `main` must remain reviewable and releasable; unfinished or untested capability stays behind a disabled feature flag or outside `main`.

Repository settings should enable Issues, Projects if the team uses them, squash merging and automatic head-branch deletion. Disable merge commits and rebase merging so each PR produces one traceable commit. Enable private vulnerability reporting where available.

## Issues

Open an issue before non-trivial work. Use the supplied forms for bugs, features and implementation tasks. An issue must describe the problem, scope, acceptance criteria, dependencies, security/privacy implications and evidence needed to close it.

Use labels from a small controlled vocabulary:

- Type: `type: bug`, `type: feature`, `type: task`, `type: docs`, `type: security`.
- Area: `area: desktop`, `area: api`, `area: data`, `area: planner`, `area: integrations`, `area: evals`, `area: ci`.
- Priority: `priority: p0`, `priority: p1`, `priority: p2`.
- State: `state: blocked`, `state: needs-decision`, `state: ready`.

Do not use issue comments for secrets, real employee/customer data or exploit details. Security reports follow [.github/SECURITY.md](../../.github/SECURITY.md).

## Branch names

Use one of these lowercase prefixes followed by a kebab-case slug:

| Prefix | Use | Example |
|---|---|---|
| `feat/` | User-visible capability | `feat/123-plan-review` |
| `fix/` | Defect correction | `fix/456-stale-approval` |
| `docs/` | Documentation only | `docs/source-to-z3` |
| `refactor/` | Behaviour-preserving code change | `refactor/212-planner-boundaries` |
| `test/` | Test-only work | `test/87-cross-tenant-cases` |
| `ci/` | Automation and workflow | `ci/native-build-matrix` |
| `security/` | Security hardening | `security/91-jwt-validation` |
| `chore/` | Repository maintenance | `chore/dependency-policy` |
| `release/` | Release preparation | `release/v0.1.0` |

Include the issue number when one exists. Branches such as `dev`, `changes`, `temp`, personal names and long-lived integration branches are not permitted.

## Commits

Use Conventional Commit subjects:

```text
type(optional-scope): imperative summary
```

Allowed types are `feat`, `fix`, `docs`, `refactor`, `test`, `ci`, `build`, `perf`, `security`, `chore`, `revert`. Examples:

```text
feat(planner): compile typed eligibility constraints
fix(auth): reject revoked memberships at commit
docs(architecture): clarify the source-to-z3 boundary
```

Keep commits cohesive and reviewable. Never include secrets, generated build outputs or unrelated formatting churn.

## Pull requests

A pull request must:

- Link its issue with `Closes #<number>` or explain why no issue is needed.
- State user-visible and architectural effects.
- Identify authority, privacy, data, migration and compatibility risks.
- Include tests run with actual outcomes and list anything not run.
- Update documentation and generated contracts where behaviour changes.
- Keep optional or incomplete features disabled and honestly labelled.
- Resolve every review conversation before merge.

Draft PRs are encouraged for early integration but are never merged. The PR title must follow the same Conventional Commit form because it becomes the squash commit subject.

## Required checks and reviews

Configure a `main` ruleset with:

- Pull requests required before merge.
- Required status check `Repository quality / repository-contract` with branches required to be current.
- All review conversations resolved.
- Force pushes and branch deletion blocked.
- Linear history required.
- One approving review when at least two maintainers are active. While the repository has only one maintainer, use zero required approvals but retain the PR, checks and documented self-review; increase this to one as soon as another maintainer joins.
- Administrator bypass restricted to emergencies and documented in the affected PR or follow-up issue.

Future subsystem checks become required only after they exist and are stable: backend tests, desktop tests, migration tests, contract drift, security tests and native build smoke checks. Do not require a fictional check.

## Merge and release policy

Squash merge is the default. The squash subject uses the approved PR title; the body retains issue links, risk and evidence. Delete the branch after merge. Revert through a new PR unless an active incident requires the documented emergency path.

Use Semantic Versioning once distributable artifacts exist. Tags are `vMAJOR.MINOR.PATCH` and point to reviewed release commits. A release manifest must record commit, platform/architecture, checksum, signing/notarisation state and tests actually executed. Artifact existence alone does not establish platform support.
