/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_PRODUCT_NAME?: string;
  readonly VITE_API_MODE?: string;
  readonly VITE_API_ORIGIN?: string;
  readonly VITE_SUPABASE_URL?: string;
  readonly VITE_SUPABASE_PUBLISHABLE_KEY?: string;
  readonly VITE_DEFAULT_COMPANY_ID?: string;
  readonly VITE_HACKATHON_DEMO?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
