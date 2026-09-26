import assert from "node:assert/strict";
import test from "node:test";

import { validatePublicReleaseConfig } from "./validate-public-config.mjs";

const validEnvironment = {
  VITE_API_MODE: "static",
  VITE_API_ORIGIN: "https://api.coordination.example",
  VITE_SUPABASE_URL: "https://project-ref.supabase.co",
  VITE_SUPABASE_PUBLISHABLE_KEY: "sb_publishable_public-value",
  VITE_DEFAULT_COMPANY_ID: "11111111-1111-4111-8111-111111111111",
};

test("accepts the complete public release configuration", () => {
  assert.deepEqual(validatePublicReleaseConfig(validEnvironment), {
    apiMode: "static",
    apiOrigin: "https://api.coordination.example",
    supabaseUrl: "https://project-ref.supabase.co",
    supabasePublishableKey: "sb_publishable_public-value",
    defaultCompanyId: "11111111-1111-4111-8111-111111111111",
  });
});

test("rejects every missing required release variable", () => {
  for (const name of [
    "VITE_API_MODE",
    "VITE_SUPABASE_URL",
    "VITE_SUPABASE_PUBLISHABLE_KEY",
    "VITE_DEFAULT_COMPANY_ID",
  ]) {
    const environment = { ...validEnvironment };
    delete environment[name];
    assert.throws(
      () => validatePublicReleaseConfig(environment),
      new RegExp(`${name} is required`),
    );
  }
});

test("accepts Supabase discovery without a baked API origin", () => {
  const environment = { ...validEnvironment, VITE_API_MODE: "supabase-discovery" };
  delete environment.VITE_API_ORIGIN;

  assert.deepEqual(validatePublicReleaseConfig(environment), {
    apiMode: "supabase-discovery",
    apiOrigin: null,
    supabaseUrl: "https://project-ref.supabase.co",
    supabasePublishableKey: "sb_publishable_public-value",
    defaultCompanyId: "11111111-1111-4111-8111-111111111111",
  });
});

test("requires a baked API origin in static mode", () => {
  const environment = { ...validEnvironment };
  delete environment.VITE_API_ORIGIN;

  assert.throws(() => validatePublicReleaseConfig(environment), /VITE_API_ORIGIN is required/);
});

test("rejects an unknown API mode", () => {
  assert.throws(
    () => validatePublicReleaseConfig({ ...validEnvironment, VITE_API_MODE: "automatic-ish" }),
    /static or supabase-discovery/,
  );
});

test("rejects insecure or non-origin endpoints", () => {
  assert.throws(
    () => validatePublicReleaseConfig({
      ...validEnvironment,
      VITE_API_ORIGIN: "http://api.coordination.example",
    }),
    /HTTPS origin/,
  );
  assert.throws(
    () => validatePublicReleaseConfig({
      ...validEnvironment,
      VITE_SUPABASE_URL: "https://project-ref.supabase.co/rest/v1",
    }),
    /no credentials, path, query, or fragment/,
  );
});

test("rejects a privileged or malformed Supabase key", () => {
  for (const key of ["sb_secret_do-not-embed", "eyJlegacy-service-role", "publishable-ish"]) {
    assert.throws(
      () => validatePublicReleaseConfig({
        ...validEnvironment,
        VITE_SUPABASE_PUBLISHABLE_KEY: key,
      }),
      /sb_publishable_/,
    );
  }
});

test("rejects a malformed company identifier", () => {
  assert.throws(
    () => validatePublicReleaseConfig({
      ...validEnvironment,
      VITE_DEFAULT_COMPANY_ID: "not-a-company-uuid",
    }),
    /must be a UUID/,
  );
});
