import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// The landing page, in a real browser, under the strict CSP. It is plain HTML and CSS, so the
// no-JavaScript tests matter as much as the rest.

/** Scroll to the bottom so the scroll-linked reveals are all past their start: axe reads colours at the moment it runs. */
async function settle(page: Page) {
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
  await page.waitForTimeout(300);
}
const scan = async (page: Page) => {
  const { violations } = await new AxeBuilder({ page }).analyze();
  return violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`);
};

const MODES = [
  { name: "light", media: { colorScheme: "light" as const } },
  { name: "dark", media: { colorScheme: "dark" as const } },
  { name: "reduced motion", media: { reducedMotion: "reduce" as const } },
  { name: "more contrast", media: { contrast: "more" as const } },
];

for (const mode of MODES) {
  test(`axe: zero violations in ${mode.name}, at the top and at the bottom`, async ({ page }) => {
    await page.emulateMedia(mode.media);
    await page.goto("/");
    expect(await scan(page)).toEqual([]);
    await settle(page);
    expect(await scan(page)).toEqual([]);
  });
}

test("is the root route, with a skip link, one h1, a main landmark and the page title", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page).toHaveTitle(/anyone can propose a payment/i);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Anyone can propose a payment. Only you can approve it.",
  );
  await expect(page.getByRole("main")).toHaveCount(1);
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to main content" });
  await expect(skip).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#main$/);
});

test("headings run h1, then h2 for each section, then h3 for the steps", async ({ page }) => {
  await page.goto("/");
  const levels = await page
    .locator("h1, h2, h3")
    .evaluateAll((els) => els.map((e) => Number(e.tagName[1])));
  expect(levels[0]).toBe(1);
  for (let i = 1; i < levels.length; i++)
    expect(levels[i]! - levels[i - 1]!).toBeLessThanOrEqual(1);
  expect(await page.getByRole("heading", { level: 2 }).count()).toBe(6);
  expect(await page.getByRole("heading", { level: 3 }).count()).toBe(3);
});

test("'Try the demo' opens the demo sign-in, and the stable direct links work without the landing page", async ({
  page,
  request,
}) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Try the demo" }).nth(1).click();
  await expect(page).toHaveURL(/\/signin$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Choose who you are");
  for (const path of ["/signin", "/home", "/agent", "/demo"]) {
    const res = await request.get(path);
    expect(res.status(), path).toBe(200);
  }
});

test("the old home is gone from the root, and the app's own links point to /home", async ({
  page,
}) => {
  await page.goto("/home");
  await expect(page).toHaveURL(/\/signin$/); // not signed in: the app sends you to the chooser, as before
});

test("every link and button is at least 48px tall, and the page has no sideways scroll at 320px and 200% text", async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 640 });
  await page.goto("/");
  const small = await page.locator("main a, header a, footer a").evaluateAll((els) =>
    els
      .map((el) => ({
        t: el.textContent?.trim().slice(0, 30),
        h: el.getBoundingClientRect().height,
      }))
      .filter((x) => x.h < 48),
  );
  expect(small).toEqual([]);
  await page.evaluate(() =>
    document.documentElement.style.setProperty("font-size", "200%", "important"),
  );
  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
});

test("works with JavaScript turned off: every section, every link and every image is there", async ({
  browser,
}) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  for (const name of [
    "At a busy counter, you can't see the screen.",
    "Nothing is sent until you have heard it and approved it.",
    "How it works",
    "Paying shouldn't depend on who you trust at the counter.",
    "What keeps it safe",
    "See it for yourself.",
  ]) {
    await expect(page.getByRole("heading", { name })).toBeAttached();
  }
  // Reveals are CSS only: with no script the content is simply there, fully opaque.
  expect(await page.locator("h1").evaluate((el) => getComputedStyle(el).opacity)).toBe("1");
  await page.getByRole("link", { name: "Try the demo" }).nth(1).click();
  await expect(page).toHaveURL(/\/signin$/);
  await context.close();
});

test("photos: AVIF or WebP, explicit sizes, descriptive alt text, hero preloaded, the rest lazy", async ({
  page,
}) => {
  const types: string[] = [];
  page.on(
    "response",
    (r) => r.url().includes("/_next/image") && types.push(r.headers()["content-type"] ?? ""),
  );
  await page.goto("/");
  await expect(page.locator('link[rel="preload"][as="image"]')).toHaveCount(1); // the hero
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
  await page.waitForLoadState("networkidle");
  const imgs = await page.locator("main img").evaluateAll((els) =>
    (els as HTMLImageElement[]).map((i) => ({
      alt: i.alt,
      w: i.getAttribute("width"),
      h: i.getAttribute("height"),
      lazy: i.loading,
      ok: i.complete && i.naturalWidth > 0,
    })),
  );
  expect(imgs).toHaveLength(7);
  for (const i of imgs) {
    expect(i.alt.length).toBeGreaterThan(25);
    expect(i.w && i.h).toBeTruthy();
    expect(i.ok, i.alt).toBe(true);
  }
  expect(imgs.slice(1).every((i) => i.lazy === "lazy")).toBe(true);
  expect(types.length).toBeGreaterThan(0);
  for (const t of types) expect(t).toMatch(/image\/(avif|webp)/);
});

test("runs under the strict CSP: no violations, no console errors, nothing leaves this origin", async ({
  page,
  baseURL,
}) => {
  const problems: string[] = [];
  const foreign: string[] = [];
  page.on(
    "console",
    (m) =>
      (m.type() === "error" || /content security policy/i.test(m.text())) &&
      problems.push(m.text()),
  );
  page.on("pageerror", (e) => problems.push(e.message));
  page.on("request", (r) => {
    if (!r.url().startsWith(baseURL ?? "") && !/^(data|blob):/.test(r.url())) foreign.push(r.url());
  });
  await page.goto("/");
  await settle(page);
  await page.waitForLoadState("networkidle");
  expect(problems).toEqual([]);
  expect(foreign).toEqual([]);
});

test("the one warm serif is for display headings only; everything else is the system font", async ({
  page,
}) => {
  await page.goto("/");
  const family = (sel: string) =>
    page
      .locator(sel)
      .first()
      .evaluate((el) => getComputedStyle(el).fontFamily);
  expect(await family("h1")).toMatch(/Instrument Serif|serif/);
  expect(await family("main p")).toContain("-apple-system");
  expect(await family("a.land-btn")).toContain("-apple-system");
});

test("red is only the primary button and tiny accents", async ({ page }) => {
  await page.goto("/");
  const reds = await page.evaluate(() => {
    const isRed = (c: string) => /^rgb\((2[0-5]\d|1[89]\d), ?\d{1,2}, ?\d{1,2}\)$/.test(c);
    const out: string[] = [];
    for (const el of document.querySelectorAll("body *")) {
      const s = getComputedStyle(el);
      if (isRed(s.backgroundColor)) out.push(`bg:${el.className}`);
    }
    return out;
  });
  // Backgrounds: only the primary buttons (hero and final call to action).
  expect(reds.every((r) => r.includes("land-btn"))).toBe(true);
  expect(reds).toHaveLength(2);
});

test("photos tilt by one degree at most", async ({ page }) => {
  await page.goto("/");
  const angles = await page
    .locator(".land-photo")
    .evaluateAll((els) => els.map((el) => parseFloat(getComputedStyle(el).rotate || "0")));
  expect(angles.length).toBeGreaterThanOrEqual(4);
  for (const a of angles) expect(Math.abs(a)).toBeLessThanOrEqual(1);
  expect(new Set(angles.map((a) => Math.sign(a))).size).toBeGreaterThan(1); // alternating
});

test("motion: nothing moves under reduced motion, and the grain is faint", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  expect(
    await page
      .locator(".reveal")
      .first()
      .evaluate((el) => getComputedStyle(el).animationName),
  ).toBe("none");
  expect(
    await page
      .locator(".drift")
      .first()
      .evaluate((el) => getComputedStyle(el).animationName),
  ).toBe("none");
  await page.emulateMedia({ reducedMotion: "no-preference" });
  const opacity = await page.evaluate(
    () => getComputedStyle(document.querySelector(".landing")!, "::before").opacity,
  );
  expect(parseFloat(opacity)).toBeLessThanOrEqual(0.08);
  await page.emulateMedia({ contrast: "more" });
  expect(
    await page.evaluate(
      () => getComputedStyle(document.querySelector(".landing")!, "::before").opacity,
    ),
  ).toBe("0");
});

test("the manifest starts at the customer home and the icons load", async ({ request }) => {
  const res = await request.get("/manifest.webmanifest");
  expect(res.status()).toBe(200);
  const manifest = await res.json();
  expect(manifest.start_url).toBe("/home");
  expect(manifest.display).toBe("standalone");
  for (const icon of manifest.icons)
    expect((await request.get(icon.src)).status(), icon.src).toBe(200);
});

test("the demo and repo links are hidden when not configured", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("link", { name: /Watch the 90 second demo/ })).toHaveCount(0);
  await expect(page.getByRole("link", { name: /GitHub/ })).toHaveCount(0);
});
