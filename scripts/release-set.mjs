import { createHash } from "node:crypto";
import { readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { readReleaseVersion } from "./release-contract.mjs";
import { verifyManifest } from "./verify-release.mjs";

export const RELEASE_PLATFORMS = [
  { id: "mac-apple-silicon", filename: "ALTO-mac-apple-silicon.dmg", platform: "macos", architecture: "arm64", target: "aarch64-apple-darwin", signing: "ad-hoc", notarization: "not-notarized", host: "darwin", hostArch: "arm64" },
  { id: "windows-x64", filename: "ALTO-windows-x64-setup.exe", platform: "windows", architecture: "x64", target: "x86_64-pc-windows-msvc", signing: "unsigned", notarization: "not-applicable", host: "win32", hostArch: "x64" },
  { id: "mac-intel", filename: "ALTO-mac-intel.dmg", platform: "macos", architecture: "x64", target: "x86_64-apple-darwin", signing: "ad-hoc", notarization: "not-notarized", host: "darwin", hostArch: "x64" },
];

export const RELEASE_FILES = RELEASE_PLATFORMS.flatMap((platform) => [platform.filename, `ALTO-${platform.id}-manifest.json`]).sort();
export const hashBytes = (bytes) => createHash("sha256").update(bytes).digest("hex");

export async function verifyReleaseSet(directory, { version, commit }) {
  const actualFiles = (await readdir(directory)).filter((name) => name !== "SHA256SUMS.txt").sort();
  if (JSON.stringify(actualFiles) !== JSON.stringify(RELEASE_FILES)) {
    throw new Error("Release must contain exactly all three installers and their three platform manifests");
  }
  for (const expected of RELEASE_PLATFORMS) {
    const manifest = await verifyManifest(path.join(directory, `ALTO-${expected.id}-manifest.json`));
    if (manifest.productName !== "ALTO" || manifest.version !== version || manifest.commit !== commit) {
      throw new Error(`${expected.id}: product, version or build commit mismatch`);
    }
    for (const key of ["platform", "architecture", "signing", "notarization"]) {
      if (manifest[key] !== expected[key]) throw new Error(`${expected.id}: unexpected ${key}`);
    }
    if (manifest.rustTarget !== expected.target || manifest.host?.platform !== expected.host || manifest.host?.architecture !== expected.hostArch) {
      throw new Error(`${expected.id}: native build target/host mismatch`);
    }
    if (manifest.artifacts.length !== 1 || manifest.artifacts[0].filename !== expected.filename) {
      throw new Error(`${expected.id}: unexpected installer filename`);
    }
    if (manifest.verification?.nativeBuild !== "passed" || manifest.verification?.manifestVerification !== "passed") {
      throw new Error(`${expected.id}: missing native build evidence`);
    }
  }
  const assets = await Promise.all(RELEASE_FILES.map(async (name) => {
    const bytes = await readFile(path.join(directory, name));
    return { name, size: bytes.length, sha256: hashBytes(bytes) };
  }));
  return assets;
}

export function checksumText(assets) {
  return assets.map((asset) => `${asset.sha256}  ${asset.name}\n`).join("");
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const directory = path.resolve(process.argv[2] || "artifacts/release-set");
  const version = await readReleaseVersion(path.resolve(import.meta.dirname, ".."));
  const assets = await verifyReleaseSet(directory, { version, commit: process.env.RELEASE_COMMIT || process.env.GITHUB_SHA });
  await writeFile(path.join(directory, "SHA256SUMS.txt"), checksumText(assets));
  console.log(`Verified ${assets.length} release files and generated SHA256SUMS.txt`);
}
