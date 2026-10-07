import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// MARS frontend — Vite SPA (ADR-001). No SSR; emits a static bundle the API
// container or a CDN can serve.
//
// Dev talks to the API through a same-origin proxy: VITE_API_BASE=/api and the
// dev server forwards /api/* to the API with the prefix stripped. The browser
// never makes a cross-origin request, so the API's CORS policy does not apply in
// dev. (The proxy is dev-only; `vite build` output needs a real API origin.)
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
          rewrite: (path) => path.replace(/^\/api/, ""),
        },
      },
    },
  };
});
