import { defineConfig, devices } from "@playwright/test";

const PORT = Number(process.env.E2E_PORT ?? 3100);
const API_PORT = Number(process.env.E2E_API_PORT ?? 3101);
const CI = Boolean(process.env.CI);

/**
 * End-to-end and accessibility tests run against a PRODUCTION build (`pnpm build:e2e` first), because
 * that is what ships and what the Content Security Policy applies to.
 * Chromium only: its virtual WebAuthn authenticator is what lets us test passkeys without a phone.
 * Two form factors: a mid-range Android phone (the main target) and a desktop (the agent's page).
 */
export default defineConfig({
  testDir: "tests/e2e",
  fullyParallel: true,
  forbidOnly: CI,
  retries: CI ? 1 : 0,
  reporter: CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: "on-first-retry",
  },
  projects: [
    { name: "phone", use: { ...devices["Pixel 7"] } },
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: [
    // A stand-in for the Zolo API. The production build proxies /api/* to it (BACKEND_URL, read at runtime).
    {
      command: "node tests/e2e/fake-api.mjs",
      url: `http://localhost:${API_PORT}/healthz`,
      ignoreHTTPSErrors: true,
      reuseExistingServer: !CI,
      env: { E2E_API_PORT: String(API_PORT) },
    },
    {
      command: `pnpm start --port ${PORT}`,
      url: `http://localhost:${PORT}`,
      env: { BACKEND_URL: `http://localhost:${API_PORT}` },
      reuseExistingServer: !CI,
      timeout: 120_000,
    },
  ],
});
