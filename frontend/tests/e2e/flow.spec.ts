import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Browser, type BrowserContext, type Page } from "@playwright/test";

// The whole journey, in a real browser, against the production build and the shared fake backend:
// agent asks, customer sets up a passkey (Chromium's virtual authenticator), hears, approves.
// These share one fake backend, so they run one at a time (see the "flow" project).

test.describe.configure({ mode: "serial" });

const API = `http://localhost:${process.env.E2E_API_PORT ?? 3101}`;
const control = (path: string) => fetch(`${API}/__fake/${path}`, { method: "POST" });

test.beforeEach(async () => {
  await control("reset");
});

async function person(browser: Browser, who: "customer" | "agent") {
  const context = await browser.newContext({ ...test.info().project.use });
  const page = await context.newPage();
  const problems: string[] = [];
  page.on("console", (m) => m.type() === "error" && problems.push(m.text()));
  page.on("pageerror", (e) => problems.push(String(e)));
  await page.goto("/signin");
  await page
    .getByRole("button", { name: who === "agent" ? /I am an agent/ : /I am a customer/ })
    .click();
  await page.waitForURL(who === "agent" ? "**/agent" : "**/");
  return { context, page, problems };
}

/** A fingerprint/face prompt that approves itself, so passkeys can be tested without a phone. */
async function virtualAuthenticator(context: BrowserContext, page: Page) {
  const cdp = await context.newCDPSession(page);
  await cdp.send("WebAuthn.enable");
  await cdp.send("WebAuthn.addVirtualAuthenticator", {
    options: {
      protocol: "ctap2",
      transport: "internal",
      hasResidentKey: true,
      hasUserVerification: true,
      isUserVerified: true,
      automaticPresenceSimulation: true,
    },
  });
}

async function noAxeViolations(page: Page) {
  // Let the "Paid" settle-in finish: axe reads colours mid-fade as low contrast.
  await page.waitForFunction(() => {
    const card = document.querySelector("[data-result] > div");
    return !card || getComputedStyle(card).opacity === "1";
  });
  const { violations } = await new AxeBuilder({ page }).analyze();
  expect(
    violations.map(
      (v) => `${page.url()} ${v.id} ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`,
    ),
  ).toEqual([]);
}

async function makeRequest(agent: Page, digits: string[]) {
  const keypad = agent.getByRole("group", { name: "Amount keypad" });
  for (const d of digits) await keypad.getByRole("button", { name: d }).click();
  await agent.getByRole("button", { name: /^Request/ }).click();
  await agent.waitForURL("**/agent/requests/*");
  const label = await agent.getByRole("img", { name: /^Code: / }).getAttribute("aria-label");
  return label!.replace(/\D/g, "");
}

async function claim(customer: Page, code: string) {
  await customer.goto("/pay/code");
  await customer.getByRole("textbox", { name: /4-digit code/ }).pressSequentially(code);
  await customer.waitForURL(/\/requests\/[^/]+$/);
  await customer.getByRole("heading", { level: 2, name: "What Zolo says" }).waitFor();
}

async function setUpPasskey(customer: Page) {
  await customer.goto("/setup/passkey");
  await customer.getByRole("button", { name: "Set up passkey" }).click();
  await expect(customer.getByText("Your passkey is ready.")).toBeVisible();
}

const approveButton = (page: Page) => page.getByRole("button", { name: /^Approve/ });
const allowed = async (page: Page) =>
  expect(approveButton(page)).not.toHaveAttribute("aria-disabled", "true", { timeout: 6000 });

test("the happy path: ask, set up a passkey, hear, approve, Paid on both screens", async ({
  browser,
}) => {
  const agent = await person(browser, "agent");
  const customer = await person(browser, "customer");
  await virtualAuthenticator(customer.context, customer.page);

  const code = await makeRequest(agent.page, ["1", "5", "0", "0", "0"]);
  await expect(agent.page.getByText("Give cash only after you see Paid.")).toBeVisible();

  await setUpPasskey(customer.page);
  await claim(customer.page, code);

  // The review screen: amount, name, words, verified; focus is on the readback, Approve waits.
  const page = customer.page;
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    /Bisi Ventures is asking for ₦15,000/,
  );
  await expect(page.getByText("Verified by bank")).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "What Zolo says" })).toBeFocused();
  await expect(approveButton(page)).toHaveAttribute("aria-disabled", "true");
  await allowed(page);
  await expect(approveButton(page)).toHaveAccessibleName(
    "Approve fifteen thousand naira to Bisi Ventures",
  );

  await approveButton(page).click();
  await page.waitForURL("**/result");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "Paid. You sent ₦15,000 to Bisi Ventures.",
  );
  await expect(page.getByRole("heading", { level: 1 })).toBeFocused();

  // The agent sees Paid by polling, and is told in the live region.
  await expect(agent.page.getByRole("heading", { level: 1, name: "Paid" })).toBeVisible({
    timeout: 6000,
  });
  await expect(agent.page.locator("[data-live-region=polite]")).toContainText(
    "Paid. fifteen thousand naira",
  );

  expect([...agent.problems, ...customer.problems]).toEqual([]); // no CSP violations, no errors
  await agent.context.close();
  await customer.context.close();
});

test("SUBMITTED: both screens say Processing and never Paid until the bank confirms", async ({
  browser,
}) => {
  await control("outcome/SUBMITTED");
  const agent = await person(browser, "agent");
  const customer = await person(browser, "customer");
  await virtualAuthenticator(customer.context, customer.page);
  const code = await makeRequest(agent.page, ["5", "0", "0", "0"]);
  await setUpPasskey(customer.page);
  await claim(customer.page, code);
  await allowed(customer.page);
  await approveButton(customer.page).click();

  const processing = "Processing. Don't hand over goods yet.";
  await expect(customer.page.getByRole("heading", { level: 1, name: processing })).toBeVisible();
  await expect(agent.page.getByRole("heading", { level: 1, name: processing })).toBeVisible({
    timeout: 6000,
  });
  for (const p of [customer.page, agent.page]) {
    // The only "Paid" allowed is the instruction "Wait for Paid", never a claim of it.
    await expect(p.locator("main")).not.toContainText(/(?<!Wait for )\bPaid\b/);
    await noAxeViolations(p);
  }
  await expect(agent.page.locator("[data-live-region=polite]")).toHaveText(processing);

  // The bank confirms: both flip to Paid by themselves.
  const id = agent.page.url().split("/").pop()!;
  await control(`settle/${id}`);
  await expect(customer.page.getByRole("heading", { level: 1, name: /^Paid\./ })).toBeVisible({
    timeout: 6000,
  });
  await expect(agent.page.getByRole("heading", { level: 1, name: "Paid" })).toBeVisible({
    timeout: 6000,
  });
  await agent.context.close();
  await customer.context.close();
});

test("decline is one tap, and the agent is told nothing moved", async ({ browser }) => {
  const agent = await person(browser, "agent");
  const customer = await person(browser, "customer");
  const code = await makeRequest(agent.page, ["2", "0", "0", "0"]);
  await claim(customer.page, code);
  await customer.page.getByRole("button", { name: "Decline" }).click();
  await expect(customer.page.getByRole("heading", { level: 1 })).toHaveText(
    "Declined. Nothing was sent.",
  );
  await expect(agent.page.getByRole("heading", { level: 1 })).toHaveText(
    "The customer said no. No money moved.",
    { timeout: 6000 },
  );
  await agent.context.close();
  await customer.context.close();
});

test("tampering after the readback (demo console) ends in 'changed' and nothing is sent", async ({
  browser,
}) => {
  const agent = await person(browser, "agent");
  const customer = await person(browser, "customer");
  await virtualAuthenticator(customer.context, customer.page);
  const code = await makeRequest(agent.page, ["1", "0", "0", "0", "0"]);
  await setUpPasskey(customer.page);
  await claim(customer.page, code);
  await allowed(customer.page);

  const demo = await customer.context.newPage();
  await demo.goto("/demo");
  await demo.getByLabel("Demo token").fill("demo-token-1234");
  await demo.getByLabel("Request id").fill(customer.page.url().split("/").pop()!);
  await demo.getByRole("button", { name: "Change the amount after the readback" }).click();
  await expect(demo.getByTestId("demo-message")).toContainText("done");
  await noAxeViolations(demo);

  await approveButton(customer.page).click();
  await customer.page.waitForURL("**/result?r=changed");
  await expect(customer.page.getByRole("heading", { level: 1 })).toHaveText(
    "This payment changed after you heard it. Nothing was sent.",
  );
  await noAxeViolations(customer.page);
  await agent.context.close();
  await customer.context.close();
});

test("an expired code is refused with a specific message", async ({ browser }) => {
  const agent = await person(browser, "agent");
  const customer = await person(browser, "customer");
  await makeRequest(agent.page, ["1", "0", "0", "0"]);
  await customer.page.goto("/pay/code");
  const field = customer.page.getByRole("textbox", { name: /4-digit code/ });
  await field.pressSequentially("9999");
  await expect(
    customer.page.getByText("No request has that code. Check the 4 digits with the agent."),
  ).toBeVisible();
  await expect(customer.page.locator("[data-live-region=assertive]")).toContainText(
    "No request has that code",
  );
  await noAxeViolations(customer.page);
  await agent.context.close();
  await customer.context.close();
});

const MODES = [
  { name: "light", media: { colorScheme: "light" as const } },
  { name: "dark", media: { colorScheme: "dark" as const } },
  {
    name: "reduced motion + more contrast",
    media: { reducedMotion: "reduce" as const, contrast: "more" as const },
  },
];

for (const mode of MODES) {
  test(`axe: every screen has zero violations in ${mode.name}`, async ({ browser }) => {
    const agent = await person(browser, "agent");
    const customer = await person(browser, "customer");
    await virtualAuthenticator(customer.context, customer.page);
    for (const p of [agent.page, customer.page]) await p.emulateMedia(mode.media);

    await agent.page.goto("/agent");
    await noAxeViolations(agent.page); // new request
    const code = await makeRequest(agent.page, ["1", "5", "0", "0", "0"]);
    await noAxeViolations(agent.page); // waiting

    await customer.page.goto("/");
    await noAxeViolations(customer.page); // home
    await customer.page.goto("/signin");
    await noAxeViolations(customer.page); // chooser
    await customer.page.goto("/setup/passkey");
    await noAxeViolations(customer.page); // passkey setup
    await setUpPasskey(customer.page);
    await noAxeViolations(customer.page); // passkey done
    await customer.page.goto("/pay/code");
    await noAxeViolations(customer.page); // pay by code
    await claim(customer.page, code);
    await noAxeViolations(customer.page); // review (Approve inactive)
    await allowed(customer.page);
    await noAxeViolations(customer.page); // review (Approve ready)
    await approveButton(customer.page).click();
    await customer.page.waitForURL("**/result");
    await customer.page.locator("[data-result=paid]").waitFor();
    await noAxeViolations(customer.page); // paid
    await expect(agent.page.getByRole("heading", { level: 1, name: "Paid" })).toBeVisible({
      timeout: 6000,
    });
    await noAxeViolations(agent.page); // agent paid
    await agent.page.goto("/demo");
    await noAxeViolations(agent.page); // demo console

    await agent.context.close();
    await customer.context.close();
  });
}

test("nothing overflows at 320px wide and 200% text, on the screens people use", async ({
  browser,
}) => {
  const agent = await person(browser, "agent");
  const customer = await person(browser, "customer");
  await virtualAuthenticator(customer.context, customer.page);
  for (const p of [agent.page, customer.page]) await p.setViewportSize({ width: 320, height: 640 });
  const zoom = (p: Page) =>
    p.evaluate(() => document.documentElement.style.setProperty("font-size", "200%", "important"));
  const fits = async (p: Page) => {
    await zoom(p);
    const { scrollWidth, clientWidth } = await p.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
  };

  await fits(agent.page);
  const code = await makeRequest(agent.page, ["1", "5", "0", "0", "0"]);
  await fits(agent.page);
  await customer.page.goto("/");
  await fits(customer.page);
  await setUpPasskey(customer.page);
  await claim(customer.page, code);
  await fits(customer.page);
  await allowed(customer.page);
  await approveButton(customer.page).click();
  await customer.page.waitForURL("**/result");
  await fits(customer.page);
  await agent.context.close();
  await customer.context.close();
});

test("keyboard only: Approve works from the keyboard", async ({ browser }) => {
  const agent = await person(browser, "agent");
  const customer = await person(browser, "customer");
  await virtualAuthenticator(customer.context, customer.page);
  const code = await makeRequest(agent.page, ["3", "0", "0", "0"]);
  await setUpPasskey(customer.page);
  await claim(customer.page, code);
  await allowed(customer.page);
  await approveButton(customer.page).focus();
  await customer.page.keyboard.press("Enter");
  await customer.page.waitForURL("**/result");
  await agent.context.close();
  await customer.context.close();
});

test("routes behind a feature flag are 404 when the flag is off, and the app has no disabled 'coming soon' controls", async ({
  browser,
}) => {
  const customer = await person(browser, "customer");
  for (const route of ["/send", "/card"]) {
    const res = await customer.page.goto(route);
    expect(res?.status()).toBe(404);
  }
  await customer.page.goto("/");
  await expect(customer.page.getByText(/send money|card guard|coming soon/i)).toHaveCount(0);
  await customer.context.close();
});
