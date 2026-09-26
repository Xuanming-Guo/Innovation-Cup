# Native release matrix

The release workflow builds on architecture-matching GitHub-hosted runners and uploads artifacts
for 30 days. It does not create a public GitHub Release automatically.

| Artifact | Native runner | Rust target | Package | Signature state | Installed smoke state |
|---|---|---|---|---|---|
| Windows 11 x64 | `windows-2025` x64 | `x86_64-pc-windows-msvc` | NSIS `-setup.exe` | Unsigned | Not run by build CI |
| macOS 13+ Apple Silicon | `macos-15` arm64 | `aarch64-apple-darwin` | `.app` and `.dmg` | Ad-hoc, not notarised | Not run by build CI |
| macOS 13+ Intel | `macos-15-intel` x64 | `x86_64-apple-darwin` | `.app` and `.dmg` | Ad-hoc, not notarised | Not run by build CI |

Each uploaded artifact contains its distributable, SHA-256 checksum in
`release-manifest.json`, full build commit, toolchain versions and explicit signing/notarisation
state. The Mac download is a DMG, not an EXE. Windows and Mac artifacts are separate native
binaries.

Run **Native release artifacts** manually from GitHub Actions after merging a reviewed release
commit, or push a reviewed SemVer tag such as `v0.1.0`. Download all three Action artifacts and
run:

```powershell
npm.cmd run release:check
```

against an `artifacts/release/` tree containing the downloaded manifest directories. Then perform
the connected cross-platform smoke procedure in
[production and hosted-demo setup](development/production-setup.md). Do not change
`installedAppSmokeTest` from `not-run` without recording real machine/OS evidence.

Before compilation, the workflow requires the repository Actions variables `VITE_API_MODE`,
`VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY` and `VITE_DEFAULT_COMPANY_ID`. The selected
laptop-host build uses `VITE_API_MODE=supabase-discovery` and omits `VITE_API_ORIGIN`; a static
deployment must provide a canonical HTTPS origin. The validator accepts only an
`sb_publishable_...` client key and a UUID. These are public build inputs, not Actions secrets. A
missing or privileged-looking key fails the job rather than producing an installer that asks
employees to configure deployment coordinates.

Apple Developer ID signing/notarisation and Windows Authenticode signing need founder-owned
certificates and CI secrets that are not present in the repository. These artifacts are suitable
for controlled internal/demo distribution; they are not represented as frictionless public-store
releases. Do not tell users to disable operating-system protections globally.

## Latest build evidence

Workflow [run 1](https://github.com/Xuanming-Guo/Innovation-Cup/actions/runs/36256960403)
completed successfully for commit `ec45bcbc35a5b912b0e27178f48f2e29a1df46f0` on 26 September
2026. It uploaded `coordination-engine-windows-x64`, `coordination-engine-macos-arm64` and
`coordination-engine-macos-x64`, each with a verified `release-manifest.json`. GitHub retains this
manual-run artifact set until 26 October 2026. That run predates required baked configuration, so
it is generic and is not the final configured distribution. Compilation and upload passed;
installed-app and connected cross-platform smoke tests remain not run.
