import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Browser, type BrowserContext, type Page } from "@playwright/test";

export const BACK = `http://localhost:${process.env.REAL_BACK_PORT ?? 3301}`;
export const DEMO_TOKEN = "e2e-demo-token";

/** Put the real backend back to its starting state (passkeys are kept, as the backend promises). */
export async function resetBackend() {
  const res = await fetch(`${BACK}/demo/reset`, {
    method: "POST",
    headers: { "x-demo-token": DEMO_TOKEN },
  });
  expect(res.status).toBe(200);
}

export async function person(browser: Browser, who: "customer" | "agent") {
  const context = await browser.newContext({ ...test.info().project.use });
  const page = await context.newPage();
  const problems: string[] = [];
  page.on("console", (m) => m.type() === "error" && problems.push(m.text()));
  page.on("pageerror", (e) => problems.push(String(e)));
  await page.goto("/signin");
  await page.waitForLoadState("networkidle");
  await page
    .getByRole("button", { name: who === "agent" ? /I am an agent/ : /I am a customer/ })
    .click();
  await page.waitForURL(who === "agent" ? "**/agent" : "**/home");
  return { context, page, problems };
}

/** Chromium's software authenticator: a fingerprint, face or screen lock that answers by itself. */
export async function virtualAuthenticator(context: BrowserContext, page: Page) {
  const cdp = await context.newCDPSession(page);
  await cdp.send("WebAuthn.enable");
  const { authenticatorId } = await cdp.send("WebAuthn.addVirtualAuthenticator", {
    options: {
      protocol: "ctap2",
      transport: "internal",
      hasResidentKey: true,
      hasUserVerification: true,
      isUserVerified: true,
      automaticPresenceSimulation: true,
    },
  });
  return {
    /** The person fails or refuses the fingerprint/face/lock prompt. */
    refuse: () => cdp.send("WebAuthn.setUserVerified", { authenticatorId, isUserVerified: false }),
    allow: () => cdp.send("WebAuthn.setUserVerified", { authenticatorId, isUserVerified: true }),
    clear: () => cdp.send("WebAuthn.clearCredentials", { authenticatorId }),
    credentials: async () =>
      (await cdp.send("WebAuthn.getCredentials", { authenticatorId })).credentials,
  };
}

export async function makeRequest(agent: Page, digits: string[]) {
  const keypad = agent.getByRole("group", { name: "Amount keypad" });
  for (const d of digits) await keypad.getByRole("button", { name: d }).click();
  await agent.getByRole("button", { name: /^Request/ }).click();
  await agent.waitForURL("**/agent/requests/*");
  const label = await agent.getByRole("img", { name: /^Code: / }).getAttribute("aria-label");
  return { code: label!.replace(/\D/g, ""), id: agent.url().split("/").pop()! };
}

export async function claim(customer: Page, code: string) {
  await customer.goto("/pay/code");
  await customer.waitForLoadState("networkidle");
  await customer.getByRole("textbox", { name: /4-digit code/ }).pressSequentially(code);
  await customer.waitForURL(/\/requests\/[^/]+$/);
  await customer.getByRole("heading", { level: 2, name: "What Zolo says" }).waitFor();
}

export async function setUpPasskey(customer: Page) {
  await customer.goto("/setup/passkey");
  await customer.waitForLoadState("networkidle");
  await customer.getByRole("button", { name: "Set up passkey" }).click();
  await expect(customer.locator("main").getByText(/Your passkey is ready/)).toBeVisible();
}

export const approveButton = (page: Page) => page.getByRole("button", { name: /^Approve/ });
export const approveReady = (page: Page) =>
  expect(approveButton(page)).not.toHaveAttribute("aria-disabled", "true", { timeout: 8000 });

export async function noAxe(page: Page) {
  const { violations } = await new AxeBuilder({ page }).analyze();
  expect(
    violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`),
  ).toEqual([]);
}

/** A demo-console call straight to the backend. */
export async function demo(path: string, body?: unknown) {
  const res = await fetch(`${BACK}${path}`, {
    method:
      body === undefined && !path.endsWith("/timeline")
        ? "POST"
        : body === undefined
          ? "GET"
          : "POST",
    headers: {
      "x-demo-token": DEMO_TOKEN,
      ...(body === undefined ? {} : { "content-type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return {
    status: res.status,
    json: (await res.json().catch(() => null)) as Record<string, unknown> | null,
  };
}
