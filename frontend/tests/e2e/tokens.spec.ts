import { expect, test, type Page } from "@playwright/test";

const rootVar = (page: Page, name: string) =>
  page.evaluate((n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim(), name);
/** 200% text, the way a user's browser setting does it. (addStyleTag would be refused by our strict CSP.) */
const zoomText = (page: Page) =>
  page.evaluate(() => document.documentElement.style.setProperty("font-size", "200%", "important"));
const htmlBg = (page: Page) =>
  page.evaluate(() => getComputedStyle(document.documentElement).backgroundColor);

test("light mode: a light backdrop, graphite-black text", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/signin");
  expect(await htmlBg(page)).toBe("rgb(233, 233, 238)"); // the desk the frame sits on
  expect(await rootVar(page, "--color-text")).toBe("#1c1c1e");
  expect(await rootVar(page, "--color-brand-text")).toBe("#d7191e");
});

test("dark mode follows the system: black backdrop, light text, the lighter red for text", async ({
  page,
}) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/signin");
  expect(await htmlBg(page)).toBe("rgb(0, 0, 0)");
  expect(await rootVar(page, "--color-text")).toBe("#f5f5f7");
  expect(await rootVar(page, "--color-brand-text")).toBe("#ff5a5f");
  expect(await rootVar(page, "--color-brand")).toBe("#d7191e"); // the fill is the same red in both
});

test("more contrast: a thicker focus ring and secondary text as strong as primary text", async ({
  page,
}) => {
  await page.emulateMedia({ contrast: "more" });
  await page.goto("/signin");
  expect(await rootVar(page, "--focus-width")).toBe("4px");
  expect(await rootVar(page, "--color-text-secondary")).toBe(await rootVar(page, "--color-text"));
});

test("reduced motion: no press scale", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/signin");
  expect(await rootVar(page, "--motion-press-scale")).toBe("1");
  await page.emulateMedia({ reducedMotion: "no-preference" });
  expect(Number(await rootVar(page, "--motion-press-scale"))).toBe(0.97); // Chrome prints it as ".97"
});

test("the title style is 1.75rem: 28px at the default size, 56px at 200% text", async ({
  page,
}) => {
  await page.goto("/signin");
  const size = () =>
    page
      .getByRole("heading", { level: 1 })
      .evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
  expect(await size()).toBe(28);
  await zoomText(page);
  expect(await size()).toBe(56); // rem all the way down: it follows the user's text size
});

test("system fonts only", async ({ page }) => {
  await page.goto("/signin");
  const family = await page.evaluate(() => getComputedStyle(document.body).fontFamily);
  expect(family).toContain("-apple-system");
  expect(family).toContain("sans-serif");
});

test("works at 320px wide AND 200% text: no horizontal scrolling, nothing cut off", async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 640 });
  await page.goto("/signin");
  await zoomText(page);
  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
  await expect(page.getByRole("heading", { level: 1 })).toBeInViewport();
});
