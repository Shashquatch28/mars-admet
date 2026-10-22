import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// MARS frontend — Vite SPA (ADR-001). No SSR; emits a static bundle the API
// container or a CDN can serve.
//
// The API lives under /api in every environment (ADR-025). Dev talks to it through
// a same-origin proxy that forwards /api/* unchanged, so the browser never makes a
// cross-origin request and the API's CORS policy does not apply. In production the
// API container serves this bundle and /api itself, so the build (VITE_API_BASE=/api)
// needs no proxy either.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.MARS_API_PROXY_TARGET || "http://localhost:8000";
  return {
    plugins: [react()],
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
