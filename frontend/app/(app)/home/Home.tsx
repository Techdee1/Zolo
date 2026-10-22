"use client";

import { BadgeCheck, ChevronRight, HandCoins, KeyRound, Receipt } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { PageHeading } from "@/components/PageHeading";
import { Screen } from "@/components/Screen";
import { getActivity } from "@/lib/api/endpoints";
import { isApiError } from "@/lib/api/client";
import type { ActivityItemOut } from "@/lib/api/types";
import { redirectIfSignedOut } from "@/lib/errors";
import { amountSpoken } from "@/lib/format/words";
import { useT, type Translate } from "@/lib/i18n";
import { usePasskeyKnown } from "@/lib/passkey-status";

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

const CARD = "rounded-zolo-card bg-zolo-elevated shadow-zolo-card";
/** A small icon in a rounded square: quiet, decorative, never the only label. */
const ICON_BOX =
  "grid size-11 shrink-0 place-items-center rounded-[12px] bg-zolo-grouped text-zolo-text";
const ROW =
  "press flex min-h-(--target-primary) items-center gap-4 p-4 text-zolo-text touch-manipulation";

function PasskeyRowBody({ passkey, t }: { passkey: boolean | null; t: Translate }) {
  return (
    <>
      <span className={ICON_BOX}>
        <KeyRound aria-hidden="true" size={22} strokeWidth={1.75} />
      </span>
      <span className="grid flex-1 justify-items-start gap-0.5">
        <span className="type-body font-semibold">{t("passkey.rowTitle")}</span>
        {passkey === null ? null : (
          <span
            className={`type-secondary inline-flex items-center gap-1.5 ${passkey ? "text-zolo-success" : ""}`}
          >
            {passkey ? <BadgeCheck aria-hidden="true" size={16} strokeWidth={1.75} /> : null}
            {t(passkey ? "passkey.statusOn" : "passkey.statusOff")}
          </span>
        )}
      </span>
    </>
  );
}

export function Home() {
  const t = useT();
  const router = useRouter();
  const passkey = usePasskeyKnown();
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
    <Screen who="customer" className="gap-8">
      <PageHeading title={t("home.title")} className="type-display">
        {t("home.title")}
      </PageHeading>

      <nav aria-label={t("home.title")}>
        <Link href="/pay/code" className={`${CARD} ${ROW}`}>
          <span className="flex flex-1 items-center gap-4">
            <span className={ICON_BOX}>
              <HandCoins aria-hidden="true" size={24} strokeWidth={1.75} />
            </span>
            <span className="grid flex-1 gap-0.5">
              <span className="type-headline">{t("home.payAgent")}</span>
              <span className="type-secondary">{t("home.payAgentHint")}</span>
            </span>
            <ChevronRight aria-hidden="true" size={22} className="text-zolo-secondary" />
          </span>
        </Link>
      </nav>

      <section aria-labelledby="recent" className="grid gap-2">
        <h2 id="recent" className="type-secondary px-4 font-semibold">
          {t("home.recent")}
        </h2>
        <div className={`${CARD} overflow-clip`}>
          {items === null ? (
            <div className="min-h-(--target-primary)" />
          ) : items.length === 0 ? (
            <div className="grid justify-items-center gap-1 px-4 py-8 text-center">
              <span className={ICON_BOX}>
                <Receipt aria-hidden="true" size={22} strokeWidth={1.75} />
              </span>
              <p className="type-body mt-2 font-semibold">{t("home.recentEmpty")}</p>
              <p className="type-secondary">{t("home.recentEmptyHint")}</p>
            </div>
          ) : (
            <ul className="m-0 list-none divide-y divide-zolo-separator p-0">
              {items.map((i) => (
                <li key={i.id} className="type-body px-4 py-3">
                  {/* Sighted: the bank's own line. Screen reader: the same, with the amount in words. */}
                  <span aria-hidden="true">
                    {i.line}, {whenWords(i.created_at, new Date(), t)}
                  </span>
                  <span className="sr-only">{spokenItem(i, t)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <section aria-labelledby="account" className="grid gap-2">
        <h2 id="account" className="sr-only">
          {t("passkey.rowTitle")}
        </h2>
        <div className={CARD}>
          {/* Once this phone has a passkey there is nothing to do here (a phone cannot make a second
              one: the browser refuses), so the row is just the status. Without one, it is the way in. */}
          {passkey ? (
            <div className="flex min-h-(--target-primary) items-center gap-4 p-4">
              <PasskeyRowBody passkey t={t} />
            </div>
          ) : (
            <Link href="/setup/passkey" className={ROW}>
              <PasskeyRowBody passkey={passkey} t={t} />
              <span className="type-secondary font-semibold text-zolo-text">
                {t("passkey.actionOff")}
              </span>
              <ChevronRight aria-hidden="true" size={22} className="text-zolo-secondary" />
            </Link>
          )}
        </div>
      </section>
    </Screen>
  );
}
