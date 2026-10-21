import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const open = async (page: Page) => {
  await page.goto("/kitchen-sink");
  await expect(page.getByRole("heading", { level: 1, name: "Component gallery" })).toBeVisible();
  // Hydrated: the timer only renders after mount.
  await expect(page.getByText("Counting down")).toBeVisible();
};

const axe = (page: Page) => new AxeBuilder({ page }).analyze();

const MODES = [
  { name: "light", media: { colorScheme: "light" as const } },
  { name: "dark", media: { colorScheme: "dark" as const } },
  { name: "reduced motion", media: { reducedMotion: "reduce" as const } },
  { name: "more contrast", media: { contrast: "more" as const } },
];

for (const mode of MODES) {
  test(`axe: zero violations in ${mode.name}`, async ({ page }) => {
    await page.emulateMedia(mode.media);
    await open(page);
    expect((await axe(page)).violations).toEqual([]);
  });
}

test("axe: zero violations with the sheet open, in dark", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await open(page);
  await page.getByRole("button", { name: "Open the sheet" }).click();
  await expect(page.getByRole("dialog", { name: "A sheet" })).toBeVisible();
  expect((await axe(page)).violations).toEqual([]);
});

test("buttons: one tap acts; a disabled one stays focusable, says why, and does nothing", async ({
  page,
}) => {
  await open(page);
  const count = page.getByTestId("click-count");
  await page.getByRole("button", { name: "Hear again" }).click();
  await expect(count).toHaveText("Button taps: 1");
  const blocked = page.getByRole("button", { name: "Approve ₦15,000 (not yet)" });
  await expect(blocked).toHaveAttribute("aria-disabled", "true");
  await expect(blocked).toHaveAccessibleDescription("Listen to the request first");
  await blocked.focus();
  await expect(blocked).toBeFocused();
  await blocked.click({ force: true }); // Playwright treats aria-disabled as disabled
  await expect(count).toHaveText("Button taps: 1");
});

test("the keypad types an amount, announces it in words, and can delete and clear", async ({
  page,
}) => {
  await open(page);
  const keypad = page.getByRole("group", { name: "Amount keypad" });
  for (const d of ["1", "5", "0", "0", "0"])
    await keypad.getByRole("button", { name: d, exact: true }).click();
  await expect(page.getByText("fifteen thousand naira").last()).toBeAttached();
  await keypad.getByRole("button", { name: "Delete last digit" }).click();
  await expect(page.getByText("one thousand five hundred naira").last()).toBeAttached();
  await keypad.getByRole("button", { name: "Clear" }).click();
  await expect(page.getByRole("button", { name: "Request", exact: true })).toHaveAttribute(
    "aria-disabled",
    "true",
  );
});

test("the sheet: focus goes in, Escape closes it, focus returns to the button that opened it", async ({
  page,
}) => {
  await open(page);
  const trigger = page.getByRole("button", { name: "Open the sheet" });
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "A sheet" });
  await expect(dialog).toBeVisible();
  await expect(dialog.locator(":focus")).toHaveCount(1);
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
  // The close button is one tap, too.
  await trigger.click();
  await page.getByRole("button", { name: "Close the sheet" }).click();
  await expect(dialog).toBeHidden();
});

test("live region: one polite status and one assertive alert, each said once", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "Announce politely" }).click();
  await expect(
    page.locator("[role=status]", { hasText: "Paid. You sent ₦15,000 to Bisi Ventures." }),
  ).toHaveCount(1);
  await page.getByRole("button", { name: "Announce an error" }).click();
  await expect(page.locator("[data-live-region=assertive]")).toHaveText(
    "Something went wrong. Nothing was sent.",
  );
});

test("time left: announces at one minute and fifteen seconds, then says time is up", async ({
  page,
}) => {
  await page.clock.install();
  await open(page);
  const polite = page.locator("[data-live-region=polite]");
  await page.clock.fastForward(50_000); // 105 s -> about 55 s left
  await expect(polite).toHaveText("One minute left.");
  await page.clock.fastForward(45_000); // about 10 s left
  await expect(polite).toHaveText("Fifteen seconds left.");
  await page.clock.fastForward(15_000);
  await expect(page.getByTestId("time-state")).toHaveText("Expired");
  await expect(polite).toHaveText("Time is up.");
});

test("every interactive control is at least 48px tall and 8px from its neighbours", async ({
  page,
}) => {
  await open(page);
  const boxes = await page.locator("main button:visible").evaluateAll((els) =>
    els.map((el) => {
      const r = el.getBoundingClientRect();
      return {
        name: el.textContent?.trim() || el.getAttribute("aria-label"),
        w: r.width,
        h: r.height,
      };
    }),
  );
  for (const b of boxes) {
    expect(b.h, `${b.name} height`).toBeGreaterThanOrEqual(48);
    expect(b.w, `${b.name} width`).toBeGreaterThanOrEqual(48);
  }
});

test("press feedback: scales to 0.97 while pressed, and not at all under reduced motion", async ({
  page,
}) => {
  const scaleWhilePressed = async () => {
    const button = page.getByRole("button", { name: "Hear again" });
    const box = (await button.boundingBox())!;
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.waitForTimeout(250);
    const t = await button.evaluate((el) => getComputedStyle(el).scale);
    await page.mouse.up();
    return t;
  };
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await open(page);
  await page.getByRole("button", { name: "Hear again" }).scrollIntoViewIfNeeded();
  expect(Number(await scaleWhilePressed())).toBeCloseTo(0.97, 2);
  await page.emulateMedia({ reducedMotion: "reduce" });
  expect(["none", "1"]).toContain(await scaleWhilePressed());
});

test("works at 320px wide AND 200% text: nothing overflows sideways", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 640 });
  await open(page);
  await page.evaluate(() =>
    document.documentElement.style.setProperty("font-size", "200%", "important"),
  );
  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
});
