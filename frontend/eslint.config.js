import js from "@eslint/js";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "node_modules", "playwright-report", "test-results"] },
  {
    // Build-time scripts run in Node.
    files: ["scripts/**/*.mjs"],
    languageOptions: { globals: { ...globals.node } },
  },
  {
    // The service worker's text; the build puts `const BUILD = ...` before it.
    files: ["pwa/sw.template.js"],
    languageOptions: { globals: { ...globals.serviceworker, BUILD: "readonly" } },
  },
  {
    files: ["public/recorder-worklet.js"],
    languageOptions: {
      globals: { AudioWorkletProcessor: "readonly", registerProcessor: "readonly" },
    },
  },
  js.configs.recommended,
  ...tseslint.configs.strict,
  jsxA11y.flatConfigs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "no-empty": ["error", { allowEmptyCatch: false }],
      "no-console": ["error", { allow: ["error"] }],
    },
  },
  {
    // One table frame and one confirmation dialog for the whole app, so a page cannot get wider
    // than a phone screen or ask with the browser's own unstyled boxes.
    files: ["src/**/*.tsx"],
    ignores: ["src/components/DataTable.tsx", "src/**/*.test.tsx"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: "JSXOpeningElement[name.name='table']",
          message: "Use <DataTable> from components/DataTable.",
        },
        {
          selector:
            "CallExpression[callee.object.name='window'][callee.property.name=/^(prompt|confirm|alert)$/]",
          message: "Use useConfirm() from components/ConfirmDialog.",
        },
      ],
    },
  },
);
