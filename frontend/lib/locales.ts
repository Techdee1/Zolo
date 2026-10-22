/**
 * The five languages of the screens. `pcm` is Nigerian Pidgin (ISO 639-3). The picker shows each
 * language in its own name, and marks it with its own `lang`, so a screen reader pronounces it right.
 */
export const LOCALES = ["en", "pcm", "yo", "ha", "ig"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "en";

/** The choice is remembered in a cookie, so the server renders the right language on first paint. */
export const LOCALE_COOKIE = "zolo_locale";

export const LOCALE_NAMES: Record<Locale, string> = {
  en: "English",
  pcm: "Pidgin",
  yo: "Yorùbá",
  ha: "Hausa",
  ig: "Igbo",
};

export const isLocale = (v: unknown): v is Locale =>
  typeof v === "string" && (LOCALES as readonly string[]).includes(v);

/** The best match for an Accept-Language header, or English. Only the language part counts. */
export function pickLocale(acceptLanguage: string | null | undefined): Locale {
  for (const part of (acceptLanguage ?? "").split(",")) {
    const tag = part.split(";")[0]?.trim().toLowerCase().split("-")[0];
    if (isLocale(tag)) return tag;
  }
  return DEFAULT_LOCALE;
}

/** What `Intl` should use for dates ("14 Oct", day first). Pidgin has no Intl data of its own, so it uses Nigerian English. */
export const intlLocale = (l: Locale): string => (l === "pcm" ? "en-NG" : l === "en" ? "en-GB" : l);
