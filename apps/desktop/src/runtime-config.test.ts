import { describe, expect, it } from "vitest";

import {
  getPublicRuntimeConfig,
  loadPublicRuntimeConfig,
  savePublicRuntimeConfig,
} from "./runtime-config";

describe("getPublicRuntimeConfig", () => {
  it("accepts localhost HTTP for native development", () => {
    const config = getPublicRuntimeConfig({
      VITE_API_ORIGIN: "http://127.0.0.1:8000/path",
      VITE_PRODUCT_NAME: "Coordination Engine",
      VITE_SUPABASE_PUBLISHABLE_KEY: "public-key",
      VITE_SUPABASE_URL: "https://example.supabase.co",
      VITE_DEFAULT_COMPANY_ID: "11111111-1111-4111-8111-111111111111",
    } as ImportMetaEnv);

    expect(config).toEqual({
      apiOrigin: "http://127.0.0.1:8000",
      productName: "Coordination Engine",
      supabaseConfigured: true,
      supabaseUrl: "https://example.supabase.co",
      supabasePublishableKey: "public-key",
      defaultCompanyId: "11111111-1111-4111-8111-111111111111",
    });
  });

  it("rejects insecure non-local API origins", () => {
    expect(() =>
      getPublicRuntimeConfig({ VITE_API_ORIGIN: "http://api.example.com" } as ImportMetaEnv),
    ).toThrow("must use HTTPS");
  });

  it("requires the public Supabase URL and key as a pair", () => {
    expect(() =>
      getPublicRuntimeConfig({ VITE_SUPABASE_URL: "https://example.supabase.co" } as ImportMetaEnv),
    ).toThrow("configured together");
  });

  it("rejects an invalid compiled company identifier", () => {
    expect(() => getPublicRuntimeConfig({
      VITE_SUPABASE_URL: "https://example.supabase.co",
      VITE_SUPABASE_PUBLISHABLE_KEY: "public-key",
      VITE_DEFAULT_COMPANY_ID: "wrong-company",
    } as ImportMetaEnv)).toThrow("must be a UUID");
  });

  it("persists a validated public deployment override", () => {
    let storedValue: string | null = null;
    const storage = {
      getItem: () => storedValue,
      removeItem: () => { storedValue = null; },
      setItem: (_key: string, value: string) => { storedValue = value; },
    };

    savePublicRuntimeConfig({
      apiOrigin: "https://api.example.com/v1",
      supabaseUrl: "https://project.supabase.co/path",
      supabasePublishableKey: "sb_publishable_public",
      defaultCompanyId: "11111111-1111-4111-8111-111111111111",
    }, "Test product", storage);

    expect(loadPublicRuntimeConfig({} as ImportMetaEnv, storage)).toMatchObject({
      apiOrigin: "https://api.example.com",
      productName: "Coordination Engine",
      supabaseUrl: "https://project.supabase.co",
      supabasePublishableKey: "sb_publishable_public",
      defaultCompanyId: "11111111-1111-4111-8111-111111111111",
    });
  });

  it("rejects insecure hosted endpoints", () => {
    expect(() => savePublicRuntimeConfig({
      apiOrigin: "http://api.example.com",
      supabaseUrl: "https://project.supabase.co",
      supabasePublishableKey: "sb_publishable_public",
      defaultCompanyId: "11111111-1111-4111-8111-111111111111",
    }, "Coordination Engine", { setItem: () => undefined })).toThrow("must use HTTPS");
  });
});
