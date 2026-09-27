import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { readReleaseVersion, validateVersions, VERSION_PATTERN } from "./release-contract.mjs";
import { checksumText, hashBytes, RELEASE_PLATFORMS, verifyReleaseSet } from "./release-set.mjs";
import { publishRelease } from "./publish-release.mjs";

const commit = "a".repeat(40);
const versions = { root: "0.1.0", desktop: "0.1.0", cargo: "0.1.0", tauri: "0.1.0" };

test("tag must match every package version and be stable SemVer", async () => {
  assert.equal(validateVersions(versions, "v0.1.0"), "0.1.0");
  for (const key of Object.keys(versions)) {
    assert.throws(() => validateVersions({ ...versions, [key]: "0.2.0" }, "v0.1.0"));
  }
  for (const tag of ["v0.1.1", "v0.1.0-rc.1", "v00.1.0", "v0.1.0+build"]) {
    assert.throws(() => validateVersions(versions, tag));
  }
  assert.match(await readReleaseVersion(path.resolve(import.meta.dirname, "..")), VERSION_PATTERN);
});

async function fixture(t) {
  const directory = await mkdtemp(path.join(os.tmpdir(), "alto-release-test-"));
  t.after(() => rm(directory, { recursive: true, force: true }));
  for (const platform of RELEASE_PLATFORMS) {
    const content = Buffer.from(`fixture bytes for ${platform.id}`);
    await writeFile(path.join(directory, platform.filename), content);
    const manifest = {
      schemaVersion: 1, productName: "ALTO", version: "0.1.0", commit,
      platform: platform.platform, architecture: platform.architecture, rustTarget: platform.target,
      signing: platform.signing, notarization: platform.notarization,
      host: { platform: platform.host, architecture: platform.hostArch },
      verification: { nativeBuild: "passed", manifestVerification: "passed", installedAppSmokeTest: "not-run" },
      artifacts: [{ filename: platform.filename, bytes: content.length, sha256: hashBytes(content) }],
    };
    await writeFile(path.join(directory, `ALTO-${platform.id}-manifest.json`), JSON.stringify(manifest));
  }
  return directory;
}

test("complete set contains all platforms, bound commits, native hosts and hashes", async (t) => {
  const directory = await fixture(t);
  const assets = await verifyReleaseSet(directory, { version: "0.1.0", commit });
  assert.equal(assets.length, 6);
  assert.equal(checksumText(assets).trim().split("\n").length, 6);
  await assert.rejects(verifyReleaseSet(directory, { version: "0.1.0", commit: "b".repeat(40) }), /commit mismatch/);
  await writeFile(path.join(directory, "ALTO-mac-intel.dmg"), "corrupt");
  await assert.rejects(verifyReleaseSet(directory, { version: "0.1.0", commit }), /size mismatch|SHA-256/);
});

test("missing platforms and unexpected files cannot be published", async (t) => {
  const directory = await fixture(t);
  await writeFile(path.join(directory, "unexpected.txt"), "extra");
  await assert.rejects(verifyReleaseSet(directory, { version: "0.1.0", commit }), /exactly all three/);
  await rm(path.join(directory, "unexpected.txt"));
  await rm(path.join(directory, "ALTO-mac-intel.dmg"));
  await assert.rejects(verifyReleaseSet(directory, { version: "0.1.0", commit }), /exactly all three/);
});

test("mislabeled architecture and fabricated installed evidence fail", async (t) => {
  const directory = await fixture(t);
  const filename = path.join(directory, "ALTO-mac-intel-manifest.json");
  const manifest = JSON.parse(await readFile(filename, "utf8"));
  manifest.host.architecture = "arm64";
  await writeFile(filename, JSON.stringify(manifest));
  await assert.rejects(verifyReleaseSet(directory, { version: "0.1.0", commit }), /host mismatch/);
  manifest.host.architecture = "x64";
  manifest.verification.installedAppSmokeTest = "passed";
  await writeFile(filename, JSON.stringify(manifest));
  await assert.rejects(verifyReleaseSet(directory, { version: "0.1.0", commit }), /must not be fabricated/);
});

function mockGithub({ existing, corruptUpload = false, publishDuringUpload = false } = {}) {
  let release = existing;
  let remote = existing?.assets || [];
  const mutations = [];
  const request = async (method, endpoint, body) => {
    if (method !== "GET") mutations.push({ method, endpoint, body });
    if (method === "GET" && endpoint.includes("/releases?")) return release ? [release] : [];
    if (method === "POST" && endpoint.endsWith("/releases")) {
      release = { ...body, id: 1, upload_url: "https://uploads.github.com/repos/owner/repo/releases/1/assets{?name,label}" };
      return release;
    }
    if (method === "GET" && endpoint.endsWith("/releases/1")) return release;
    if (method === "GET" && endpoint.includes("/assets?")) return remote;
    if (method === "DELETE") {
      remote = remote.filter((asset) => !endpoint.endsWith(`/${asset.id}`));
      return null;
    }
    if (method === "POST" && endpoint.startsWith("https://uploads.github.com/")) {
      remote.push({ id: remote.length + 10, name: new URL(endpoint).searchParams.get("name"), state: "uploaded", size: body.length, digest: `sha256:${corruptUpload ? "0".repeat(64) : hashBytes(body)}` });
      if (publishDuringUpload) release = { ...release, draft: false };
      return remote.at(-1);
    }
    if (method === "PATCH") {
      release = { ...release, ...body };
      return release;
    }
    throw new Error(`Unexpected mocked request ${method} ${endpoint}`);
  };
  return { request, mutations };
}

const fixtureBytes = Buffer.from("release bytes");
const asset = { name: "ALTO-windows-x64-setup.exe", size: fixtureBytes.length, sha256: hashBytes(fixtureBytes) };
const publishOptions = { repository: "owner/repo", tag: "v0.1.0", commit, assets: [asset], loadAsset: async () => fixtureBytes };
const ownedDraft = { id: 1, tag_name: "v0.1.0", target_commitish: commit, draft: true, body: `<!-- alto-release:${commit} -->`, upload_url: "https://uploads.github.com/repos/owner/repo/releases/1/assets{?name,label}" };

test("publish happens only after draft upload and remote digest verification", async () => {
  const api = mockGithub();
  const result = await publishRelease({ ...publishOptions, request: api.request });
  assert.equal(result.draft, false);
  assert.equal(api.mutations[0].body.draft, true);
  assert.equal(api.mutations.at(-1).method, "PATCH");
  assert.deepEqual(api.mutations.at(-1).body, { draft: false, make_latest: "true" });
});

test("published tags and unrelated drafts cannot be mutated", async () => {
  for (const existing of [{ ...ownedDraft, draft: false }, { ...ownedDraft, body: "manual draft" }]) {
    const api = mockGithub({ existing });
    await assert.rejects(publishRelease({ ...publishOptions, request: api.request }), /already published|does not belong/);
    assert.equal(api.mutations.length, 0);
  }
});

test("rerun resumes verified draft assets and repairs only incomplete draft uploads", async () => {
  const complete = { id: 2, name: asset.name, state: "uploaded", size: asset.size, digest: `sha256:${asset.sha256}` };
  const resumed = mockGithub({ existing: { ...ownedDraft, assets: [complete] } });
  await publishRelease({ ...publishOptions, request: resumed.request });
  assert.deepEqual(resumed.mutations.map((item) => item.method), ["PATCH"]);
  const interrupted = mockGithub({ existing: { ...ownedDraft, assets: [{ ...complete, state: "starter" }] } });
  await publishRelease({ ...publishOptions, request: interrupted.request });
  assert.deepEqual(interrupted.mutations.map((item) => item.method), ["DELETE", "POST", "PATCH"]);
});

test("corruption or publication during upload prevents further writes", async () => {
  for (const flags of [{ corruptUpload: true }, { publishDuringUpload: true }]) {
    const api = mockGithub(flags);
    await assert.rejects(publishRelease({ ...publishOptions, request: api.request }), /verification failed|already published/);
    assert.ok(!api.mutations.some((item) => item.method === "PATCH"));
  }
});
