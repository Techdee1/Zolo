import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

// WCAG 2.2 AA, as axe tags it. Zero violations of ANY impact is the bar here, stricter than the
// "no serious or critical" gate in the PRD.
const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

async function scan(page: import("@playwright/test").Page) {
  return new AxeBuilder({ page }).withTags(WCAG).analyze();
}

for (const scheme of ["light", "dark"] as const) {
  test(`home has no accessibility violations (${scheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await page.goto("/");
    const { violations } = await scan(page);
    expect(violations, JSON.stringify(violations, null, 2)).toEqual([]);
  });
}

test("home has no accessibility violations with reduced motion and more contrast", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce", contrast: "more" });
  await page.goto("/");
  expect((await scan(page)).violations).toEqual([]);
});

test("the page is a proper document: language, title, one h1, a main landmark", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page).toHaveTitle(/Zolo/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
  await expect(page.getByRole("main")).toBeVisible();
});

test("people can zoom: the viewport does not forbid scaling", async ({ page }) => {
  await page.goto("/");
  const content = await page.locator('meta[name="viewport"]').getAttribute("content");
  expect(content).not.toMatch(/user-scalable\s*=\s*(no|0)/i);
  expect(content).not.toMatch(/maximum-scale/i);
});

test("the first Tab stop is the skip link, and it works", async ({ page, isMobile }) => {
  test.skip(isMobile, "keyboard navigation is a desktop concern");
  await page.goto("/");
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to main content" });
  await expect(skip).toBeFocused();
  await expect(skip).toBeInViewport();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#main$/);
});

test("the focus ring is clearly visible", async ({ page, isMobile }) => {
  test.skip(isMobile, "keyboard navigation is a desktop concern");
  await page.goto("/");
  await page.keyboard.press("Tab");
  const outline = await page.getByRole("link", { name: "Skip to main content" }).evaluate((el) => {
    const s = getComputedStyle(el);
    return { width: parseFloat(s.outlineWidth), style: s.outlineStyle };
  });
  expect(outline.style).toBe("solid");
  expect(outline.width).toBeGreaterThanOrEqual(3);
});

test("security headers and a strict, nonce-based CSP are on the page", async ({ request }) => {
  const res = await request.get("/");
  const h = res.headers();
  expect(h["x-frame-options"]).toBe("DENY");
  expect(h["x-content-type-options"]).toBe("nosniff");
  expect(h["referrer-policy"]).toBe("no-referrer");
  expect(h["strict-transport-security"]).toContain("max-age=");
  expect(h["x-powered-by"]).toBeUndefined();
  const csp = h["content-security-policy"] ?? "";
  const scripts = csp.split("; ").find((d) => d.startsWith("script-src")) ?? "";
  expect(scripts).toMatch(/'nonce-[A-Za-z0-9+/=]+'/);
  expect(scripts).not.toContain("'unsafe-inline'");
  expect(scripts).not.toContain("'unsafe-eval'");
  expect(csp).toContain("frame-ancestors 'none'");
});

test("every page request gets a fresh nonce", async ({ request }) => {
  const nonce = async () =>
    ((await request.get("/")).headers()["content-security-policy"] ?? "").match(
      /'nonce-([^']+)'/,
    )?.[1];
  const [a, b] = [await nonce(), await nonce()];
  expect(a).toBeTruthy();
  expect(a).not.toBe(b);
});

test("the page runs under the CSP with no violations and no console errors", async ({ page }) => {
  const problems: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error" || /content security policy/i.test(m.text())) problems.push(m.text());
  });
  page.on("pageerror", (e) => problems.push(e.message));
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  expect(problems).toEqual([]);
});

test("no third-party requests: nothing leaves this origin", async ({ page, baseURL }) => {
  const foreign: string[] = [];
  page.on("request", (r) => {
    if (
      !r.url().startsWith(baseURL ?? "") &&
      !r.url().startsWith("data:") &&
      !r.url().startsWith("blob:")
    )
      foreign.push(r.url());
  });
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  expect(foreign).toEqual([]);
});

test("the app really runs under the CSP: scripts execute and React hydrates", async ({ page }) => {
  await page.goto("/");
  // Next sets window.next once its client runtime has started. If the CSP blocked the scripts
  // (as a statically prerendered page would), this never appears even though the HTML looks fine.
  await page.waitForFunction(() =>
    Boolean((window as unknown as { next?: { version?: string } }).next?.version),
  );
});
