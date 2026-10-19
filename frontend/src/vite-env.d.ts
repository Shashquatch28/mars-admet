/// <reference types="vite/client" />

interface ImportMetaEnv {
  // Base URL of the MARS API: "/api" in dev and in the production build. When unset, the UI
  // runs on the illustrative fixture and shows the "design prototype" strip.
  readonly VITE_API_BASE?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
