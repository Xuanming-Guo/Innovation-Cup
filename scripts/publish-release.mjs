import { readFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { readReleaseVersion, VERSION_PATTERN } from "./release-contract.mjs";
import { checksumText, hashBytes, verifyReleaseSet } from "./release-set.mjs";

export async function publishRelease({ request, repository, tag, commit, assets, loadAsset }) {
  if (!VERSION_PATTERN.test(tag.slice(1)) || !tag.startsWith("v") || !/^[0-9a-f]{40}$/.test(commit)) {
    throw new Error("Publication requires a stable version tag and full commit SHA");
  }
  const base = `/repos/${repository}/releases`;
  const marker = `<!-- alto-release:${commit} -->`;
  let release;
  for (let page = 1; ; page += 1) {
    const releases = await request("GET", `${base}?per_page=100&page=${page}`);
    release = releases.find((item) => item.tag_name === tag);
    if (release || releases.length < 100) break;
  }
  const assertOwnedDraft = (item) => {
    if (!item.draft) throw new Error(`${tag} is already published; its assets will never be replaced`);
    if (item.tag_name !== tag || !item.body?.includes(marker) || item.target_commitish !== commit) {
      throw new Error("Existing draft does not belong to this release commit; refusing to modify it");
    }
    return item;
  };
  if (release) assertOwnedDraft(release);
  else {
    release = await request("POST", base, {
      tag_name: tag,
      target_commitish: commit,
      name: `ALTO ${tag}`,
      draft: true,
      prerelease: false,
      make_latest: "false",
      body: [
        `ALTO ${tag} — Every change, coordinated.`, "",
        "Download the installer for Windows x64, Mac Apple silicon, or Mac Intel below.",
        "Demo release. Windows is unsigned; macOS builds are ad-hoc signed and not notarized.",
        "Your computer may ask you to confirm before opening. Approve only the specific ALTO app; do not disable system protection globally.", "",
        "The builds use authenticated service discovery and operator-provided AI configuration. An internet connection and an available demo service are required.", "",
        "The guided Northstar demo uses a canonical interpretation, planning snapshot and schedule, verified by Z3 and an independent validator. Assistant conversations use the live AI provider.", "",
        "Native CI compiled each target. Installed-app testing is not established by this workflow; macOS builds have not been tested on physical Mac hardware.",
        "Platform manifests record architecture, commit, signing state and build evidence. SHA256SUMS.txt covers all installers and manifests.", "",
        `Source commit: ${commit}`, marker,
      ].join("\n"),
    });
    assertOwnedDraft(release);
  }
  const currentDraft = async () => assertOwnedDraft(await request("GET", `${base}/${release.id}`));
  const remoteAssets = () => request("GET", `${base}/${release.id}/assets?per_page=100`);
  const expectedNames = new Set(assets.map((asset) => asset.name));
  const rejectUnexpected = (remote) => {
    if (remote.length > assets.length || remote.some((item) => !expectedNames.has(item.name))) {
      throw new Error("Draft contains unexpected assets; refusing to publish or delete them");
    }
  };
  const matches = async (remote, local) => {
    if (remote.state !== "uploaded" || remote.size !== local.size) return false;
    if (remote.digest) return remote.digest === `sha256:${local.sha256}`;
    const bytes = await request("GET", `${base}/assets/${remote.id}`, undefined, { binary: true });
    return hashBytes(bytes) === local.sha256;
  };
  let remote = await remoteAssets();
  rejectUnexpected(remote);
  for (const asset of assets) {
    const existing = remote.find((item) => item.name === asset.name);
    if (existing && await matches(existing, asset)) continue;
    await currentDraft();
    if (existing) {
      // Only our unpublished draft may be repaired after an interrupted upload/rebuild.
      await request("DELETE", `${base}/assets/${existing.id}`);
    }
    const draft = await currentDraft();
    const uploadUrl = `${draft.upload_url.split("{")[0]}?name=${encodeURIComponent(asset.name)}`;
    await request("POST", uploadUrl, await loadAsset(asset.name), { upload: true });
  }
  await currentDraft();
  remote = await remoteAssets();
  rejectUnexpected(remote);
  if (remote.length !== assets.length) throw new Error("Draft is missing release assets");
  for (const asset of assets) {
    const found = remote.filter((item) => item.name === asset.name);
    if (found.length !== 1 || !await matches(found[0], asset)) {
      throw new Error(`Uploaded asset verification failed: ${asset.name}`);
    }
  }
  await currentDraft();
  const published = await request("PATCH", `${base}/${release.id}`, { draft: false, make_latest: "true" });
  if (published.draft) throw new Error("Release remained a draft");
  return published;
}

export function githubRequest(token) {
  return async (method, endpoint, body, { binary = false, upload = false } = {}) => {
    const url = new URL(endpoint, "https://api.github.com");
    if (!["api.github.com", "uploads.github.com"].includes(url.hostname) || url.protocol !== "https:") {
      throw new Error("Unexpected GitHub API host");
    }
    const response = await fetch(url, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: binary ? "application/octet-stream" : "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        ...(body !== undefined ? { "Content-Type": upload ? "application/octet-stream" : "application/json" } : {}),
      },
      ...(body !== undefined ? { body: upload ? body : JSON.stringify(body) } : {}),
      signal: AbortSignal.timeout(300_000),
    });
    if (!response.ok) throw new Error(`GitHub ${method} ${url.pathname} returned ${response.status}`);
    if (response.status === 204) return null;
    return binary ? Buffer.from(await response.arrayBuffer()) : response.json();
  };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  if (process.env.GITHUB_EVENT_NAME !== "push" || process.env.GITHUB_REF_TYPE !== "tag") {
    throw new Error("Only a pushed release tag may publish; manual runs produce artifacts only");
  }
  const { GITHUB_TOKEN: token, GITHUB_REPOSITORY: repository, GITHUB_REF_NAME: tag } = process.env;
  if (!token || !/^[\w.-]+\/[\w.-]+$/.test(repository || "")) throw new Error("GitHub token/repository is missing");
  const directory = path.resolve(process.argv[2] || "artifacts/release-set");
  const commit = process.env.RELEASE_COMMIT || process.env.GITHUB_SHA;
  const version = await readReleaseVersion(path.resolve(import.meta.dirname, ".."), tag);
  const assets = await verifyReleaseSet(directory, { version, commit });
  const loadAsset = (name) => readFile(path.join(directory, name));
  const checksums = await loadAsset("SHA256SUMS.txt");
  if (checksums.toString("utf8") !== checksumText(assets)) throw new Error("SHA256SUMS.txt does not match release files");
  assets.push({ name: "SHA256SUMS.txt", size: checksums.length, sha256: hashBytes(checksums) });
  const release = await publishRelease({ request: githubRequest(token), repository, tag, commit, assets, loadAsset });
  console.log(`Published verified release: ${release.html_url}`);
}
