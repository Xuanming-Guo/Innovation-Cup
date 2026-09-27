# ALTO download page

The compact static site deployed at [xuanming-guo.github.io/Innovation-Cup](https://xuanming-guo.github.io/Innovation-Cup/) provides the ALTO demo video, Data Room, and permanent download links for the three desktop builds.

Downloads remain the page’s primary action. The page contains no backend logic and does not decide which Mac architecture a visitor uses.

## Local development

From this directory:

```powershell
npm ci
npm test
npm run dev
```

Create the production output with:

```powershell
npm run build
```

Vite writes the static site to `dist/` and uses relative asset paths so the output works under the GitHub Pages repository path. `node_modules/` and `dist/` are generated locally and must not be committed.

## Demo video and Data Room

The embedded video is stored at:

```text
public/alto-demo.mp4
```

Use MP4 with H.264 video and AAC audio. Keep it below GitHub’s 100 MB per-file limit and preferably below 50 MB for page performance. Vite copies it to `dist/alto-demo.mp4`, which is the deployed player and direct-file fallback path.

The supporting Data Room card opens this public Google Drive folder in a new tab:

<https://drive.google.com/drive/folders/1H0xRJpa73xkRBztrmQzJI5bub6HVkQe3?usp=sharing>

## Permanent download contract

The page links to `/releases/latest/download/<asset-name>` for these exact GitHub Release assets:

- `ALTO-mac-apple-silicon.dmg`
- `ALTO-windows-x64-setup.exe`
- `ALTO-mac-intel.dmg`

The URLs follow the repository’s latest published release. Publishing a newer release with the same filenames updates all three downloads automatically; rebuilding or redeploying the landing page is unnecessary.

Temporary GitHub Actions artifacts do not satisfy these URLs. Until a published GitHub Release contains the exact assets, the corresponding download links return GitHub’s not-found page.

The **Release notes & checksums** link opens the latest GitHub Release page. Once a release is published, that page contains its release description, platform manifests, and `SHA256SUMS.txt`; it is not an automatic updater or a link to temporary Actions artifacts.

## Distribution notice

This is a hackathon demo release. The Windows installer is unsigned. The macOS builds are ad-hoc signed and not notarized, so operating systems may require a user to confirm the specific app before opening it. The page must never tell visitors to disable Windows security or macOS Gatekeeper globally.

Signing, checksum generation, asset verification, and installed-app evidence are governed by [`../docs/release-matrix.md`](../docs/release-matrix.md).

## Runtime relationship

The landing page only distributes static installers. A downloaded ALTO app authenticates with Supabase, resolves the current API endpoint through authenticated service discovery, and connects to the configured ALTO backend. Endpoint changes do not require the landing page or installers to be rebuilt.
