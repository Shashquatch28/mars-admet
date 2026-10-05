import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// MARS frontend — Vite SPA (ADR-001). No SSR; emits a static bundle the API
// container or a CDN can serve.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
});
