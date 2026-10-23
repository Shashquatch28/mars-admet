import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

// MARS frontend — Vite SPA (ADR-001). No SSR; emits a static bundle the API
// container or a CDN can serve.
//
// The API lives under /api in every environment (ADR-025). Dev talks to it through
// a same-origin proxy that forwards /api/* unchanged, so the browser never makes a
// cross-origin request and the API's CORS policy does not apply. In production the
// API container serves this bundle and /api itself, so the build (VITE_API_BASE=/api)
// needs no proxy either.
export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.MARS_API_PROXY_TARGET || "http://localhost:8000";
  return {
    plugins: [react()],
    resolve: {
      // ketcher-core imports two Node built-ins that Vite would externalise (ADR-035). "events" is the npm package of
      // the same name, the browser EventEmitter. "assert" is a local stand-in, because the npm package needs `process`.
      alias: [
        { find: /^events$/, replacement: "events/" },
        // The build uses the variant that keeps Indigo's WebAssembly as a separate file (7.5 MB, not base64 in a 29 MB
        // script). The dev server's dependency optimiser moves the worker and strands its .wasm, so in dev the
        // self-contained variant stands in for it (ADR-035).
        ...(command === "serve"
          ? [{ find: /^ketcher-standalone\/dist\/binaryWasmNoRender$/, replacement: "ketcher-standalone" }]
          : []),
        { find: /^assert$/, replacement: fileURLToPath(new URL("./src/vendor/nodeAssert.ts", import.meta.url)) },
      ],
    },
    // Some of Ketcher's dependencies read Node's `global` (ADR-035). Same object as `window` in a browser.
    define: { global: "globalThis" },
    optimizeDeps: { esbuildOptions: { define: { global: "globalThis" } } },
    build: {
      // ketcher-core mixes ES imports with require("raphael") in the same module. Left alone, Rollup keeps the
      // require() and the editor fails to load in the built app with "require is not defined" (ADR-035).
      commonjsOptions: { transformMixedEsModules: true },
    },
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
  };
});
