# ALTO

**Every change, coordinated.**

[![Repository quality](https://github.com/Xuanming-Guo/Innovation-Cup/actions/workflows/quality.yml/badge.svg)](https://github.com/Xuanming-Guo/Innovation-Cup/actions/workflows/quality.yml)

ALTO is a human-led coordination application for the Recruit Holdings Innovation Cup 2026. It turns an authorised organisational goal into an evidence-linked, capacity-feasible plan, verifies that plan against encoded constraints, and keeps people in control of approval and execution.

- [Download ALTO and watch the demo](https://xuanming-guo.github.io/Innovation-Cup/)
- [Explore the Data Room](https://drive.google.com/drive/folders/1H0xRJpa73xkRBztrmQzJI5bub6HVkQe3?usp=sharing)
- [Release notes and checksums](https://github.com/Xuanming-Guo/Innovation-Cup/releases/latest)
- [Read the ALTO operating guide](docs/development/alto-runbook.md)

## Try the judge demo

The public demo opens as Maya, a director at the synthetic company Northstar Labs. Each installation receives its own anonymous Supabase identity and isolated demo run; judges do not need to create an account or provide an AI credential.

The first-run tour:

1. Opens **Settings → AI credentials and deployment** and explains that the demo is already configured.
2. Returns to Home, selects **Question**, sends “Hi! What are you and what do you do?”, and waits for the real assistant response.
3. Prompts the user to select **Prepare the Northstar launch plan** and follow the planning flow.

The demo uses synthetic people, projects, availability, and source material. It does not contain real employee or customer data.

## Downloads

The landing page uses permanent links to the assets on the latest published GitHub Release:

| Platform | Release asset | Distribution state |
|---|---|---|
| Mac with Apple silicon | `ALTO-mac-apple-silicon.dmg` | Ad-hoc signed; not notarized |
| Windows x64 | `ALTO-windows-x64-setup.exe` | Unsigned |
| Mac with Intel processor | `ALTO-mac-intel.dmg` | Ad-hoc signed; not notarized |

Those links become available only when a published release contains all three exact filenames. Temporary GitHub Actions artifacts do not satisfy the download links. Publishing a newer release with the same stable filenames automatically moves the landing page downloads to the new files; no website edit is required.

These are hackathon demo builds. Verify the published SHA-256 checksum before opening a downloaded installer.

### Opening the Windows build

Windows may show a Microsoft Defender SmartScreen warning because the installer is unsigned. Confirm that the file came from this repository and that its checksum matches the published value, then use **More info → Run anyway** for this installer only.

### Opening a Mac build

1. Open the DMG and move ALTO to **Applications**.
2. In Finder, Control-click ALTO and choose **Open**.
3. If macOS still blocks it, try opening it once, then open **System Settings → Privacy & Security** and choose **Open Anyway** for ALTO.

Do not disable Gatekeeper or other operating-system protections globally. The macOS packages are built on native GitHub-hosted runners and inspected in CI, but they have not been installed or hardware-tested on a physical Mac. The Windows release requires a separate installed smoke test before it is described as tested.

## How downloaded apps reach the demo backend

Every supported desktop package uses the same authenticated service-discovery flow:

```text
Downloaded ALTO app
  → anonymous Supabase Auth
  → authenticated service discovery
  → ALTO API and durable worker
  → Gemini and Z3 processing
```

The installers contain only public connection settings: the Supabase project URL, Supabase publishable key, Northstar company UUID, and discovery mode. Database credentials, privileged Supabase credentials, and Google AI credentials are never included in the desktop bundle. Provider credentials remain server-side and encrypted through Supabase Vault.

Service discovery allows the public backend endpoint to change without rebuilding the installers. If the backend is unavailable, clients fail closed and show a service-unavailable state.

## What ALTO does

A manager describes a desired outcome or change in natural language. ALTO retrieves the permitted commitments, sources, priorities, deadlines, dependencies, and capacity it already knows. It asks for genuinely missing information and reserves material decisions for an authorised person.

Gemini proposes typed task contracts and complete candidate plans. Trusted code validates their evidence, meaning, and authority. Z3 verifies the submitted owners and times against admitted constraints without silently choosing a replacement schedule. An independent validator checks the concrete plan before exact-version approval and atomic commitment. Employees then receive authorised briefs, complete work, submit evidence, and optionally share private preference feedback for later planning.

ALTO is not an all-knowing AI manager. Models interpret and explain; trusted code enforces identity, permissions, supported constraints, and state transitions; humans remain responsible for material approval.

```text
Authorised sources
  → versioned evidence
  → typed task contracts
  → immutable planning snapshot
  → complete candidate plan
  → fixed-value Z3 verification
  → independent validation
  → human approval and atomic commitment
  → authorised employee work
  → exact-version submission and review
```

## Architecture

| Area | Technology and trust boundary |
|---|---|
| Desktop | Tauri 2, React, TypeScript, and Vite |
| API | Python, FastAPI, and Pydantic |
| Worker | Separate durable Python worker for model, planning, and background jobs |
| Planning | Server-side `z3-solver` with deterministic compilation and independent validation |
| Model | Google Gemini through a typed server-side adapter and validated Vault-backed credential |
| Platform | Supabase Auth, Postgres, Vault, private Storage, Realtime, and durable job state |
| Deployment | FastAPI and the durable worker behind an authenticated HTTPS service boundary |
| Native targets | Windows 11 x64 and macOS 13+ on Apple silicon and Intel |

Supabase is the shared system of record. Installed clients authenticate with Supabase and resolve the current API endpoint through company-scoped service discovery. All application commands continue to enforce the authenticated identity, company membership, run scope, actor grants, and current authority on the server.

## Repository layout

```text
.github/                 Pull-request templates and CI/release workflows
apps/desktop/            Tauri and React desktop application
deploy/local-host/       Demo deployment configuration and safe environment template
docs/                    Product, architecture, security, and operating documentation
landing page/            Static GitHub Pages download and demo site
scripts/                 Repository, host, and release validation tools
services/backend/        FastAPI API and durable worker
supabase/                Migrations, database tests, Edge Functions, and operator tools
```

## Local development

The root project requires Node.js 24 and npm 11. The backend supports Python 3.11–3.13 and uses `uv` for its locked environment.

```powershell
npm.cmd ci
uv sync --project services/backend --locked
npm.cmd run doctor
```

Run the API, worker, and native desktop in separate terminals:

```powershell
npm.cmd run dev:api
npm.cmd run dev:worker
npm.cmd run dev:desktop
```

Run the repository verification suite with:

```powershell
npm.cmd run check
```

Local and hosted setup require ignored environment files derived from the committed `.env.example` templates. Never commit filled environment files or copy a database password, service-role key, runtime DSN, or provider credential into a `VITE_` variable.

## Documentation

| Document | Purpose |
|---|---|
| [ALTO runbook](docs/development/alto-runbook.md) | Setup, locked judge mode, walkthrough, troubleshooting, and verification |
| [Implementation status](docs/implementation-status.md) | Evidence-backed capability ledger and outstanding gates |
| [Implementation journal](docs/development/alto-implementation-journal.md) | Commands, observations, and current verification evidence |
| [Storyboard coverage](docs/storyboard-coverage.md) | Mapping from supplied manager/employee references to implemented states |
| [Production setup](docs/development/production-setup.md) | Supabase, runtime roles, Edge Functions, API/worker, and desktop configuration |
| [Native release matrix](docs/release-matrix.md) | Build targets, checksums, signing state, and testing boundaries |
| [Security boundary](docs/security/tenant-and-storage-boundary.md) | Authentication, tenancy, RLS, private files, and hosted secrets |

## Security and evidence

Do not commit credentials, customer data, or real employee information. Report security concerns through [.github/SECURITY.md](.github/SECURITY.md), not through a public issue containing exploit details.

Every implementation claim must match observable evidence. A compiled package is not automatically an installed or hardware-tested package, a verified schedule is not business approval, and an Actions artifact is not a published release.
