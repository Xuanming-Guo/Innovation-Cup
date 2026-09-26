import { delimiter, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import process from "node:process";

const repositoryRoot = resolve(import.meta.dirname, "..");
const projectRoot = resolve(repositoryRoot, "services", "backend");
const sourceRoot = resolve(projectRoot, "src");
const [command, ...args] = process.argv.slice(2);

if (!command) {
  console.error("Usage: node scripts/backend.mjs <command> [...args]");
  process.exit(2);
}

const pythonPath = process.env.PYTHONPATH
  ? `${sourceRoot}${delimiter}${process.env.PYTHONPATH}`
  : sourceRoot;
const uvCommand = process.platform === "win32" ? "uv.exe" : "uv";
const result = spawnSync(uvCommand, ["run", "--project", projectRoot, command, ...args], {
  cwd: repositoryRoot,
  env: {
    ...process.env,
    PYTHONPATH: pythonPath,
    UV_LINK_MODE: process.env.UV_LINK_MODE ?? "copy",
  },
  stdio: "inherit",
  windowsHide: true,
});

if (result.error) {
  console.error(result.error.message);
  process.exit(1);
}

process.exit(result.status ?? 1);
