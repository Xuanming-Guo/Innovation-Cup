import { spawnSync } from "node:child_process";
import process from "node:process";

const strict = process.argv.includes("--strict");
const isWindows = process.platform === "win32";

const commands = [
  ["Node.js", "node", ["--version"], true],
  ["npm", isWindows ? "npm.cmd" : "npm", ["--version"], true],
  ["Rust", "rustc", ["--version"], true],
  ["Cargo", "cargo", ["--version"], true],
  ["Python", "python", ["--version"], true],
  ["uv", "uv", ["--version"], true],
  ["Supabase CLI", isWindows ? "supabase.exe" : "supabase", ["--version"], false],
];

const environment = [
  ["VITE_API_ORIGIN", false],
  ["VITE_SUPABASE_URL", false],
  ["VITE_SUPABASE_PUBLISHABLE_KEY", false],
  ["COORDINATION_DATABASE_URL", true],
  ["COORDINATION_GEMINI_API_KEY", true],
];

let missingRequired = 0;

console.log("Coordination Engine developer doctor");
console.log(`platform: ${process.platform} ${process.arch}`);
console.log("\nToolchain");

for (const [label, command, args, required] of commands) {
  const executable = isWindows && command.endsWith(".cmd")
    ? (process.env.ComSpec ?? "cmd.exe")
    : command;
  const executableArgs = isWindows && command.endsWith(".cmd")
    ? ["/d", "/s", "/c", [command, ...args].join(" ")]
    : args;
  const result = spawnSync(executable, executableArgs, { encoding: "utf8", windowsHide: true });
  const available = result.status === 0;
  if (!available && required) missingRequired += 1;
  const version = available ? (result.stdout || result.stderr).trim() : "not found";
  console.log(`- ${label}: ${available ? version : "NOT AVAILABLE"}${required ? "" : " (optional)"}`);
}

console.log("\nConfiguration presence (values are never printed)");
for (const [name, secret] of environment) {
  const present = Boolean(process.env[name]?.trim());
  console.log(`- ${name}: ${present ? "set" : "not set"}${secret ? " [server secret]" : ""}`);
}

if (strict && missingRequired > 0) {
  console.error(`\n${missingRequired} required tool(s) are unavailable.`);
  process.exitCode = 1;
} else {
  console.log("\nDoctor completed. The Gemini value is an optional local/test fallback; production companies configure BYOK through the authenticated application.");
}
