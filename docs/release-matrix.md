# Native release matrix

## Current automation state

The **Native release artifacts** workflow builds all three targets on architecture-matching
GitHub-hosted runners with `VITE_HACKATHON_DEMO=true`, public Supabase discovery configuration and
the ALTO product name. Manual runs retain candidate artifacts for 30 days. Stable SemVer tag runs
add a separate publication job with `contents: write`; build jobs retain read-only permissions.

The workflow is prepared locally for the release PR. Implementation is not evidence of a completed
native CI run or public release. The landing page's `/releases/latest/download/...` URLs become
available once the tagged workflow successfully publishes the complete asset set.

| Public build | Native runner | Rust target | Package | Signature state | Installed smoke state |
|---|---|---|---|---|---|
| Windows 11 x64 | `windows-2025` x64 | `x86_64-pc-windows-msvc` | NSIS `.exe` | Unsigned | Required before claiming installed support |
| macOS 13+ Apple silicon | `macos-15` arm64 | `aarch64-apple-darwin` | `.app` and `.dmg` | Ad-hoc; not notarized | Not run; no Mac test hardware is available |
| macOS 13+ Intel | `macos-15-intel` x64 | `x86_64-apple-darwin` | `.app` and `.dmg` | Ad-hoc; not notarized | Not run; no Mac test hardware is available |

## Public `v0.1.0` contract

The tagged workflow publishes these exact installer names:

- `ALTO-mac-apple-silicon.dmg`
- `ALTO-windows-x64-setup.exe`
- `ALTO-mac-intel.dmg`

Every package must use version `0.1.0` consistently across the root package, desktop package,
Cargo package and Tauri configuration. The `v0.1.0` tag must point to the reviewed release commit
on `main`.

The workflow fixes judge mode, discovery mode and product name, and requires these public values:

- `VITE_HACKATHON_DEMO=true`
- `VITE_API_MODE=supabase-discovery`
- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_PUBLISHABLE_KEY`
- `VITE_DEFAULT_COMPANY_ID`
- `VITE_PRODUCT_NAME=ALTO`

These are public client configuration, not Actions secrets. The validator must reject a missing
value, a malformed company UUID, a non-HTTPS Supabase URL or a privileged-looking key. Database
passwords, runtime DSNs, Supabase secret/service-role keys, Vault contents and Google credentials
must never be copied into the build environment or installer.

Manual workflow dispatch remains a candidate-build path and uploads temporary Actions artifacts
only. A reviewed SemVer tag must build all three platforms before publishing anything, normalize
the files to the stable public names, generate a platform manifest for each package and create one
top-level `SHA256SUMS.txt`. Each manifest records the commit, version, platform, architecture,
target, checksum, signature/notarization state and installed-test state.

Each native candidate contains its installer and `ALTO-<platform>-manifest.json`. The combined
`verified-release-set` artifact contains all six files and `SHA256SUMS.txt`. The tagged workflow
then creates a draft release, uploads and verifies the complete asset set, and
only then publishes it as the latest release. It must fail if a published release already exists
for the tag and must never replace assets on a published tag. A code correction requires a new
patch version; a transient job failure may rerun only the unchanged tag workflow.

The landing page follows the latest published release automatically. Publishing a complete newer
release with the same stable filenames updates the three download links without a Pages rebuild.
The **Release notes & checksums** link opens the release page containing the release description,
platform manifests and `SHA256SUMS.txt`.

## Signing and evidence boundary

Apple Developer ID signing/notarization and Windows Authenticode signing require founder-owned
certificates and CI secrets that are not present. The hackathon packages therefore remain Windows
unsigned and macOS ad-hoc signed/not notarized. Opening instructions may explain how to approve the
specific downloaded application, but must never tell users to disable operating-system protection
globally.

A successful compile, package inspection or checksum does not establish installed behavior. Do not
change an `installedAppSmokeTest` field from `not-run` without recording the real machine, OS,
architecture and observed result. Native macOS CI can establish architecture and package validity;
it cannot be described as physical-Mac hardware testing.

## Historical build evidence

Workflow [run 1](https://github.com/Xuanming-Guo/Innovation-Cup/actions/runs/36256960403)
completed for commit `ec45bcbc35a5b912b0e27178f48f2e29a1df46f0` on 26 September
2026. It uploaded `coordination-engine-windows-x64`, `coordination-engine-macos-arm64` and
`coordination-engine-macos-x64`, each with a verified `release-manifest.json`. That run predates
the locked judge configuration and stable public filenames. It is historical compilation evidence,
not the public ALTO `v0.1.0` release or installed-platform evidence.
