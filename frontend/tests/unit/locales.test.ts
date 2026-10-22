import { describe, expect, it } from "vitest";
import { DEFAULT_LOCALE, LOCALES, intlLocale, isLocale, pickLocale } from "@/lib/locales";
import { readbackFor } from "@/lib/readback-lang";
import en from "@/messages/en.json";
import { messagesFor } from "./messages";

type Tree = { [key: string]: string | Tree };
const flat = (d: Tree, p = ""): Array<[string, string]> =>
  Object.entries(d).flatMap(([k, v]) =>
    typeof v === "string" ? [[p + k, v] as [string, string]] : flat(v, `${p}${k}.`),
  );
const placeholders = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]!).sort();

// The landing page is English only, and the demo console and the brand line stay in English too.
const ENGLISH_ONLY = /^(landing|demo|demoMenu)\.|^app\.(name|forBank)$/;
const source = flat(en as Tree).filter(([k]) => !ENGLISH_ONLY.test(k));

describe("the five languages", () => {
  it("are English, Pidgin, Yoruba, Hausa and Igbo", () => {
    expect([...LOCALES]).toEqual(["en", "pcm", "yo", "ha", "ig"]);
    expect(DEFAULT_LOCALE).toBe("en");
  });

  for (const locale of LOCALES.filter((l) => l !== "en")) {
    describe(locale, () => {
      it("translates every screen string, with none missing", async () => {
        const raw = (await import(`@/messages/${locale}.json`)).default as Tree;
        const have = new Map(flat(raw));
        const missing = source.map(([k]) => k).filter((k) => !have.has(k));
        expect(missing).toEqual([]);
        expect([...have.keys()].filter((k) => !source.some(([s]) => s === k))).toEqual([]); // and nothing extra
      });

      it("keeps every {placeholder} exactly as in English, so no amount or name is ever lost", async () => {
        const raw = (await import(`@/messages/${locale}.json`)).default as Tree;
        for (const [k, v] of flat(raw)) {
          const english = source.find(([s]) => s === k)?.[1] ?? "";
          expect(placeholders(v), k).toEqual(placeholders(english));
        }
      });

      it("has no empty strings, and no English left in the safety-critical sentences", async () => {
        const raw = (await import(`@/messages/${locale}.json`)).default as Tree;
        const all = new Map(flat(raw));
        for (const [k, v] of all) expect(v.trim().length, k).toBeGreaterThan(0);
        for (const k of [
          "result.changed",
          "result.declined",
          "result.expired",
          "result.failed",
          "result.processing",
          "review.cancelled",
          "passkey.never",
        ]) {
          expect(all.get(k), k).not.toBe((en as unknown as { [k: string]: string })[k]);
          expect(all.get(k), k).not.toMatch(
            /^(This payment changed|Declined\.|This request expired|The payment did not|Processing\.)/,
          );
        }
      });

      it("says Processing differently from Paid: a payment still in the bank's hands never reads as done", async () => {
        const raw = (await import(`@/messages/${locale}.json`)).default as {
          result: {
            processing: string;
            paidShort: string;
            badge: { processing: string; paid: string };
          };
        };
        expect(raw.result.processing).not.toContain(raw.result.paidShort);
        expect(raw.result.badge.processing).not.toBe(raw.result.badge.paid);
      });

      it("still says Zolo never asks for a PIN or card number", async () => {
        const raw = (await import(`@/messages/${locale}.json`)).default as {
          passkey: { never: string };
        };
        expect(raw.passkey.never).toMatch(/Zolo/);
        expect(raw.passkey.never).toMatch(/PIN/);
      });
    });
  }

  it("every language still has the English fallback for what is not translated (the demo console)", () => {
    for (const locale of LOCALES) {
      const all = new Map(flat(messagesFor(locale) as Tree));
      expect(all.get("demo.title")).toBe("Demo console");
      expect(all.get("app.name")).toBe("Zolo");
    }
  });
});

describe("choosing a language", () => {
  it("recognises only the five", () => {
    for (const l of LOCALES) expect(isLocale(l)).toBe(true);
    for (const bad of ["fr", "EN", "", null, undefined, "pcm-NG"])
      expect(isLocale(bad)).toBe(false);
  });

  it("falls back from the browser's preference to English", () => {
    expect(pickLocale("yo-NG,en;q=0.8")).toBe("yo");
    expect(pickLocale("fr-FR, ig;q=0.7")).toBe("ig");
    expect(pickLocale("pcm")).toBe("pcm");
    expect(pickLocale("fr, de")).toBe("en");
    expect(pickLocale(null)).toBe("en");
  });

  it("formats dates day first, in a locale that exists", () => {
    expect(intlLocale("en")).toBe("en-GB");
    expect(intlLocale("pcm")).toBe("en-NG");
    for (const l of LOCALES)
      expect(() =>
        new Intl.DateTimeFormat(intlLocale(l), { day: "numeric", month: "short" }).format(
          new Date(),
        ),
      ).not.toThrow();
  });
});

describe("the language of the spoken readback", () => {
  it("is Pidgin for Pidgin, English for English, and English with a note for Yoruba, Hausa and Igbo", () => {
    expect(readbackFor("pcm")).toEqual({ lang: "pcm" });
    expect(readbackFor("en")).toEqual({ lang: "en" });
    for (const l of ["yo", "ha", "ig"] as const) expect(readbackFor(l)).toEqual({ lang: l });
  });
});
