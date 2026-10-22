import { expect, test } from "@playwright/test";
import {
  approveButton,
  approveReady,
  claim,
  demo,
  makeRequest,
  noAxe,
  person,
  resetBackend,
  setUpPasskey,
  virtualAuthenticator,
} from "./helpers";

// Every test here talks to the REAL backend through the frontend's /api proxy: real sessions in an
// HttpOnly cookie, real WebAuthn verification (origin and RP ID are the frontend's), real state machine.

test.beforeEach(async () => {
  await resetBackend();
});

test("NO_PASSKEY: a customer who never set one up is told so, sent to set one up, and comes back to the same request", async ({
  browser,
}) => {
  // This runs first, on a database whose passkeys were cleared when the backend started.
  const agent = await person(browser, "agent");
  const customer = await person(browser, "customer");
  await virtualAuthenticator(customer.context, customer.page);
  const { code } = await makeRequest(agent.page, ["1", "0", "0", "0"]);
  await claim(customer.page, code);
  const reviewUrl = customer.page.url();
  await expect(
    customer.page.getByRole("region", { name: "Set up your passkey first" }),
  ).toBeVisible();
  await noAxe(customer.page);

  await approveReady(customer.page);
  await approveButton(customer.page).click(); // the real backend answers 409 NO_PASSKEY
  await customer.page.waitForURL(/\/setup\/passkey\?next=/);
  await customer.page.getByRole("button", { name: "Set up passkey" }).click();
  await expect(customer.page.locator("main").getByText("Your passkey is ready.")).toBeVisible();
  await customer.page.getByRole("link", { name: "Done" }).click();
  await customer.page.waitForURL(reviewUrl);

  await approveReady(customer.page);
  await approveButton(customer.page).click();
  await customer.page.waitForURL("**/result");
  await expect(customer.page.getByRole("heading", { level: 1 })).toContainText("Paid", {
    timeout: 10_000,
  });
  await agent.context.close();
  await customer.context.close();
});

test("registering works against the real backend; the same phone cannot register twice; a second phone replaces the first", async ({
  browser,
}) => {
  const customer = await person(browser, "customer");
  const authenticator = await virtualAuthenticator(customer.context, customer.page);
  await setUpPasskey(customer.page);
  expect(await authenticator.credentials()).toHaveLength(1);
  await noAxe(customer.page);

  // The same phone: the real backend lists the passkey as one to exclude, so the browser refuses. We say why.
  await customer.page.goto("/setup/passkey");
  await customer.page.waitForLoadState("networkidle");
  await customer.page.getByRole("button", { name: "Set up passkey" }).click();
  await expect(
    customer.page.locator("main").getByText("This phone already has your passkey."),
  ).toBeVisible();
  expect(await authenticator.credentials()).toHaveLength(1);

  // Another phone: a second authenticator in a fresh browser. The backend replaces the first passkey.
  const other = await person(browser, "customer");
  await virtualAuthenticator(other.context, other.page);
  await other.page.goto("/setup/passkey");
  await other.page.waitForLoadState("networkidle");
  await other.page.getByRole("button", { name: "Set up passkey" }).click();
  await expect(
    other.page.locator("main").getByText("Your passkey is ready. It replaced your old one."),
  ).toBeVisible();
  expect(
    [...customer.problems, ...other.problems].filter((p) => !/status of 4\d\d|409|400/.test(p)),
  ).toEqual([]);
  await customer.context.close();
  await other.context.close();
});

test("the full journey: ask, hear the real readback, approve with the passkey, Paid on both screens", async ({
  browser,
}) => {
  const agent = await person(browser, "agent");
  const customer = await person(browser, "customer");
  await virtualAuthenticator(customer.context, customer.page);
  const { code } = await makeRequest(agent.page, ["1", "5", "0", "0", "0"]);
  await setUpPasskey(customer.page);
  await claim(customer.page, code);

  // The readback text and the words come from the backend, not from the frontend.
  await expect(
    customer.page.getByText(
      /Bisi Ventures is asking for fifteen thousand naira\. One five, zero zero zero\./,
    ),
  ).toBeVisible();
  await expect(customer.page.getByRole("heading", { level: 1 })).toHaveAccessibleName(
    "Bisi Ventures is asking for fifteen thousand naira",
  );
  await approveReady(customer.page);
  await noAxe(customer.page);
  await approveButton(customer.page).click();

  await customer.page.waitForURL("**/result");
  await expect(customer.page.getByRole("heading", { level: 1 })).toContainText(
    /Paid\. You sent ₦15,000 to bisi ventures\./i,
    { timeout: 10_000 },
  );
  await expect(agent.page.getByRole("heading", { level: 1, name: "Paid" })).toBeVisible({
    timeout: 10_000,
  });
  await customer.page.goto("/home");
  await expect(customer.page.getByText(/Paid ₦15,000 to bisi ventures/i).first()).toBeVisible();
  expect([...agent.problems, ...customer.problems]).toEqual([]);
  await agent.context.close();
  await customer.context.close();
});

test("a passkey on another phone: this phone cannot sign, so nothing is sent and the customer is told", async ({
  browser,
}) => {
  const agent = await person(browser, "agent");
  const customer = await person(browser, "customer");
  const authenticator = await virtualAuthenticator(customer.context, customer.page);
  const { code } = await makeRequest(agent.page, ["1", "2", "0", "0"]);
  await setUpPasskey(customer.page);
  await claim(customer.page, code);
  await approveReady(customer.page);
  // The credential is wiped from this "phone": the backend still knows it, the phone does not.
  for (const c of await authenticator.credentials()) expect(c.credentialId).toBeTruthy();
  await authenticator.clear();
  await approveButton(customer.page).click();
  await expect(customer.page.getByTestId("review-problem")).toBeVisible({ timeout: 15_000 });
  const id = customer.page.url().split("/").pop()!;
  const timeline = await demo(`/demo/requests/${id}/timeline`);
  expect((timeline.json!.request as { state: string }).state).toBe("READ_BACK"); // nothing moved
  await agent.context.close();
  await customer.context.close();
});

test("cancelling the fingerprint or face prompt sends nothing, and the customer can try again", async ({
  browser,
}) => {
  const agent = await person(browser, "agent");
  const customer = await person(browser, "customer");
  const authenticator = await virtualAuthenticator(customer.context, customer.page);
  const { code } = await makeRequest(agent.page, ["2", "0", "0", "0"]);
  await setUpPasskey(customer.page);
  await claim(customer.page, code);
  await approveReady(customer.page);

  await authenticator.refuse();
  await approveButton(customer.page).click();
  await expect(
    customer.page.locator("main").getByText("Cancelled. Nothing was sent. You can try again."),
  ).toBeVisible({ timeout: 10_000 });
  await expect(customer.page.locator("[data-live-region=assertive]")).toContainText("Cancelled");
  const id = customer.page.url().split("/").pop()!;
  const timeline = await demo(`/demo/requests/${id}/timeline`);
  expect((timeline.json!.request as { state: string }).state).toBe("READ_BACK"); // nothing moved

  await authenticator.allow();
  await approveButton(customer.page).click();
  await customer.page.waitForURL("**/result");
  await expect(customer.page.getByRole("heading", { level: 1 })).toContainText("Paid", {
    timeout: 10_000,
  });
  await agent.context.close();
  await customer.context.close();
});

test("the amount changed after the readback: the real backend refuses with INTENT_CHANGED and nothing is sent", async ({
  browser,
}) => {
  const agent = await person(browser, "agent");
  const customer = await person(browser, "customer");
  await virtualAuthenticator(customer.context, customer.page);
  const { code } = await makeRequest(agent.page, ["1", "0", "0", "0", "0"]);
  await setUpPasskey(customer.page);
  await claim(customer.page, code);
  await approveReady(customer.page);
  const id = customer.page.url().split("/").pop()!;
  expect((await demo(`/demo/requests/${id}/tamper`, {})).status).toBe(200);

  await approveButton(customer.page).click();
  await customer.page.waitForURL("**/result?r=changed");
  await expect(customer.page.getByRole("heading", { level: 1 })).toContainText(
    "This payment changed after you heard it. Nothing was sent.",
  );
  await noAxe(customer.page);
  const timeline = await demo(`/demo/requests/${id}/timeline`);
  expect((timeline.json!.request as { state: string }).state).toBe("READ_BACK");
  await agent.context.close();
  await customer.context.close();
});

test("replaying an accepted approval is refused (ALREADY_USED): no second payment", async ({
  browser,
}) => {
  const agent = await person(browser, "agent");
  const customer = await person(browser, "customer");
  await virtualAuthenticator(customer.context, customer.page);
  const { code, id } = await makeRequest(agent.page, ["3", "0", "0", "0"]);
  await setUpPasskey(customer.page);
  await claim(customer.page, code);
  await approveReady(customer.page);
  await approveButton(customer.page).click();
  await customer.page.waitForURL("**/result");
  await expect(customer.page.getByRole("heading", { level: 1 })).toContainText("Paid", {
    timeout: 10_000,
  });

  const replay = await demo(`/demo/requests/${id}/replay`);
  expect(replay.status).toBe(409);
  expect(replay.json).toMatchObject({ code: "ALREADY_USED" });

  // ...and the demo console shows it, with the real code.
  const console_ = await customer.context.newPage();
  await console_.goto("/demo");
  await console_.waitForLoadState("networkidle");
  await console_.getByLabel("Demo token").fill("e2e-demo-token");
  await console_.getByLabel("Request id").fill(id);
  await console_.getByRole("button", { name: "Replay the approval" }).click();
  await expect(console_.getByTestId("demo-message")).toContainText("refused (ALREADY_USED)");
  await expect(console_.getByText("SETTLED", { exact: true }).first()).toBeVisible({
    timeout: 6000,
  });
  await noAxe(console_);
  await agent.context.close();
  await customer.context.close();
});

test("a request that expires while the customer is listening ends on 'expired', and the backend says 410", async ({
  browser,
}) => {
  const agent = await person(browser, "agent");
  const customer = await person(browser, "customer");
  await virtualAuthenticator(customer.context, customer.page);
  const { code } = await makeRequest(agent.page, ["4", "0", "0", "0"]);
  await setUpPasskey(customer.page);
  await claim(customer.page, code);
  await approveReady(customer.page);
  const id = customer.page.url().split("/").pop()!;
  expect((await demo(`/demo/requests/${id}/expire`)).status).toBe(200);

  await approveButton(customer.page).click();
  await customer.page.waitForURL("**/result", { timeout: 10_000 });
  await expect(customer.page.getByRole("heading", { level: 1 })).toContainText(
    "This request expired. Nothing was sent.",
  );
  await expect(agent.page.getByRole("heading", { level: 1 })).toContainText("expired", {
    timeout: 6000,
  });
  await agent.context.close();
  await customer.context.close();
});

test("declining is one tap and nothing is sent", async ({ browser }) => {
  const agent = await person(browser, "agent");
  const customer = await person(browser, "customer");
  const { code } = await makeRequest(agent.page, ["2", "5", "0", "0"]);
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

test("the real backend's contract: unsupported readback languages are refused, wrong codes are specific, and sessions are cookies", async ({
  browser,
}) => {
  const agent = await person(browser, "agent");
  const customer = await person(browser, "customer");
  const { code, id } = await makeRequest(agent.page, ["5", "0", "0", "0"]);

  // A wrong code: the real CODE_NOT_FOUND, spoken specifically.
  await customer.page.goto("/pay/code");
  await customer.page.waitForLoadState("networkidle");
  await customer.page
    .getByRole("textbox", { name: /4-digit code/ })
    .pressSequentially(code === "9999" ? "9998" : "9999");
  await expect(
    customer.page
      .locator("main")
      .getByText("No request has that code. Check the 4 digits with the agent."),
  ).toBeVisible();

  await claim(customer.page, code);
  const statuses = await customer.page.evaluate(async (rid) => {
    const get = async (lang: string) =>
      (await fetch(`/api/requests/${rid}/readback?lang=${lang}`)).status;
    const body = async (lang: string) =>
      (await (await fetch(`/api/requests/${rid}/readback?lang=${lang}`)).json()) as {
        lang: string;
        fallback_from: string | null;
      };
    return {
      en: await get("en"),
      pcm: await get("pcm"),
      yo: await get("yo"),
      ha: await get("ha"),
      fr: await get("fr"),
      yoBody: await body("yo"),
    };
  }, id);
  // Yoruba, Hausa and Igbo are accepted: never a 422. Only a language we do not have is refused.
  expect(statuses).toMatchObject({ en: 200, pcm: 200, yo: 200, ha: 200, fr: 422 });
  // ...and the answer is either that language, or English with `fallback_from` saying so.
  const { lang, fallback_from } = statuses.yoBody;
  expect(lang === "yo" ? fallback_from === null : lang === "en" && fallback_from === "yo").toBe(
    true,
  );

  const cookies = await customer.context.cookies();
  const session = cookies.find((c) => c.name === "zolo_session");
  expect(session?.httpOnly).toBe(true);
  expect(session?.sameSite).toBe("Lax");
  expect(await customer.page.evaluate(() => document.cookie)).not.toContain("zolo_session");
  await agent.context.close();
  await customer.context.close();
});
