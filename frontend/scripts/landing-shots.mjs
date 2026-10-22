// Makes the three app screenshots the landing page shows, from the RUNNING app in demo mode:
// the agent's code screen, the customer's review screen, and the Paid screen.
//   BASE=http://localhost:3000 API=http://localhost:3101 node scripts/landing-shots.mjs
// The app must be built with NEXT_PUBLIC_FEATURE_DEMO=true and talk to tests/e2e/fake-api.ts.
import { chromium } from "@playwright/test";

const BASE = process.env.BASE ?? "http://localhost:3000";
const API = process.env.API ?? "http://localhost:3101";
const OUT = new URL("../public/landing/", import.meta.url).pathname;

await fetch(`${API}/__fake/reset`, { method: "POST" });
const browser = await chromium.launch();
const make = async () => {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    colorScheme: "light",
    reducedMotion: "reduce", // no settle-in mid-frame
    baseURL: BASE,
  });
  return { context, page: await context.newPage() };
};
const agent = await make();
const cust = await make();

/** The demo wrench is for the stage, not for the picture. */
const shot = async (who, name) => {
  await who.page.evaluate(() => document.querySelector("button[aria-haspopup=dialog]")?.remove());
  await who.page.waitForTimeout(300);
  await who.page.screenshot({ path: `${OUT}${name}.png` });
  console.log("wrote", name);
};
const signIn = async (who, label, url) => {
  await who.page.goto("/signin");
  await who.page.waitForLoadState("networkidle");
  await who.page.getByRole("button", { name: label }).click();
  await who.page.waitForURL(url);
};

await signIn(agent, /I am an agent/, "**/agent");
await signIn(cust, /I am a customer/, "**/home");
await agent.page.waitForLoadState("networkidle");
for (const d of ["1", "5", "0", "0", "0"])
  await agent.page
    .getByRole("group", { name: "Amount keypad" })
    .getByRole("button", { name: d })
    .click();
await agent.page.getByRole("button", { name: /^Request/ }).click();
await agent.page.waitForURL("**/agent/requests/*");
await agent.page.getByRole("img", { name: /^Code: / }).waitFor();
const code = (
  await agent.page.getByRole("img", { name: /^Code: / }).getAttribute("aria-label")
).replace(/\D/g, "");
await shot(agent, "shot-agent-code");

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
await cust.page.goto("/setup/passkey");
await cust.page.waitForLoadState("networkidle");
await cust.page.getByRole("button", { name: "Set up passkey" }).click();
await cust.page.getByText("Your passkey is ready.").waitFor();

await cust.page.goto("/pay/code");
await cust.page.waitForLoadState("networkidle");
await cust.page.getByRole("textbox").pressSequentially(code);
await cust.page.getByRole("heading", { level: 2, name: "What Zolo says" }).waitFor();
await cust.page.waitForFunction(
  () =>
    document.querySelector("button[data-variant=primary]")?.getAttribute("aria-disabled") !==
    "true",
  null,
  { timeout: 8000 },
);
await shot(cust, "shot-review");
await cust.page.getByRole("button", { name: /^Approve/ }).click();
await cust.page.waitForURL("**/result");
await cust.page.locator("[data-result=paid]").waitFor();
await shot(cust, "shot-paid");

await browser.close();
