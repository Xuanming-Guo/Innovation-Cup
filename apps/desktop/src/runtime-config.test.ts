import { describe, expect, it } from "vitest";

import { getPublicRuntimeConfig } from "./runtime-config";

describe("getPublicRuntimeConfig", () => {
  it("accepts localhost HTTP for native development", () => {
    const config = getPublicRuntimeConfig({
      VITE_API_ORIGIN: "http://127.0.0.1:8000/path",
      VITE_PRODUCT_NAME: "Coordination Engine",
      VITE_SUPABASE_PUBLISHABLE_KEY: "public-key",
      VITE_SUPABASE_URL: "https://example.supabase.co",
    } as ImportMetaEnv);

    expect(config).toEqual({
      apiOrigin: "http://127.0.0.1:8000",
      productName: "Coordination Engine",
      supabaseConfigured: true,
    });
  });

  it("rejects insecure non-local API origins", () => {
    expect(() =>
      getPublicRuntimeConfig({ VITE_API_ORIGIN: "http://api.example.com" } as ImportMetaEnv),
    ).toThrow("must use HTTPS");
  });
});
