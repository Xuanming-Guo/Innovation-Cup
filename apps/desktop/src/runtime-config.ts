const DEFAULT_API_ORIGIN = "http://127.0.0.1:8000";
const PUBLIC_CONFIG_STORAGE_KEY = "coordination.public-runtime-config.v1";
const COMPANY_ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export type ApiMode = "static" | "supabase-discovery";

export interface PublicRuntimeConfigInput {
  apiOrigin: string;
  supabaseUrl: string;
  supabasePublishableKey: string;
  defaultCompanyId: string;
}

export interface PublicRuntimeConfig {
  apiMode: ApiMode;
  apiOrigin: string;
  productName: string;
  supabaseConfigured: boolean;
  supabaseUrl: string | null;
  supabasePublishableKey: string | null;
  defaultCompanyId: string | null;
  hackathonDemo: boolean;
}

function normaliseOrigin(rawOrigin: string | undefined): string {
  const value = rawOrigin?.trim() || DEFAULT_API_ORIGIN;
  const url = new URL(value);

  if (url.protocol !== "https:" && !["localhost", "127.0.0.1", "::1"].includes(url.hostname)) {
    throw new Error("VITE_API_ORIGIN must use HTTPS outside local development");
  }

  return url.origin;
}

function normaliseSupabaseUrl(rawUrl: string): string {
  const url = new URL(rawUrl.trim());
  if (url.protocol !== "https:") {
    throw new Error("Supabase URL must use HTTPS");
  }
  return url.origin;
}

function parseApiMode(value: string | undefined): ApiMode {
  const mode = value?.trim() || "static";
  if (mode !== "static" && mode !== "supabase-discovery") {
    throw new Error("VITE_API_MODE must be static or supabase-discovery");
  }
  return mode;
}

export function createPublicRuntimeConfig(
  input: PublicRuntimeConfigInput,
  productName = "ALTO",
): PublicRuntimeConfig {
  const supabasePublishableKey = input.supabasePublishableKey.trim();
  const defaultCompanyId = input.defaultCompanyId.trim();
  if (!supabasePublishableKey) throw new Error("Supabase publishable key is required");
  if (!COMPANY_ID_PATTERN.test(defaultCompanyId)) {
    throw new Error("Company ID must be a UUID");
  }
  return {
    apiMode: "static",
    apiOrigin: normaliseOrigin(input.apiOrigin),
    productName,
    supabaseConfigured: true,
    supabaseUrl: normaliseSupabaseUrl(input.supabaseUrl),
    supabasePublishableKey,
    defaultCompanyId,
    hackathonDemo: false,
  };
}

export function getPublicRuntimeConfig(env: ImportMetaEnv = import.meta.env): PublicRuntimeConfig {
  const apiMode = parseApiMode(env.VITE_API_MODE);
  const rawSupabaseUrl = env.VITE_SUPABASE_URL?.trim() || null;
  const supabasePublishableKey = env.VITE_SUPABASE_PUBLISHABLE_KEY?.trim() || null;
  const defaultCompanyId = env.VITE_DEFAULT_COMPANY_ID?.trim() || null;
  if ((rawSupabaseUrl === null) !== (supabasePublishableKey === null)) {
    throw new Error("Supabase URL and publishable key must be configured together");
  }
  if (defaultCompanyId !== null && !COMPANY_ID_PATTERN.test(defaultCompanyId)) {
    throw new Error("VITE_DEFAULT_COMPANY_ID must be a UUID");
  }
  const supabaseUrl = rawSupabaseUrl === null ? null : normaliseSupabaseUrl(rawSupabaseUrl);
  if (apiMode === "supabase-discovery" && (supabaseUrl === null || defaultCompanyId === null)) {
    throw new Error("Supabase discovery requires Supabase configuration and a company ID");
  }
  return {
    apiMode,
    apiOrigin: apiMode === "static" ? normaliseOrigin(env.VITE_API_ORIGIN) : DEFAULT_API_ORIGIN,
    productName: env.VITE_PRODUCT_NAME?.trim() || "ALTO",
    supabaseConfigured: supabaseUrl !== null,
    supabaseUrl,
    supabasePublishableKey,
    defaultCompanyId,
    hackathonDemo: env.VITE_HACKATHON_DEMO?.trim().toLowerCase() === "true",
  };
}

export function loadPublicRuntimeConfig(
  env: ImportMetaEnv = import.meta.env,
  storage: Pick<Storage, "getItem" | "removeItem"> = window.localStorage,
): PublicRuntimeConfig {
  const environmentConfig = getPublicRuntimeConfig(env);
  if (environmentConfig.hackathonDemo) return environmentConfig;
  const storedValue = storage.getItem(PUBLIC_CONFIG_STORAGE_KEY);
  if (storedValue === null) return environmentConfig;

  try {
    const parsed = JSON.parse(storedValue) as Partial<PublicRuntimeConfigInput>;
    if (
      typeof parsed.apiOrigin !== "string" ||
      typeof parsed.supabaseUrl !== "string" ||
      typeof parsed.supabasePublishableKey !== "string" ||
      typeof parsed.defaultCompanyId !== "string"
    ) {
      throw new Error("Stored deployment configuration is incomplete");
    }
    return createPublicRuntimeConfig(
      parsed as PublicRuntimeConfigInput,
      environmentConfig.productName,
    );
  } catch {
    storage.removeItem(PUBLIC_CONFIG_STORAGE_KEY);
    return environmentConfig;
  }
}

export function savePublicRuntimeConfig(
  input: PublicRuntimeConfigInput,
  productName: string,
  storage: Pick<Storage, "setItem"> = window.localStorage,
): PublicRuntimeConfig {
  const config = createPublicRuntimeConfig(input, productName);
  storage.setItem(PUBLIC_CONFIG_STORAGE_KEY, JSON.stringify({
    apiOrigin: config.apiOrigin,
    supabaseUrl: config.supabaseUrl,
    supabasePublishableKey: config.supabasePublishableKey,
    defaultCompanyId: config.defaultCompanyId,
  }));
  return config;
}

export function clearPublicRuntimeConfig(
  storage: Pick<Storage, "removeItem"> = window.localStorage,
): void {
  storage.removeItem(PUBLIC_CONFIG_STORAGE_KEY);
}
