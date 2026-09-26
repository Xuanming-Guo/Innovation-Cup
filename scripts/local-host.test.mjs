import assert from "node:assert/strict";
import test from "node:test";

import {
  parseEnvironmentFile,
  runtimeEnvironment,
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
