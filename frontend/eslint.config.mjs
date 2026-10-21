import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import jsxA11y from "eslint-plugin-jsx-a11y";

// Accessibility is the product: every jsx-a11y rule in its STRICT set is an error, and a few
// extras that matter for blind users are spelled out so they cannot be quietly relaxed.
const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    files: ["**/*.{js,jsx,ts,tsx}"],
    rules: {
      ...Object.fromEntries(
        Object.entries(jsxA11y.configs.strict.rules ?? {}).map(([name, level]) => [
          name,
          level === "off" ? "off" : "error",
        ]),
      ),
      "jsx-a11y/no-autofocus": "error", // focus is managed deliberately, on the h1, on route change
      "jsx-a11y/anchor-is-valid": "error",
      "jsx-a11y/no-noninteractive-tabindex": ["error", { tags: [], roles: ["tabpanel"] }],
      "jsx-a11y/control-has-associated-label": "error",
      "no-restricted-syntax": [
        "error",
        {
          selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
          message: "No raw HTML: names and amounts come from the API and must stay text.",
        },
      ],
    },
  },
  {
    // Money is integer kobo. No floating-point tools where amounts are formatted.
    files: ["lib/format/**/*.ts"],
    rules: {
      "no-restricted-globals": [
        "error",
        { name: "parseFloat", message: "Money is integer kobo: no floats." },
      ],
      "no-restricted-properties": [
        "error",
        { object: "Number", property: "parseFloat", message: "Money is integer kobo: no floats." },
        { property: "toFixed", message: "Money is integer kobo: no floats." },
        { property: "toLocaleString", message: "Use groupDigits: a fixed format, no locale." },
        { object: "Math", property: "round", message: "Money is integer kobo: no rounding." },
        { object: "Math", property: "floor", message: "Use BigInt or integer arithmetic." },
        { object: "Math", property: "ceil", message: "Use BigInt or integer arithmetic." },
      ],
    },
  },
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "coverage/**",
    "playwright-report/**",
    "test-results/**",
    "next-env.d.ts",
    "lib/api/schema.d.ts", // generated from backend/openapi.json
  ]),
]);

export default eslintConfig;
