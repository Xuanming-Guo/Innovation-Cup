import assert from "node:assert/strict";
import test from "node:test";

import {
  hasExpiredQuickTunnelSession,
  parseEnvironmentFile,
  runtimeEnvironment,
  startHostServices,
  validateHostEnvironment,
} from "./local-host.mjs";

const valid = {
  COORDINATION_SUPABASE_URL: "https://project.supabase.co",
  COORDINATION_API_DATABASE_URL:
    "postgresql://coordination_api_prod:password@pooler.example.com:5432/postgres?sslmode=require",
  COORDINATION_WORKER_DATABASE_URL:
    "postgresql://coordination_worker_prod:password@pooler.example.com:5432/postgres?sslmode=require",
  COORDINATION_HOST_COMPANY_ID: "11111111-1111-4111-8111-111111111111",
  COORDINATION_HOST_ACTOR_ID: "99999999-9999-4999-8999-999999999999",
};

test("parses host values without treating encoded URL characters as comments", () => {
  assert.deepEqual(parseEnvironmentFile("# comment\nVALUE=postgresql://user:p%23ss@host/db\n"), {
    VALUE: "postgresql://user:p%23ss@host/db",
  });
});

test("accepts separate least-privileged runtime database identities", () => {
  assert.equal(validateHostEnvironment(valid), valid);
});

test("accepts project-qualified custom roles for the Supabase shared pooler", () => {
  const sharedPooler = {
    ...valid,
    COORDINATION_API_DATABASE_URL:
      "postgresql://coordination_api_prod.project:password@aws-0-us-west-2.pooler.supabase.com:5432/postgres?sslmode=require",
    COORDINATION_WORKER_DATABASE_URL:
      "postgresql://coordination_worker_prod.project:password@aws-0-us-west-2.pooler.supabase.com:5432/postgres?sslmode=require",
  };

  assert.equal(validateHostEnvironment(sharedPooler), sharedPooler);
});

test("rejects an unqualified custom role for the Supabase shared pooler", () => {
  const sharedPooler = {
    ...valid,
    COORDINATION_API_DATABASE_URL:
      "postgresql://coordination_api_prod:password@aws-0-us-west-2.pooler.supabase.com:5432/postgres?sslmode=require",
  };

  assert.throws(() => validateHostEnvironment(sharedPooler), /coordination_api_prod\.project/);
});

test("rejects a privileged or reused runtime identity", () => {
  assert.throws(
    () => validateHostEnvironment({ ...valid, COORDINATION_API_DATABASE_URL: valid.COORDINATION_WORKER_DATABASE_URL }),
    /coordination_api_prod/,
  );
});

test("preserves the host instance across restarts while updating the commit", () => {
  const first = runtimeEnvironment("", "a".repeat(40));
  const firstValues = parseEnvironmentFile(first);
  const second = runtimeEnvironment(first, "b".repeat(40));
  const secondValues = parseEnvironmentFile(second);

  assert.match(firstValues.COORDINATION_HOST_INSTANCE_ID, /^[0-9a-f-]{36}$/u);
  assert.equal(secondValues.COORDINATION_HOST_INSTANCE_ID, firstValues.COORDINATION_HOST_INSTANCE_ID);
  assert.equal(secondValues.COORDINATION_BUILD_COMMIT, "b".repeat(40));
});

const EXPIRED = "2026-09-27T11:00:00.000000000Z ERR Unauthorized: Tunnel not found";
const CONNECTED = "2026-09-27T11:01:00.000000000Z INF Registered tunnel connection";
const CURRENT_ORIGIN = "https://current-session.trycloudflare.com";
const TUNNEL_CONTAINER = "a".repeat(64);
const STARTED_AT = "2026-09-27T08:20:00.000000000Z";

function hostRunner({
  tunnelLogs = [CONNECTED],
  startupErrors = [],
  existing = true,
  running = true,
  status = JSON.stringify({ ready: true, api_origin: CURRENT_ORIGIN }),
  inspectionError = false,
} = {}) {
  const calls = [];
  const logs = [...tunnelLogs];
  const errors = [...startupErrors];
  const runner = (command, args, options) => {
    calls.push({ command, args, options });
    assert.equal(command, "docker");
    if (args[0] === "inspect") {
      if (inspectionError) throw new Error("Inspection unavailable");
      assert.equal(args.at(-1), TUNNEL_CONTAINER);
      assert.doesNotMatch(args[2], /Config|Env/u);
      return JSON.stringify({ running, startedAt: STARTED_AT });
    }
    if (args[0] === "logs") {
      assert.deepEqual(args, [
        "logs", "--timestamps", "--since", STARTED_AT, "--tail", "200", TUNNEL_CONTAINER,
      ]);
      assert.equal(options.includeStderr, true);
      return logs.shift() ?? CONNECTED;
    }
    assert.deepEqual(args.slice(0, 7), [
      "compose", "--env-file", ".env", "--env-file", ".env.runtime", "-f", "compose.yaml",
    ]);
    const action = args.slice(7);
    if (action[0] === "ps") {
      assert.deepEqual(action, ["ps", "-a", "-q", "tunnel"]);
      return existing ? TUNNEL_CONTAINER : "";
    }
    if (action[0] === "up") {
      if (!action.includes("--force-recreate")) {
        const error = errors.shift();
        if (error) throw error;
      }
      return "";
    }
    if (action[0] === "exec") {
      assert.deepEqual(action, [
        "exec", "-T", "registrar", "python", "-m", "coordination.hosting.registrar", "--status",
      ]);
      return status;
    }
    if (action[0] === "logs") return "Historical https://old-session.trycloudflare.com";
    assert.fail(`Unexpected mocked command: ${args.join(" ")}`);
  };
  return {
    runner,
    calls,
    startups: () => calls.filter(({ args }) => args[0] === "compose" && args[7] === "up")
      .map(({ args }) => args.slice(7)),
  };
}

test("only an unrecovered explicit expired-session event authorizes tunnel rotation", () => {
  assert.equal(hasExpiredQuickTunnelSession(EXPIRED), true);
  assert.equal(hasExpiredQuickTunnelSession(`${EXPIRED}\n${CONNECTED}`), false);
  assert.equal(hasExpiredQuickTunnelSession("DNS lookup failed\nconnection timeout"), false);
  assert.equal(hasExpiredQuickTunnelSession("Unauthorized: invalid token"), false);
  assert.equal(hasExpiredQuickTunnelSession("host.registration_retry\nhost.lease_conflict"), false);
  assert.equal(hasExpiredQuickTunnelSession(""), false);
});

test("timestamp order prevents captured stderr from making a recovered session look expired", () => {
  assert.equal(hasExpiredQuickTunnelSession(`${CONNECTED}\n${EXPIRED}`), false);
  const laterFailure = EXPIRED.replace("11:00:00", "11:02:00");
  assert.equal(hasExpiredQuickTunnelSession(`${laterFailure}\n${CONNECTED}`), true);
});

test("healthy startup keeps the tunnel and reports the current registered origin", () => {
  const fake = hostRunner();
  assert.equal(startHostServices({ runner: fake.runner, log: () => assert.fail("Unexpected recovery") }), CURRENT_ORIGIN);
  assert.deepEqual(fake.startups(), [["up", "-d", "--build", "--wait", "--wait-timeout", "300"]]);
  assert.equal(fake.calls.some(({ args }) => args[0] === "compose" && args[7] === "logs"), false);
});

test("confirmed stale existing session recreates only the tunnel before normal startup", () => {
  const fake = hostRunner({ tunnelLogs: [EXPIRED] });
  const messages = [];
  assert.equal(startHostServices({ runner: fake.runner, log: (message) => messages.push(message) }), CURRENT_ORIGIN);
  assert.deepEqual(fake.startups(), [
    ["up", "-d", "--no-deps", "--force-recreate", "tunnel"],
    ["up", "-d", "--build", "--wait", "--wait-timeout", "300"],
  ]);
  assert.equal(messages.length, 1);
});

test("an expired session first found after waiting gets one recovery and a no-build wait", () => {
  const fake = hostRunner({ tunnelLogs: [CONNECTED, EXPIRED], startupErrors: [new Error("Wait failed")] });
  assert.equal(startHostServices({ runner: fake.runner, log: () => {} }), CURRENT_ORIGIN);
  assert.deepEqual(fake.startups(), [
    ["up", "-d", "--build", "--wait", "--wait-timeout", "300"],
    ["up", "-d", "--no-deps", "--force-recreate", "tunnel"],
    ["up", "-d", "--wait", "--wait-timeout", "300"],
  ]);
});

test("a failed wait after early recovery never rotates the tunnel twice", () => {
  const fake = hostRunner({ tunnelLogs: [EXPIRED, EXPIRED], startupErrors: [new Error("Still unhealthy")] });
  assert.throws(() => startHostServices({ runner: fake.runner, log: () => {} }), /after one Quick Tunnel recovery attempt/u);
  assert.equal(fake.startups().filter((args) => args.includes("--force-recreate")).length, 1);
  assert.equal(fake.calls.filter(({ args }) => args[0] === "logs").length, 1);
});

test("a failed wait after late recovery is terminal, not another restart loop", () => {
  const fake = hostRunner({
    tunnelLogs: [CONNECTED, EXPIRED, EXPIRED],
    startupErrors: [new Error("Wait failed"), new Error("Still unhealthy")],
  });
  assert.throws(() => startHostServices({ runner: fake.runner, log: () => {} }), /after one Quick Tunnel recovery attempt/u);
  assert.equal(fake.startups().filter((args) => args.includes("--force-recreate")).length, 1);
  assert.equal(fake.startups().length, 3);
});

test("database or lease failure does not trigger tunnel recreation", () => {
  for (const failure of ["host.registration_retry", "host.lease_conflict", "DNS lookup failed"]) {
    const expected = new Error(failure);
    const fake = hostRunner({ tunnelLogs: [CONNECTED, failure], startupErrors: [expected] });
    assert.throws(() => startHostServices({ runner: fake.runner, log: () => assert.fail("Unexpected recovery") }), (error) => error === expected);
    assert.equal(fake.startups().length, 1);
  }
});

test("fresh, stopped or uninspectable tunnels receive normal startup without forced rotation", () => {
  for (const options of [{ existing: false }, { running: false }, { inspectionError: true }]) {
    const fake = hostRunner({ ...options, tunnelLogs: [EXPIRED] });
    assert.equal(startHostServices({ runner: fake.runner, log: () => assert.fail("Unexpected recovery") }), CURRENT_ORIGIN);
    assert.equal(fake.startups().length, 1);
  }
});

test("success cannot come from an old log URL or an invalid current readiness response", () => {
  for (const status of [
    "not json",
    JSON.stringify({ ready: false, api_origin: CURRENT_ORIGIN }),
    JSON.stringify({ ready: true, api_origin: "http://current-session.trycloudflare.com" }),
    JSON.stringify({ ready: true, api_origin: "https://current-session.trycloudflare.com/path" }),
    JSON.stringify({ ready: true, api_origin: "https://current-session.trycloudflare.com@other.example" }),
    JSON.stringify({ ready: true, api_origin: null }),
  ]) {
    const fake = hostRunner({ status });
    assert.throws(() => startHostServices({ runner: fake.runner, log: () => assert.fail("Unexpected recovery") }), /readiness status|not currently registered/u);
    assert.equal(fake.startups().length, 1);
  }
});
