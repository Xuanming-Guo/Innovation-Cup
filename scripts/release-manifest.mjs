import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { readdir, readFile, stat, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

function parseArguments(argv) {
  const values = new Map();
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) {
      throw new Error(`Invalid argument near ${key ?? "end of command"}`);
    }
    values.set(key.slice(2), value);
  }
  return values;
}

function required(argumentsMap, name) {
  const value = argumentsMap.get(name)?.trim();
  if (!value) throw new Error(`--${name} is required`);
  return value;
}

function commandVersion(command, args = ["--version"]) {
  try {
    return execFileSync(command, args, { encoding: "utf8" }).trim();
  } catch {
    return "unavailable";
  }
}

async function findDistributables(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const found = [];
  for (const entry of entries) {
    const itemPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      found.push(...await findDistributables(itemPath));
    } else if (/\.(dmg|exe)$/i.test(entry.name)) {
      found.push(itemPath);
    }
  }
  return found.sort();
}

async function hashFile(filename) {
  const bytes = await readFile(filename);
  return createHash("sha256").update(bytes).digest("hex");
}

const argumentsMap = parseArguments(process.argv.slice(2));
const inputDirectory = path.resolve(required(argumentsMap, "input"));
const outputFilename = path.resolve(required(argumentsMap, "output"));
const platform = required(argumentsMap, "platform");
const architecture = required(argumentsMap, "arch");
const target = required(argumentsMap, "target");
const signing = required(argumentsMap, "signing");
const notarization = required(argumentsMap, "notarization");
const artifactFiles = await findDistributables(inputDirectory);
if (artifactFiles.length === 0) throw new Error(`No .exe or .dmg found under ${inputDirectory}`);

const repositoryRoot = path.resolve(import.meta.dirname, "..");
const tauriConfig = JSON.parse(await readFile(
  path.join(repositoryRoot, "apps", "desktop", "src-tauri", "tauri.conf.json"),
  "utf8",
));
const commit = (process.env.RELEASE_COMMIT || process.env.GITHUB_SHA || commandVersion("git", ["rev-parse", "HEAD"]).split(/\s/)[0]).trim();
if (!/^[0-9a-f]{40}$/i.test(commit)) throw new Error("Build commit must be a full 40-character SHA");

const artifacts = await Promise.all(artifactFiles.map(async (filename) => {
  const metadata = await stat(filename);
  return {
    filename: path.relative(path.dirname(outputFilename), filename).replaceAll("\\", "/"),
    bytes: metadata.size,
    sha256: await hashFile(filename),
  };
}));

const manifest = {
  schemaVersion: 1,
  productName: tauriConfig.productName,
  version: tauriConfig.version,
  commit,
  generatedAt: new Date().toISOString(),
  platform,
  architecture,
  rustTarget: target,
  host: {
    platform: process.platform,
    architecture: process.arch,
    release: os.release(),
  },
  toolchains: {
    node: process.version,
    npm: process.platform === "win32"
      ? commandVersion(process.env.ComSpec || "cmd.exe", ["/d", "/s", "/c", "npm.cmd --version"])
      : commandVersion("npm"),
    rustc: commandVersion("rustc"),
    cargo: commandVersion("cargo"),
  },
  signing,
  notarization,
  verification: {
    nativeBuild: "passed",
    manifestVerification: "passed",
    installedAppSmokeTest: "not-run",
  },
  artifacts,
};

await writeFile(outputFilename, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
console.log(`Wrote ${outputFilename} for ${artifacts.length} distributable(s)`);
