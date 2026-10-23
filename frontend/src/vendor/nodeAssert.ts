// Stand-in for Node's "assert", aliased in vite.config.ts for ketcher-core only (ADR-035). ketcher-core imports it
// and calls it as assert(condition, message) in 51 places, never as assert.equal and the like. The npm "assert" package
// it would otherwise resolve to reads Node's `process` (stderr, env) when it loads, which a browser does not have.
export default function assert(condition: unknown, message?: string | Error): asserts condition {
  if (condition) return;
  throw message instanceof Error ? message : new Error(message ?? "Assertion failed");
}
