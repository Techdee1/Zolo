"use client";

import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { PageHeading } from "@/components/PageHeading";
import { getActivity } from "@/lib/api/endpoints";
import { isApiError } from "@/lib/api/client";
import type { ActivityItemOut } from "@/lib/api/types";
import { redirectIfSignedOut } from "@/lib/errors";
import { amountSpoken } from "@/lib/format/words";
import { useT, type Translate } from "@/lib/i18n";

/** "today", "yesterday", then "14 Oct" (the PRD's wording for dates). */
export function whenWords(iso: string, now: Date, t: Translate): string {
  const then = new Date(iso);
  const day = (d: Date) => Date.UTC(d.getFullYear(), d.getMonth(), d.getDate());
  const days = Math.round((day(now) - day(then)) / 86_400_000);
  if (days <= 0) return t("home.today");
  if (days === 1) return t("home.yesterday");
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" }).format(then);
}

function spokenItem(i: ActivityItemOut, t: Translate): string {
  const params = {
    amountWords: amountSpoken(i.amount_kobo),
    payee: i.payee_name,
    when: whenWords(i.created_at, new Date(), t),
  };
  if (i.state === "SETTLED") return t("home.itemPaid", params);
  if (i.state === "DECLINED") return t("home.itemDeclined", params);
  return t("home.itemNotPaid", params);
}

const TILE =
  "flex min-h-(--target-primary) items-center justify-between gap-4 rounded-zolo-card border " +
  "border-zolo-separator bg-zolo-grouped p-4 type-headline text-zolo-text touch-manipulation " +
  "transition-transform duration-100 ease-out active:scale-(--motion-press-scale)";

export function Home() {
  const t = useT();
  const router = useRouter();
  const [items, setItems] = useState<ActivityItemOut[] | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getActivity({ signal: controller.signal })
      .then((a) => setItems(a.items.slice(0, 3)))
      .catch((e: unknown) => {
        if (controller.signal.aborted) return;
        if (isApiError(e, "FORBIDDEN"))
          router.replace("/agent"); // an agent signed in
        else if (!redirectIfSignedOut(e, router)) setItems([]);
      });
    return () => controller.abort();
  }, [router]);

  return (
    <main id="main" className="screen grid gap-8">
      <p className="wordmark">
        {t("app.name")} <span className="wordmark-sub">{t("app.forBank")}</span>
      </p>
      <PageHeading title={t("home.title")}>{t("home.title")}</PageHeading>

      <nav aria-label={t("home.title")}>
        <ul className="m-0 grid list-none gap-3 p-0">
          <li>
            <Link href="/pay/code" className={TILE}>
              <span>
                {t("home.payAgent")}
                <span className="type-secondary block font-normal text-zolo-secondary">
                  {t("home.payAgentHint")}
                </span>
              </span>
              <ChevronRight aria-hidden="true" size={24} />
            </Link>
          </li>
        </ul>
      </nav>

      <section aria-labelledby="recent" className="grid gap-3">
        <h2 id="recent" className="type-headline">
          {t("home.recent")}
        </h2>
        {items === null ? null : items.length === 0 ? (
          <p className="type-body text-zolo-secondary">{t("home.recentEmpty")}</p>
        ) : (
          <ul className="m-0 grid list-none gap-2 p-0">
            {items.map((i) => (
              <li key={i.id} className="type-body">
                {/* Sighted: the bank's own line. Screen reader: the same, with the amount in words. */}
                <span aria-hidden="true">
                  {i.line}, {whenWords(i.created_at, new Date(), t)}
                </span>
                <span className="sr-only">{spokenItem(i, t)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="grid gap-2">
        <Link href="/setup/passkey" className="type-body underline underline-offset-4">
          {t("home.setupPasskey")}
        </Link>
        <Link href="/signin" className="type-body text-zolo-secondary underline underline-offset-4">
          {t("home.switchUser")}
        </Link>
      </div>
    </main>
  );
}
