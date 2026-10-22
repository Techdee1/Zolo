import { cookies, headers } from "next/headers";
import { getRequestConfig } from "next-intl/server";
import { DEFAULT_LOCALE, LOCALE_COOKIE, isLocale, pickLocale, type Locale } from "@/lib/locales";
import en from "@/messages/en.json";

type Tree = { [key: string]: string | Tree };

/** A language file over English, so a missing string is English, never a blank or a raw key. */
function over(base: Tree, top: Tree): Tree {
  const out: Tree = { ...base };
  for (const [k, v] of Object.entries(top)) {
    const b = out[k];
    out[k] = typeof v === "object" && typeof b === "object" ? over(b, v) : v;
  }
  return out;
}

const load = async (locale: Locale): Promise<Tree> =>
  locale === DEFAULT_LOCALE
    ? (en as Tree)
    : over(en as Tree, (await import(`../messages/${locale}.json`)).default as Tree);

/**
 * No locale in the URL: the cookie says which language, then the browser's Accept-Language, then
 * English. Routes stay the same in every language, so direct links and the manifest do too.
 */
export default getRequestConfig(async () => {
  const fromCookie = (await cookies()).get(LOCALE_COOKIE)?.value;
  const locale: Locale = isLocale(fromCookie)
    ? fromCookie
    : pickLocale((await headers()).get("accept-language"));
  const messages = await load(locale);
  return { locale, messages };
});
