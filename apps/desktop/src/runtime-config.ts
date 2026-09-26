const DEFAULT_API_ORIGIN = "http://127.0.0.1:8000";

export interface PublicRuntimeConfig {
  apiOrigin: string;
  productName: string;
  supabaseConfigured: boolean;
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
  return {
    apiOrigin: normaliseOrigin(env.VITE_API_ORIGIN),
    productName: env.VITE_PRODUCT_NAME?.trim() || "Coordination Engine",
    supabaseConfigured: Boolean(
      env.VITE_SUPABASE_URL?.trim() && env.VITE_SUPABASE_PUBLISHABLE_KEY?.trim(),
    ),
  };
}
