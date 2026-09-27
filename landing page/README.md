# ALTO download page

A self-contained static landing page for the three ALTO desktop builds.

## Local use

```powershell
npm install
npm test
npm run dev
```

Create the deployable static output with:

```powershell
npm run build
```

Publish the contents of `dist/` to the static host. The Vite build uses relative asset paths,
so it works at the root of a domain or under a GitHub Pages repository path.

## Demo video

Place the finished demo at `public/alto-demo.mp4`. Use an H.264 MP4 with AAC audio and keep
the file below GitHub's 100 MB per-file limit (ideally below 50 MB for page performance). Vite
copies the file to `dist/alto-demo.mp4`, which is the stable path used by the embedded player.

## Download contract

The page expects the latest public GitHub Release to contain these exact filenames:

- `ALTO-mac-apple-silicon.dmg`
- `ALTO-windows-x64-setup.exe`
- `ALTO-mac-intel.dmg`

Until those assets exist on a published release, the corresponding links will return GitHub's
not-found response. Release signing, notarization, checksums, and installed-app verification
remain governed by `../docs/release-matrix.md`.
