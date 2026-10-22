import type { ReadbackLang } from "@/lib/api/endpoints";
import type { Locale } from "@/lib/locales";
export type { Locale };

/**
 * The readback is asked for in the customer's own language. The backend answers in that language
 * when it has a recording of the exact sentence; for Yoruba, Hausa or Igbo without one it answers in
 * English and sets `fallback_from`, and only then does the screen say the voice is in English.
 * Anything else the backend would refuse (422), but all five of ours are accepted.
 */
export function readbackFor(locale: Locale): { lang: ReadbackLang } {
  return { lang: locale };
}

/** Did the readback fall back to English for a language the customer chose? Then say so. */
export const fellBack = (readback: { fallback_from?: string | null }): boolean =>
  Boolean(readback.fallback_from);
