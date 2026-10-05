import { defineConfig } from "vitest/config";

// Unit tests target the pure domain layer (state derivation, reconciliation,
// formatting) — no DOM needed.
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
