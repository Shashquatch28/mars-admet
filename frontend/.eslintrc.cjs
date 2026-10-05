/* ESLint for the MARS frontend.
 *
 * Two jobs. The first is ordinary TS/React correctness. The second is the one
 * that matters here: mechanically enforcing the rules in AGENTS.md that an AI
 * coding agent will otherwise quietly break. A rule that only lives in prose
 * gets re-litigated every session; a rule in this file does not.
 *
 * What is NOT enforced here, because the type system already does it better:
 * IntervalTrack and ADGauge require an explicit `domain` with no default
 * (ADR-005, ADR-012), so a caller cannot invent a scale without a type error.
 */
module.exports = {
  root: true,
  env: { browser: true, es2022: true },
  parser: "@typescript-eslint/parser",
  parserOptions: { ecmaVersion: "latest", sourceType: "module", ecmaFeatures: { jsx: true } },
  plugins: ["@typescript-eslint", "react-refresh"],
  extends: [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended",
    "plugin:react-hooks/recommended",
  ],
  ignorePatterns: ["dist", "node_modules", "*.cjs", "vite.config.ts", "vitest.config.ts"],
  settings: { react: { version: "18.3" } },
  rules: {
    "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
    "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
    "@typescript-eslint/consistent-type-imports": ["warn", { prefer: "type-imports" }],
    eqeqeq: ["error", "always", { null: "ignore" }],
    "no-restricted-syntax": [
      "error",
      {
        // AGENTS.md: "No raw hex in a component — reference a CSS custom
        // property from a scoped .module.css." Hex in a component means a
        // colour that exists outside the token layer, which is how a design
        // system drifts. Note SVG presentation attributes do not resolve
        // var(), so SVG colour goes through a CSS class (see StructureViewer).
        selector: "Literal[value=/#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})(?![0-9a-zA-Z])/]",
        message:
          "Raw hex colour. Use a token: var(--surface-panel) etc. from src/styles/tokens.css (AGENTS.md).",
      },
      {
        // AGENTS.md #2: row state is DERIVED inside EndpointRow from the
        // contract, never passed in. A `variant`/`tone`/`severity` prop is how
        // a caller would start colouring a value by what it thinks it means.
        selector:
          "JSXOpeningElement[name.name='EndpointRow'] > JSXAttribute[name.name=/^(variant|tone|severity|status|highlight|intent)$/]",
        message:
          "EndpointRow takes no variant/tone/severity/status/highlight prop. Row state is derived inside the component from the contract (AGENTS.md, ADR-006).",
      },
    ],
  },
  overrides: [
    {
      // Fixtures and tests legitimately hold illustrative literals.
      files: ["**/*.test.ts", "**/*.test.tsx"],
      rules: { "no-restricted-syntax": "off" },
    },
  ],
};
