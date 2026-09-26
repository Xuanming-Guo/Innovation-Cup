const DEFAULT_API_ORIGIN = "http://127.0.0.1:8000";

export interface PublicRuntimeConfig {
  apiOrigin: string;
  productName: string;
  supabaseConfigured: boolean;
  supabaseUrl: string | null;
  supabasePublishableKey: string | null;
  defaultCompanyId: string | null;
}

function normaliseOrigin(rawOrigin: string | undefined): string {
  const value = rawOrigin?.trim() || DEFAULT_API_ORIGIN;
  const url = new URL(value);

  if (url.protocol !== "https:" && !["localhost", "127.0.0.1", "::1"].includes(url.hostname)) {
    throw new Error("VITE_API_ORIGIN must use HTTPS outside local development");
  }

  return url.origin;
}

export function getPublicRuntimeConfig(env: ImportMetaEnv = import.meta.env): PublicRuntimeConfig {
  const supabaseUrl = env.VITE_SUPABASE_URL?.trim() || null;
  const supabasePublishableKey = env.VITE_SUPABASE_PUBLISHABLE_KEY?.trim() || null;
  if ((supabaseUrl === null) !== (supabasePublishableKey === null)) {
    throw new Error("Supabase URL and publishable key must be configured together");
  }
  if (supabaseUrl !== null && new URL(supabaseUrl).protocol !== "https:") {
    throw new Error("VITE_SUPABASE_URL must use HTTPS");
  }
  return {
    apiOrigin: normaliseOrigin(env.VITE_API_ORIGIN),
    productName: env.VITE_PRODUCT_NAME?.trim() || "Coordination Engine",
    supabaseConfigured: supabaseUrl !== null,
    supabaseUrl,
    supabasePublishableKey,
    defaultCompanyId: env.VITE_DEFAULT_COMPANY_ID?.trim() || null,
  };
}
