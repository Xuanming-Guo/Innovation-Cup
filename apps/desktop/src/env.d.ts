/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_PRODUCT_NAME?: string;
  readonly VITE_API_ORIGIN?: string;
  readonly VITE_SUPABASE_URL?: string;
  readonly VITE_SUPABASE_PUBLISHABLE_KEY?: string;
  readonly VITE_DEFAULT_COMPANY_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
