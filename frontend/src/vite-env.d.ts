/// <reference types="vite/client" />

interface ImportMetaEnv {
  // Base URL of the MARS API: "/api" in dev and in the production build. When unset, the UI
  // has no API: it says so and shows no values (ADR-031).
  readonly VITE_API_BASE?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
