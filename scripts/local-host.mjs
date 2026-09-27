import { randomUUID } from "node:crypto";
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const HOST_DIRECTORY = resolve(ROOT, "deploy", "local-host");
const HOST_ENV_PATH = resolve(HOST_DIRECTORY, ".env");
const RUNTIME_ENV_PATH = resolve(HOST_DIRECTORY, ".env.runtime");
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const REQUIRED_HOST_VALUES = [
  "COORDINATION_SUPABASE_URL",
  "COORDINATION_API_DATABASE_URL",
  "COORDINATION_WORKER_DATABASE_URL",
  "COORDINATION_HOST_COMPANY_ID",
  "COORDINATION_HOST_ACTOR_ID",
];

export function parseEnvironmentFile(contents) {
  const values = {};
  for (const rawLine of contents.split(/\r?\n/u)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const separator = line.indexOf("=");
    if (separator <= 0) throw new Error("Host environment contains an invalid line");
    const name = line.slice(0, separator).trim();
    const value = line.slice(separator + 1).trim();
    values[name] = value;
  }
  return values;
}

export function validateHostEnvironment(values) {
  for (const name of REQUIRED_HOST_VALUES) {
    if (!values[name]?.trim()) throw new Error(`${name} is required in deploy/local-host/.env`);
  }
  const supabaseUrl = new URL(values.COORDINATION_SUPABASE_URL);
  if (supabaseUrl.protocol !== "https:" || supabaseUrl.pathname !== "/") {
    throw new Error("COORDINATION_SUPABASE_URL must be one HTTPS origin");
  }
  if (!UUID_PATTERN.test(values.COORDINATION_HOST_COMPANY_ID)) {
    throw new Error("COORDINATION_HOST_COMPANY_ID must be a UUID");
  }
  if (!UUID_PATTERN.test(values.COORDINATION_HOST_ACTOR_ID)) {
    throw new Error("COORDINATION_HOST_ACTOR_ID must be a UUID");
  }
  const apiDatabase = new URL(values.COORDINATION_API_DATABASE_URL);
  const workerDatabase = new URL(values.COORDINATION_WORKER_DATABASE_URL);
  if (!apiDatabase.protocol.startsWith("postgres") || !workerDatabase.protocol.startsWith("postgres")) {
    throw new Error("Both runtime database values must be PostgreSQL URLs");
  }
  const projectRef = supabaseUrl.hostname.split(".", 1)[0];
  const expectedUsername = (database, role) =>
    database.hostname.endsWith(".pooler.supabase.com") ? `${role}.${projectRef}` : role;
  if (decodeURIComponent(apiDatabase.username) !== expectedUsername(apiDatabase, "coordination_api_prod")) {
    throw new Error(
      `The API database URL must use ${expectedUsername(apiDatabase, "coordination_api_prod")}`,
    );
  }
  if (decodeURIComponent(workerDatabase.username) !== expectedUsername(workerDatabase, "coordination_worker_prod")) {
    throw new Error(
      `The worker database URL must use ${expectedUsername(workerDatabase, "coordination_worker_prod")}`,
    );
  }
  if (values.COORDINATION_API_DATABASE_URL === values.COORDINATION_WORKER_DATABASE_URL) {
    throw new Error("API and worker must use different database credentials");
  }
  return values;
}

export function runtimeEnvironment(existingContents, buildCommit) {
  if (!/^[0-9a-f]{40}$/u.test(buildCommit)) {
    throw new Error("The host must start from a committed Git revision");
  }
  const existing = parseEnvironmentFile(existingContents);
  const instanceId = UUID_PATTERN.test(existing.COORDINATION_HOST_INSTANCE_ID ?? "")
    ? existing.COORDINATION_HOST_INSTANCE_ID
    : randomUUID();
  return [
    `COORDINATION_BUILD_COMMIT=${buildCommit}`,
    `COORDINATION_HOST_INSTANCE_ID=${instanceId}`,
    "",
  ].join("\n");
}

function run(command, args, { capture = false, allowFailure = false, includeStderr = false } = {}) {
  const result = spawnSync(command, args, {
    cwd: HOST_DIRECTORY,
    encoding: "utf8",
    shell: false,
    stdio: capture ? "pipe" : "inherit",
  });
  if (result.error) throw result.error;
  if (result.status !== 0 && !allowFailure) {
    throw new Error(`${command} exited with status ${result.status}`);
  }
  return capture ? `${result.stdout}${includeStderr ? result.stderr : ""}`.trim() : "";
}

function dockerCompose(arguments_, options, runner = run) {
  return runner("docker", [
    "compose",
    "--env-file",
    ".env",
    "--env-file",
    ".env.runtime",
    "-f",
    "compose.yaml",
    ...arguments_,
  ], options);
}

export function hasExpiredQuickTunnelSession(logs) {
  const events = [];
  for (const line of logs.split(/\r?\n/u)) {
    if (!/Unauthorized:\s*Tunnel not found/iu.test(line)
      && !/Registered tunnel connection/iu.test(line)) continue;
    events.push({
      timestamp: line.match(/^\d{4}-\d{2}-\d{2}T\S+/u)?.[0] ?? null,
      expired: /Unauthorized:\s*Tunnel not found/iu.test(line),
    });
  }
  // Docker may place stdout and stderr in separate captured buffers. Its timestamps
  // preserve chronology when those buffers are combined for inspection.
  if (events.every((event) => event.timestamp !== null)) {
    events.sort((left, right) => left.timestamp.localeCompare(right.timestamp));
  }
  return events.at(-1)?.expired ?? false;
}

function existingTunnelSessionExpired(runner) {
  try {
    const containerId = dockerCompose(["ps", "-a", "-q", "tunnel"], { capture: true }, runner);
    if (!/^[a-f0-9]{12,64}$/u.test(containerId)) return false;
    const state = JSON.parse(runner("docker", [
      "inspect", "--format",
      '{"running":{{.State.Running}},"startedAt":{{json .State.StartedAt}}}',
      containerId,
    ], { capture: true }));
    if (state.running !== true || typeof state.startedAt !== "string"
      || !/^\d{4}-\d{2}-\d{2}T[\d:.]+Z$/u.test(state.startedAt)) return false;
    const logs = runner("docker", [
      "logs", "--timestamps", "--since", state.startedAt, "--tail", "200", containerId,
    ], { capture: true, includeStderr: true });
    return hasExpiredQuickTunnelSession(logs);
  } catch {
    // Inspection failure is not evidence that a tunnel should be rotated. The
    // normal startup path still reports Docker/configuration failures below.
    return false;
  }
}

function currentRegisteredOrigin(runner) {
  const output = dockerCompose([
    "exec", "-T", "registrar", "python", "-m", "coordination.hosting.registrar", "--status",
  ], { capture: true }, runner);
  let status;
  try {
    status = JSON.parse(output);
  } catch {
    throw new Error("The registrar did not return valid current readiness status");
  }
  if (status?.ready !== true || typeof status.api_origin !== "string"
    || !/^https:\/\/[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.trycloudflare\.com$/u.test(status.api_origin)) {
    throw new Error("The public endpoint is not currently registered and ready");
  }
  return status.api_origin;
}

export function startHostServices({ runner = run, log = console.log } = {}) {
  let recovered = false;
  function recoverExpiredTunnel() {
    if (recovered || !existingTunnelSessionExpired(runner)) return false;
    recovered = true;
    log("Cloudflare rejected the existing Quick Tunnel session. Recreating only the tunnel once; API, worker and stored data are retained.");
    dockerCompose(["up", "-d", "--no-deps", "--force-recreate", "tunnel"], undefined, runner);
    return true;
  }
  try {
    recoverExpiredTunnel();
    try {
      dockerCompose(["up", "-d", "--build", "--wait", "--wait-timeout", "300"], undefined, runner);
      return currentRegisteredOrigin(runner);
    } catch (error) {
      if (!recoverExpiredTunnel()) throw error;
      dockerCompose(["up", "-d", "--wait", "--wait-timeout", "300"], undefined, runner);
      return currentRegisteredOrigin(runner);
    }
  } catch (error) {
    dockerCompose([
      "logs", "--tail", "100", "api", "worker", "tunnel", "registrar",
    ], { allowFailure: true }, runner);
    if (recovered) {
      throw new Error("Host startup failed after one Quick Tunnel recovery attempt. Check the readiness diagnostics above; no further automatic restart was performed.", { cause: error });
    }
    throw error;
  }
}

function ensureHostFiles() {
  if (!existsSync(HOST_ENV_PATH)) {
    throw new Error("Copy deploy/local-host/.env.example to deploy/local-host/.env and fill it first");
  }
  validateHostEnvironment(parseEnvironmentFile(readFileSync(HOST_ENV_PATH, "utf8")));
}

function start() {
  ensureHostFiles();
  run("docker", ["version"], { capture: true });
  run("docker", ["compose", "version"], { capture: true });
  const buildCommit = run("git", ["rev-parse", "HEAD"], { capture: true });
  const existingRuntime = existsSync(RUNTIME_ENV_PATH)
    ? readFileSync(RUNTIME_ENV_PATH, "utf8")
    : "";
  writeFileSync(RUNTIME_ENV_PATH, runtimeEnvironment(existingRuntime, buildCommit), {
    encoding: "utf8",
    mode: 0o600,
  });
  const origin = startHostServices();
  console.log(`\nCoordination Engine host is online at ${origin}.`);
  console.log("Keep this laptop awake, online, and running Docker Desktop.");
}

function stop() {
  ensureHostFiles();
  dockerCompose(["down", "--timeout", "30"]);
  console.log("Coordination Engine host is offline. Its discovery lease was released or will expire shortly.");
}

function status() {
  ensureHostFiles();
  dockerCompose(["ps"]);
  run("docker", [
    "compose", "--env-file", ".env", "--env-file", ".env.runtime",
    "-f", "compose.yaml", "logs", "--no-color", "--tail", "10", "registrar",
  ], { allowFailure: true });
}

function main() {
  const action = process.argv[2];
  if (action === "start") start();
  else if (action === "stop") stop();
  else if (action === "status") status();
  else throw new Error("Usage: node scripts/local-host.mjs <start|status|stop>");
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    main();
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  }
}
