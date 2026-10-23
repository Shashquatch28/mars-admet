/// <reference types="vite/client" />

interface ImportMetaEnv {
  // Base URL of the MARS API: "/api" in dev and in the production build. When unset, the UI
  // has no API: it says so and shows no values (ADR-032).
  readonly VITE_API_BASE?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}

// Ketcher's standalone package ships four builds under subpath exports without type declarations; each re-exports the
// same API as the root entry. This one keeps Indigo's WebAssembly as a separate file (not base64 inside the chunk)
// and leaves out Indigo's image renderer, which the editor does not use (ADR-035).
declare module "ketcher-standalone/dist/binaryWasmNoRender" {
  export * from "ketcher-standalone";
}
