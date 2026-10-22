// Takes screenshots of every screen (light and dark, phone and desktop) from a running app.
//   BASE=http://localhost:3000 API=http://localhost:3101 node scripts/shots.mjs <outDir>
// The app must be built with NEXT_PUBLIC_FEATURE_DEMO=true and point at tests/e2e/fake-api.ts.
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

const BASE = process.env.BASE ?? "http://localhost:3000";
const API = process.env.API ?? "http://localhost:3101";
const out = process.argv[2] ?? "shots";
mkdirSync(out, { recursive: true });

const control = (p) => fetch(`${API}/__fake/${p}`, { method: "POST" });
const VIEWPORTS = { phone: { width: 390, height: 844 }, desktop: { width: 1280, height: 800 } };

const browser = await chromium.launch();
for (const scheme of ["light", "dark"]) {
  for (const [vp, viewport] of Object.entries(VIEWPORTS)) {
    await control("reset");
    const make = async () => {
      const context = await browser.newContext({
        viewport,
        colorScheme: scheme,
        baseURL: BASE,
        deviceScaleFactor: vp === "phone" ? 2 : 1,
      });
      return { context, page: await context.newPage() };
    };
    const agent = await make();
    const cust = await make();
    const shot = async (who, name) => {
      await who.page.waitForTimeout(450); // let any settle-in finish
      await who.page.screenshot({ path: `${out}/${scheme}-${vp}-${name}.png` });
    };
    const login = async (who, label, url) => {
      await who.page.goto("/signin");
      await who.page.getByRole("button", { name: label }).click();
      await who.page.waitForURL(url);
    };

    await cust.page.goto("/signin");
    await shot(cust, "01-signin");
    await login(agent, /I am an agent/, "**/agent");
    await login(cust, /I am a customer/, "**/");
    await shot(cust, "02-home-new");

    await shot(agent, "03-agent-new-empty");
    for (const d of ["1", "5", "0", "0", "0"])
      await agent.page
        .getByRole("group", { name: "Amount keypad" })
        .getByRole("button", { name: d })
        .click();
    await shot(agent, "04-agent-new");
    await agent.page.getByRole("button", { name: /^Request/ }).click();
    await agent.page.waitForURL("**/agent/requests/*");
    await shot(agent, "05-agent-waiting");
    const code = (
      await agent.page.getByRole("img", { name: /^Code: / }).getAttribute("aria-label")
    ).replace(/\D/g, "");

    await cust.page.goto("/pay/code");
    await shot(cust, "06-pay-code");
    await cust.page.waitForLoadState("networkidle");
    await cust.page.getByRole("textbox").pressSequentially(code);
    await cust.page.getByRole("heading", { level: 2, name: "What Zolo says" }).waitFor();
    await shot(cust, "07-review-no-passkey");
    const reviewUrl = cust.page.url();

    // A software authenticator, so the passkey step can be shown.
    const cdp = await cust.context.newCDPSession(cust.page);
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
    await cust.page.getByRole("link", { name: "Set up passkey" }).click();
    await cust.page.waitForURL("**/setup/passkey*");
    await shot(cust, "08-passkey-setup");
    await cust.page.getByRole("button", { name: "Set up passkey" }).click();
    await cust.page.getByText("Your passkey is ready.").waitFor();
    await shot(cust, "09-passkey-done");

    await cust.page.goto(reviewUrl);
    await cust.page.getByRole("heading", { level: 2, name: "What Zolo says" }).waitFor();
    await shot(cust, "10-review-waiting");
    await cust.page.waitForFunction(
      () =>
        document.querySelector("button[data-variant=primary]")?.getAttribute("aria-disabled") !==
        "true",
      null,
      { timeout: 8000 },
    );
    await shot(cust, "11-review-ready");
    await cust.page.getByRole("button", { name: /^Approve/ }).click();
    await cust.page.waitForURL("**/result");
    await shot(cust, "12-paid");
    await agent.page.locator("[data-result=paid]").waitFor({ timeout: 8000 });
    await shot(agent, "13-agent-paid");

    await cust.page.goto("/");
    await cust.page.getByText("Declined").or(cust.page.getByText("Paid ₦")).first().waitFor();
    await shot(cust, "14-home-with-payment");
    await cust.page.getByRole("button", { name: "Demo tools" }).click();
    await shot(cust, "15-demo-menu");
    await cust.page.keyboard.press("Escape");

    // The bank has not confirmed yet.
    await control("outcome/SUBMITTED");
    await agent.page.goto("/agent");
    for (const d of ["5", "0", "0", "0"])
      await agent.page
        .getByRole("group", { name: "Amount keypad" })
        .getByRole("button", { name: d })
        .click();
    await agent.page.getByRole("button", { name: /^Request/ }).click();
    await agent.page.waitForURL("**/agent/requests/*");
    const code2 = (
      await agent.page.getByRole("img", { name: /^Code: / }).getAttribute("aria-label")
    ).replace(/\D/g, "");
    await cust.page.goto("/pay/code");
    await cust.page.waitForLoadState("networkidle");
    await cust.page.getByRole("textbox").pressSequentially(code2);
    await cust.page.getByRole("heading", { level: 2, name: "What Zolo says" }).waitFor();
    await cust.page.waitForFunction(
      () =>
        document.querySelector("button[data-variant=primary]")?.getAttribute("aria-disabled") !==
        "true",
      null,
      { timeout: 8000 },
    );
    await cust.page.getByRole("button", { name: /^Approve/ }).click();
    await cust.page.waitForURL("**/result");
    await shot(cust, "16-processing");
    await agent.page
      .getByRole("heading", { level: 1, name: /Processing/ })
      .waitFor({ timeout: 8000 });
    await shot(agent, "17-agent-processing");

    await agent.context.close();
    await cust.context.close();
    console.log("done", scheme, vp);
  }
}
await browser.close();
