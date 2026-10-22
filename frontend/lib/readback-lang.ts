import type { ReadbackLang } from "@/lib/api/endpoints";
import type { Locale } from "@/lib/locales";
export type { Locale };

/**
 * The backend can only SPEAK English and Pidgin; any other `lang` is a 422. So a Yoruba, Hausa or
 * Igbo customer gets the screens in their language and the spoken readback in English, with a short
 * note saying so. We never ask for a language the backend does not have.
 */
export function readbackFor(locale: Locale): { lang: ReadbackLang; englishNote: boolean } {
  if (locale === "pcm") return { lang: "pcm", englishNote: false };
  if (locale === "en") return { lang: "en", englishNote: false };
  return { lang: "en", englishNote: true };
}
