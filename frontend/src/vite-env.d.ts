/// <reference types="vite/client" />

interface ImportMetaEnv {
  // Base URL of the MARS API (e.g. http://localhost:8000). When unset, the UI
  // runs on the illustrative fixture and shows the "design prototype" strip.
  readonly VITE_API_BASE?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
