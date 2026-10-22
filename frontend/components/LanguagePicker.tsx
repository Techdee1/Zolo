"use client";

import { useRouter } from "next/navigation";
import { useId } from "react";
import { useLocale, useT } from "@/lib/i18n";
import { LOCALES, LOCALE_COOKIE, LOCALE_NAMES, isLocale } from "@/lib/locales";

/**
 * Chooses the language of the screens. A native <select>: every screen reader and phone already
 * knows how to use one, and each language is written in its own name with its own `lang`, so it is
 * pronounced properly. The choice is a cookie, and `refresh()` makes the server render the new words.
 */
export function LanguagePicker() {
  const t = useT();
  const router = useRouter();
  const locale = useLocale();
  const id = useId();
  const hintId = useId();

  return (
    <div className="grid gap-2">
      <label htmlFor={id} className="type-body font-semibold">
        {t("language.label")}
      </label>
      <select
        id={id}
        aria-describedby={hintId}
        value={locale}
        className="type-body min-h-(--target-min) w-full rounded-zolo-control border border-zolo-separator bg-zolo-elevated px-4 text-zolo-text"
        onChange={(e) => {
          const next = e.target.value;
          if (!isLocale(next)) return;
          document.cookie = `${LOCALE_COOKIE}=${next}; path=/; max-age=31536000; samesite=lax`;
          router.refresh();
        }}
      >
        {LOCALES.map((l) => (
          <option key={l} value={l} lang={l}>
            {LOCALE_NAMES[l]}
          </option>
        ))}
      </select>
      <p id={hintId} className="type-secondary m-0">
        {t("language.hint")}
      </p>
    </div>
  );
}
