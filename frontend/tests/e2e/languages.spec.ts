import AxeBuilder from "@axe-core/playwright";
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import en from "../../messages/en.json";
import ha from "../../messages/ha.json";
import ig from "../../messages/ig.json";
import pcm from "../../messages/pcm.json";
import yo from "../../messages/yo.json";

// The five languages in a real browser: the cookie, the browser's own language, the <html lang>,
// the picker, and axe on the screens in every language (a wrong `lang` is an axe violation).

const FILES = { pcm, yo, ha, ig } as const;
type Code = keyof typeof FILES;
const CODES = ["pcm", "yo", "ha", "ig"] as const;

const setLanguage = (context: BrowserContext, code: string) =>
  context.addCookies([{ name: "zolo_locale", value: code, url: "http://localhost:3100" }]);

const axe = async (page: Page) =>
  (await new AxeBuilder({ page }).analyze()).violations.map(
    (v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`,
  );

test("English is the default, and the page says so", async ({ page }) => {
  await page.goto("/signin");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(en.signin.title);
});

for (const code of CODES) {
  test(`${code}: the cookie sets the words and <html lang>, with zero axe violations`, async ({
    context,
    page,
  }) => {
    await setLanguage(context, code);
    await page.goto("/signin");
    await expect(page.locator("html")).toHaveAttribute("lang", code);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      FILES[code as Code].signin.title,
    );
    await expect(page.getByRole("link", { name: FILES[code as Code].app.skip })).toBeAttached();
    expect(await axe(page)).toEqual([]);
    await page.emulateMedia({ colorScheme: "dark" });
    expect(await axe(page)).toEqual([]);
  });

  test(`${code}: no text is cut off at 320px wide and 200% text`, async ({ context, page }) => {
    await setLanguage(context, code);
    await page.setViewportSize({ width: 320, height: 640 });
    await page.goto("/signin");
    await page.evaluate(() =>
      document.documentElement.style.setProperty("font-size", "200%", "important"),
    );
    const { scrollWidth, clientWidth } = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
  });
}

test("the browser's own language is used when there is no cookie, and the cookie beats it", async ({
  browser,
}) => {
  const yoruba = await browser.newContext({ locale: "yo-NG" });
  const page = await yoruba.newPage();
  await page.goto("/signin");
  await expect(page.locator("html")).toHaveAttribute("lang", "yo");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(yo.signin.title);
  await yoruba.addCookies([{ name: "zolo_locale", value: "ig", url: "http://localhost:3100" }]);
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("lang", "ig");
  await yoruba.close();
});

test("a language we do not have falls back to English", async ({ browser }) => {
  const french = await browser.newContext({ locale: "fr-FR" });
  const page = await french.newPage();
  await page.goto("/signin");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await french.close();
});

test("the picker changes the words on the spot and is remembered", async ({ page }) => {
  await page.goto("/signin");
  await page.waitForLoadState("networkidle");
  const picker = page.getByRole("combobox", { name: "Language" });
  await expect(picker.locator("option")).toHaveText([
    "English",
    "Pidgin",
    "Yorùbá",
    "Hausa",
    "Igbo",
  ]);
  await picker.selectOption("ha");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(ha.signin.title);
  await expect(page.locator("html")).toHaveAttribute("lang", "ha");
  await expect(page.getByRole("combobox", { name: ha.language.label })).toHaveValue("ha");
  await page.reload();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(ha.signin.title); // remembered
});

test("the landing page stays English and says so, whatever language the app is in", async ({
  context,
  page,
}) => {
  await setLanguage(context, "yo");
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("lang", "yo");
  await expect(page.locator(".landing")).toHaveAttribute("lang", "en");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Anyone can propose a payment. Only you can approve it.",
  );
  expect(await axe(page)).toEqual([]);
});

test("the manifest and direct links do not change with the language (no locale in the URL)", async ({
  context,
  request,
  page,
}) => {
  await setLanguage(context, "ig");
  for (const path of ["/signin", "/agent", "/home"]) {
    const res = await page.goto(path);
    expect(res?.status(), path).toBe(200);
  }
  const manifest = await (await request.get("/manifest.webmanifest")).json();
  expect(manifest.start_url).toBe("/home");
});
