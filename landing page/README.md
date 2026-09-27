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

## Download contract

The page expects the latest public GitHub Release to contain these exact filenames:

- `ALTO-mac-apple-silicon.dmg`
- `ALTO-windows-x64-setup.exe`
- `ALTO-mac-intel.dmg`

Until those assets exist on a published release, the corresponding links will return GitHub's
not-found response. Release signing, notarization, checksums, and installed-app verification
remain governed by `../docs/release-matrix.md`.

