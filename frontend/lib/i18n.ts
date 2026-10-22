import { useCallback } from "react";
import { useLocale as useIntlLocale, useTranslations } from "next-intl";
import { DEFAULT_LOCALE, isLocale, type Locale } from "@/lib/locales";
import en from "@/messages/en.json";

/**
 * Every word a person reads or hears lives in `messages/*.json`, by key. There is no text in
 * components (the UI kit takes labels as props for the same reason). English is the source; the
 * other four languages arrive in step 7 and plug in here, with the same keys and the same
 * `{name}` placeholders.
 *
 * A missing placeholder throws: a payment screen must not show "Paid. You sent {amount}".
 */
type Flat<T, P extends string = ""> = {
  [K in keyof T & string]: T[K] extends string ? `${P}${K}` : Flat<T[K], `${P}${K}.`>;
}[keyof T & string];

export type MessageKey = Flat<typeof en>;
export type Params = Record<string, string | number>;

export function lookup(messages: unknown, key: string): string {
  let node: unknown = messages;
  for (const part of key.split(".")) {
    node = (node as Record<string, unknown> | undefined)?.[part];
  }
  if (typeof node !== "string") throw new Error(`Missing message: ${key}`);
  return node;
}

export function fill(template: string, params: Params = {}): string {
  return template.replace(/\{(\w+)\}/g, (_, name: string) => {
    const value = params[name];
    if (value === undefined) throw new Error(`Missing value "${name}" for: ${template}`);
    return String(value);
  });
}

export type Translate = (key: MessageKey, params?: Params) => string;

export const t: Translate = (key, params) => fill(lookup(en, key), params);

/**
 * The translate function for the current language (next-intl, with the language chosen by cookie).
 * It has the same shape as the static English `t` above, so a screen reads the same either way.
 */
export function useT(): Translate {
  const intl = useTranslations();
  return useCallback<Translate>((key, params) => intl(key as never, params as never), [intl]);
}

/** The language of the screens: English, Pidgin, Yoruba, Hausa or Igbo. */
export function useLocale(): Locale {
  const locale = useIntlLocale();
  return isLocale(locale) ? locale : DEFAULT_LOCALE;
}
