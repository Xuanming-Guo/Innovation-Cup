import { createHash } from "node:crypto";
import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";

async function hashFile(filename) {
  const bytes = await readFile(filename);
  return createHash("sha256").update(bytes).digest("hex");
}

async function findManifests(target) {
  const metadata = await stat(target);
  if (metadata.isFile()) return [target];
  const entries = await readdir(target, { withFileTypes: true });
  const manifests = [];
  for (const entry of entries) {
    const itemPath = path.join(target, entry.name);
    if (entry.isDirectory()) manifests.push(...await findManifests(itemPath));
    else if (entry.name === "release-manifest.json") manifests.push(itemPath);
  }
  return manifests;
}

const target = process.argv[2];
if (!target) throw new Error("Usage: node scripts/verify-release.mjs <manifest-or-directory>");
const manifests = await findManifests(path.resolve(target));
if (manifests.length === 0) throw new Error("No release-manifest.json files found");

for (const manifestFilename of manifests) {
  const manifest = JSON.parse(await readFile(manifestFilename, "utf8"));
  if (manifest.schemaVersion !== 1) throw new Error(`${manifestFilename}: unsupported schema version`);
  if (!/^[0-9a-f]{40}$/i.test(manifest.commit)) throw new Error(`${manifestFilename}: invalid commit`);
  if (!Array.isArray(manifest.artifacts) || manifest.artifacts.length === 0) {
    throw new Error(`${manifestFilename}: no artifacts`);
  }
  if (manifest.verification?.installedAppSmokeTest !== "not-run") {
    throw new Error(`${manifestFilename}: installed smoke evidence must not be fabricated by build CI`);
  }

  const manifestDirectory = path.dirname(manifestFilename);
  for (const artifact of manifest.artifacts) {
    const artifactFilename = path.resolve(manifestDirectory, artifact.filename);
    if (!artifactFilename.startsWith(`${manifestDirectory}${path.sep}`)) {
      throw new Error(`${manifestFilename}: artifact escapes manifest directory`);
    }
    const metadata = await stat(artifactFilename);
    if (metadata.size !== artifact.bytes) throw new Error(`${artifactFilename}: size mismatch`);
    if (await hashFile(artifactFilename) !== artifact.sha256) {
      throw new Error(`${artifactFilename}: SHA-256 mismatch`);
    }
  }
  console.log(`Verified ${manifestFilename}`);
}
