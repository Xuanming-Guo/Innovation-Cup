import { execFileSync } from "node:child_process";
import { appendFile, readFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

export const VERSION_PATTERN = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;

export function validateVersions({ root, desktop, cargo, tauri }, tag) {
  if (!VERSION_PATTERN.test(root)) throw new Error("Release version must be stable MAJOR.MINOR.PATCH");
  for (const [name, version] of Object.entries({ desktop, cargo, tauri })) {
    if (version !== root) throw new Error(`${name} version ${version} does not match root ${root}`);
  }
  if (tag !== undefined && tag !== `v${root}`) {
    throw new Error(`Release tag ${tag} does not match v${root}`);
  }
  return root;
}

export async function readReleaseVersion(repositoryRoot, tag) {
  const json = async (filename) => JSON.parse(await readFile(path.join(repositoryRoot, filename), "utf8"));
  const root = await json("package.json");
  const desktop = await json("apps/desktop/package.json");
  const tauri = await json("apps/desktop/src-tauri/tauri.conf.json");
  const cargo = await readFile(path.join(repositoryRoot, "apps/desktop/src-tauri/Cargo.toml"), "utf8");
  const packageSection = cargo.split(/^\[/m).find((section) => section.startsWith("package]"));
  const cargoVersion = packageSection?.match(/^version\s*=\s*"([^"]+)"/m)?.[1];
  if (tauri.productName !== "ALTO") throw new Error("Native productName must be ALTO");
  return validateVersions({ root: root.version, desktop: desktop.version, cargo: cargoVersion, tauri: tauri.version }, tag);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const repositoryRoot = path.resolve(import.meta.dirname, "..");
  const tagged = process.env.GITHUB_EVENT_NAME === "push" && process.env.GITHUB_REF_TYPE === "tag";
  const version = await readReleaseVersion(repositoryRoot, tagged ? process.env.GITHUB_REF_NAME : undefined);
  const git = (args) => execFileSync("git", args, { cwd: repositoryRoot, encoding: "utf8" }).trim();
  const commit = git(["rev-parse", "HEAD"]);
  if (tagged) {
    if (git(["rev-parse", `${process.env.GITHUB_REF_NAME}^{commit}`]) !== commit) {
      throw new Error("Checked-out commit does not match release tag");
    }
    // main is PR-controlled; allow it to advance while the native jobs run.
    git(["merge-base", "--is-ancestor", commit, "origin/main"]);
  }
  const tracked = git(["ls-files", "apps/desktop/.env*", ".env*"]).split(/\r?\n/).filter(Boolean);
  if (tracked.some((filename) => !filename.endsWith(".example"))) {
    throw new Error("Filled environment files must not be tracked or baked into a release");
  }
  if (process.env.GITHUB_OUTPUT) {
    await appendFile(process.env.GITHUB_OUTPUT, `version=${version}\ncommit=${commit}\n`);
  }
  console.log(`Release contract: ALTO ${version}, commit ${commit}${tagged ? ", reviewed main ancestry" : ", candidate only"}`);
}
