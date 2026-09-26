import { pathToFileURL } from "node:url";

const COMPANY_ID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const REQUIRED_VARIABLES = [
  "VITE_API_MODE",
  "VITE_SUPABASE_URL",
  "VITE_SUPABASE_PUBLISHABLE_KEY",
  "VITE_DEFAULT_COMPANY_ID",
];

function required(environment, name) {
  const value = environment[name]?.trim();
  if (!value) throw new Error(`${name} is required for a native release`);
  return value;
}

function requireHttpsOrigin(value, name) {
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new Error(`${name} must be a valid HTTPS origin`);
  }

  if (
    url.protocol !== "https:" ||
    url.username ||
    url.password ||
    url.pathname !== "/" ||
    url.search ||
    url.hash
  ) {
    throw new Error(`${name} must be an HTTPS origin with no credentials, path, query, or fragment`);
  }

  return url.origin;
}

export function validatePublicReleaseConfig(environment) {
  const apiMode = required(environment, "VITE_API_MODE");
  if (apiMode !== "static" && apiMode !== "supabase-discovery") {
    throw new Error("VITE_API_MODE must be static or supabase-discovery");
  }
  const apiOrigin = apiMode === "static"
    ? requireHttpsOrigin(required(environment, "VITE_API_ORIGIN"), "VITE_API_ORIGIN")
    : null;
  const supabaseUrl = requireHttpsOrigin(
    required(environment, "VITE_SUPABASE_URL"),
    "VITE_SUPABASE_URL",
  );
  const supabasePublishableKey = required(
    environment,
    "VITE_SUPABASE_PUBLISHABLE_KEY",
  );
  const defaultCompanyId = required(environment, "VITE_DEFAULT_COMPANY_ID");

  if (!supabasePublishableKey.startsWith("sb_publishable_")) {
    throw new Error(
      "VITE_SUPABASE_PUBLISHABLE_KEY must be an sb_publishable_ key; never embed a secret or service-role key",
    );
  }
  if (!COMPANY_ID_PATTERN.test(defaultCompanyId)) {
    throw new Error("VITE_DEFAULT_COMPANY_ID must be a UUID");
  }

  return { apiMode, apiOrigin, supabaseUrl, supabasePublishableKey, defaultCompanyId };
}

function isMainModule() {
  return process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
}

if (isMainModule()) {
  try {
    validatePublicReleaseConfig(process.env);
    console.log(`Validated ${REQUIRED_VARIABLES.length} baked public release variables.`);
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  }
}
