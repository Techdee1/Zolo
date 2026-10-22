import { defineConfig, devices } from "@playwright/test";

/**
 * The same journeys, against the REAL backend (Postgres, the real WebAuthn verification, the real
 * state machine) instead of the fake. Chromium's virtual authenticator plays the phone.
 *
 *   pnpm build:e2e && pnpm e2e:real
 *
 * It needs Docker for Postgres (`docker compose up -d postgres` in ../backend) and `uv`. It uses its
 * own database (`zolo_e2e`) and its own ports, so it never touches your development data.
 * The passkey origin and RP_ID are the FRONTEND's (localhost:3300), as in production: the browser
 * only ever talks to the frontend, which proxies /api to the backend.
 */
const FRONT = Number(process.env.REAL_FRONT_PORT ?? 3300);
const BACK = Number(process.env.REAL_BACK_PORT ?? 3301);
const DB =
  process.env.REAL_DATABASE_URL ?? "postgresql+asyncpg://zolo:zolo@localhost:5432/zolo_e2e";
const CI = Boolean(process.env.CI);

export const DEMO_TOKEN = "e2e-demo-token";

export default defineConfig({
  testDir: "tests/real",
  fullyParallel: false,
  workers: 1,
  forbidOnly: CI,
  retries: 0,
  timeout: 60_000,
  reporter: CI
    ? [["github"], ["html", { open: "never", outputFolder: "playwright-report-real" }]]
    : "list",
  use: { baseURL: `http://localhost:${FRONT}`, trace: "retain-on-failure" },
  projects: [{ name: "real", use: { ...devices["Pixel 7"] } }],
  webServer: [
    {
      command:
        "uv run python -m alembic upgrade head && uv run python -m zolo.seed && " +
        "uv run python ../frontend/tests/real/clear_passkeys.py && " +
        `uv run python -m uvicorn zolo.api.main:create_app --factory --port ${BACK}`,
      cwd: "../backend",
      url: `http://localhost:${BACK}/readyz`,
      reuseExistingServer: !CI,
      timeout: 120_000,
      env: {
        DATABASE_URL: DB,
        SESSION_SECRET: "e2e-session-secret-that-is-at-least-32-chars",
        RP_ID: "localhost",
        ORIGIN: `http://localhost:${FRONT}`,
        CORS_ORIGINS: `http://localhost:${FRONT}`,
        COOKIE_SECURE: "false",
        TRUST_FORWARDED_FOR: "true",
        DEMO_MODE: "true",
        DEMO_TOKEN,
        ENV: "dev",
        MOCK_BANK_LATENCY_MIN_MS: "50",
        MOCK_BANK_LATENCY_MAX_MS: "100",
      },
    },
    {
      command: `pnpm start --port ${FRONT}`,
      url: `http://localhost:${FRONT}/signin`,
      reuseExistingServer: !CI,
      timeout: 120_000,
      env: { BACKEND_URL: `http://localhost:${BACK}` },
    },
  ],
});
