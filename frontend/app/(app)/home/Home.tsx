"use client";

import { ArrowRight, BadgeCheck, ChevronRight, HandCoins, KeyRound, Receipt } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { LanguagePicker } from "@/components/LanguagePicker";
import { PageHeading } from "@/components/PageHeading";
import { Screen } from "@/components/Screen";
import { STYLE, type BadgeVariant } from "@/components/ui/Badge";
import { getActivity } from "@/lib/api/endpoints";
import { isApiError } from "@/lib/api/client";
import type { ActivityItemOut } from "@/lib/api/types";
import { redirectIfSignedOut } from "@/lib/errors";
import { formatNaira } from "@/lib/format/money";
import { amountSpoken } from "@/lib/format/words";
import { useLocale, useT, type MessageKey, type Translate } from "@/lib/i18n";
import { intlLocale, type Locale } from "@/lib/locales";
import { usePasskeyKnown } from "@/lib/passkey-status";
import { getSessionHint } from "@/lib/session-hint";
import { CARD, CARD_PAD, ROW, ROW_LINK } from "@/lib/styles";

/** "today", "yesterday", then "14 Oct" (the PRD's wording for dates). */
export function whenWords(iso: string, now: Date, t: Translate, locale: Locale = "en"): string {
  const then = new Date(iso);
  const day = (d: Date) => Date.UTC(d.getFullYear(), d.getMonth(), d.getDate());
  const days = Math.round((day(now) - day(then)) / 86_400_000);
  if (days <= 0) return t("home.today");
  if (days === 1) return t("home.yesterday");
  return new Intl.DateTimeFormat(intlLocale(locale), { day: "numeric", month: "short" }).format(
    then,
  );
}

/** One payment as a sentence in the customer's language, with the amount in words, for the ear. */
function itemSpoken(i: ActivityItemOut, t: Translate, locale: Locale): string {
  const params = {
    amountWords: amountSpoken(i.amount_kobo),
    payee: i.payee_name,
    when: whenWords(i.created_at, new Date(), t, locale),
  };
  if (i.state === "SETTLED") return t("home.itemPaid", params);
  if (i.state === "DECLINED") return t("home.itemDeclined", params);
  return t("home.itemNotPaid", params);
}

/** For the eye: the icon and the short status word, from the same labels the result screens use. */
function itemStatus(state: string): { variant: BadgeVariant; label: MessageKey } {
  switch (state) {
    case "SETTLED":
      return { variant: "paid", label: "result.badge.paid" };
    case "DECLINED":
      return { variant: "declined", label: "result.badge.declined" };
    case "EXPIRED":
      return { variant: "expired", label: "result.badge.expired" };
    case "FAILED":
      return { variant: "failed", label: "result.badge.failed" };
    case "SUBMITTED":
    case "APPROVED":
      return { variant: "processing", label: "result.badge.processing" };
    default:
      return { variant: "waiting", label: "agent.badge.failed" }; // "Not paid"
  }
}

const initials = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join("");

function ActivityRow({ item, t, locale }: { item: ActivityItemOut; t: Translate; locale: Locale }) {
  const { variant, label } = itemStatus(item.state);
  const { icon: Icon, tone } = STYLE[variant];
  return (
    <li className={ROW}>
      {/* Sighted: payee, status and amount laid out. Screen reader: one sentence, amount in words. */}
      <span aria-hidden="true" className={`icon-tile round ${tone}`}>
        <Icon size={20} strokeWidth={1.75} />
      </span>
      <span aria-hidden="true" className="grid min-w-0 flex-1 gap-0.5">
        <span className="type-body truncate font-semibold">{item.payee_name}</span>
        <span className="type-secondary">
          {t(label)} · {whenWords(item.created_at, new Date(), t, locale)}
        </span>
      </span>
      <span
        aria-hidden="true"
        className={`type-body font-semibold tabular-nums ${item.state === "SETTLED" ? "" : "text-zolo-secondary"}`}
      >
        {formatNaira(item.amount_kobo)}
      </span>
      <span className="sr-only">{itemSpoken(item, t, locale)}</span>
    </li>
  );
}

function PasskeyRowBody({ passkey, t }: { passkey: boolean | null; t: Translate }) {
  return (
    <>
      <span className="icon-tile text-zolo-text">
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
  const locale = useLocale();
  const router = useRouter();
  const passkey = usePasskeyKnown();
  const [items, setItems] = useState<ActivityItemOut[] | null>(null);
  const [name, setName] = useState<string | null>(null);

  useEffect(() => {
    const id = setTimeout(() => setName(getSessionHint()?.name ?? null), 0);
    return () => clearTimeout(id);
  }, []);

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
    <Screen
      back="/signin"
      who="customer"
      className="gap-8"
      hero={
        <>
          {name ? (
            <p className="m-0 flex items-center gap-3">
              <span aria-hidden="true" className="avatar">
                {initials(name)}
              </span>
              <span className="type-headline">{name}</span>
            </p>
          ) : null}
          <PageHeading title={t("home.title")} className="type-display">
            {t("home.title")}
          </PageHeading>
          <nav aria-label={t("home.title")}>
            {/* The one red thing on this screen: the way to pay. */}
            <Link
              href="/pay/code"
              className="press flex min-h-(--target-primary) touch-manipulation items-center gap-4 rounded-[22px] bg-[linear-gradient(145deg,#e3262c,#b3141a)] p-4 text-zolo-on-brand shadow-zolo-primary"
            >
              <span className="grid size-12 shrink-0 place-items-center rounded-[16px] bg-white/15">
                <HandCoins aria-hidden="true" size={26} strokeWidth={1.75} />
              </span>
              <span className="grid flex-1 gap-0.5">
                <span className="type-headline">{t("home.payAgent")}</span>
                <span className="type-secondary text-zolo-on-brand">{t("home.payAgentHint")}</span>
              </span>
              <span className="grid size-10 shrink-0 place-items-center rounded-full bg-white text-[#b3141a]">
                <ArrowRight aria-hidden="true" size={20} strokeWidth={2.25} />
              </span>
            </Link>
          </nav>
        </>
      }
    >
      <section aria-labelledby="recent" className="rise grid gap-3">
        <h2 id="recent" className="section-title">
          {t("home.recent")}
        </h2>
        <div className={`${CARD} overflow-clip`}>
          {items === null ? (
            <div className="min-h-(--target-primary)" />
          ) : items.length === 0 ? (
            <div className="grid justify-items-center gap-1 px-4 py-8 text-center">
              <span className="icon-tile text-zolo-secondary">
                <Receipt aria-hidden="true" size={22} strokeWidth={1.75} />
              </span>
              <p className="type-body mt-2 font-semibold">{t("home.recentEmpty")}</p>
              <p className="type-secondary">{t("home.recentEmptyHint")}</p>
            </div>
          ) : (
            <ul className="rows inset m-0 list-none p-0">
              {items.map((i) => (
                <ActivityRow key={i.id} item={i} t={t} locale={locale} />
              ))}
            </ul>
          )}
        </div>
      </section>

      <section aria-labelledby="account" className="rise grid gap-3 [--rise:1]">
        <h2 id="account" className="sr-only">
          {t("passkey.rowTitle")}
        </h2>
        <div className={`${CARD} overflow-clip`}>
          {/* Once this phone has a passkey there is nothing to do here (a phone cannot make a second
              one: the browser refuses), so the row is just the status. Without one, it is the way in. */}
          {passkey ? (
            <div className={ROW}>
              <PasskeyRowBody passkey t={t} />
            </div>
          ) : (
            <Link href="/setup/passkey" className={ROW_LINK}>
              <PasskeyRowBody passkey={passkey} t={t} />
              <span className="type-secondary font-semibold text-zolo-text">
                {t("passkey.actionOff")}
              </span>
              <ChevronRight aria-hidden="true" size={22} className="text-zolo-secondary" />
            </Link>
          )}
        </div>
      </section>

      <section className={`rise ${CARD_PAD} [--rise:2]`}>
        <LanguagePicker />
      </section>
    </Screen>
  );
}
