import en from "@/messages/en.json";
import ha from "@/messages/ha.json";
import ig from "@/messages/ig.json";
import pcm from "@/messages/pcm.json";
import yo from "@/messages/yo.json";
import type { Locale } from "@/lib/locales";

type Tree = { [key: string]: string | Tree };

/** The same merge the app does (a language file over English), for tests. */
function over(base: Tree, top: Tree): Tree {
  const out: Tree = { ...base };
  for (const [k, v] of Object.entries(top)) {
    const b = out[k];
    out[k] = typeof v === "object" && typeof b === "object" ? over(b, v) : v;
  }
  return out;
}

const FILES: Record<Locale, Tree> = {
  en: en as Tree,
  pcm: pcm as Tree,
  yo: yo as Tree,
  ha: ha as Tree,
  ig: ig as Tree,
};

export const messagesFor = (locale: Locale): Tree =>
  locale === "en" ? FILES.en : over(FILES.en, FILES[locale]);
