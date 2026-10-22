"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { PageHeading } from "@/components/PageHeading";
import { ResultView } from "@/components/ResultView";
import { Screen } from "@/components/Screen";
import { HeroAmount } from "@/components/ui/AmountDisplay";
import { useAnnounce } from "@/components/ui/LiveRegion";
import type { BadgeVariant } from "@/components/ui/Badge";
import { formatNaira } from "@/lib/format/money";
import { amountSpoken } from "@/lib/format/words";
import { useT, type MessageKey } from "@/lib/i18n";
import type { ResultReason } from "@/lib/result-reason";
import { LINK_PRIMARY, LINK_SECONDARY } from "@/lib/styles";
import { useRequestPoll } from "@/lib/use-request-poll";

type Outcome = {
  key:
    | "paid"
    | "processing"
    | "declined"
    | "expired"
    | "changed"
    | "failed"
    | "limit"
    | "blocked"
    | "rejected";
  variant: BadgeVariant;
  title: MessageKey;
  body?: MessageKey;
  retry: boolean;
};

/** What the customer is told, from the request's state (and, where the state cannot say, the reason). */
function outcomeOf(
  state: string,
  failure: string | null | undefined,
  reason: ResultReason | null,
): Outcome | null {
  if (reason === "changed")
    return {
      key: "changed",
      variant: "changed",
      title: "result.changed",
      body: "result.changedBody",
      retry: true,
    };
  if (reason === "limit")
    return {
      key: "limit",
      variant: "failed",
      title: "result.limit",
      body: "result.limitBody",
      retry: false,
    };
  switch (state) {
    case "SETTLED":
      return {
        key: "paid",
        variant: "paid",
        title: "result.paid",
        body: "result.paidBody",
        retry: false,
      };
    case "SUBMITTED":
    case "APPROVED":
      // The approval went through; the bank has not confirmed. Never "Paid", and the page keeps polling.
      return {
        key: "processing",
        variant: "processing",
        title: "result.processing",
        body: "result.processingBody",
        retry: false,
      };
    case "DECLINED":
      return {
        key: "declined",
        variant: "declined",
        title: "result.declined",
        body: "result.declinedBody",
        retry: false,
      };
    case "EXPIRED":
      return {
        key: "expired",
        variant: "expired",
        title: "result.expired",
        body: "result.expiredBody",
        retry: true,
      };
    case "FAILED":
      if (failure === "RISK_BLOCKED")
        return {
          key: "blocked",
          variant: "failed",
          title: "result.blocked",
          body: "result.blockedBody",
          retry: false,
        };
      if (failure === "BANK_REJECTED")
        return {
          key: "rejected",
          variant: "failed",
          title: "result.rejected",
          body: "result.rejectedBody",
          retry: true,
        };
      return {
        key: "failed",
        variant: "failed",
        title: "result.failed",
        body: "result.failedBody",
        retry: true,
      };
    default:
      return null; // still waiting on the customer: this is not a result yet
  }
}

export function ResultScreen({ id, reason }: { id: string; reason: ResultReason | null }) {
  const t = useT();
  const router = useRouter();
  const announce = useAnnounce();
  // "changed" and "limit" already say all there is to say, so one look is enough; the others
  // follow the server's state, and SUBMITTED keeps asking until the bank confirms.
  const { request, denied } = useRequestPoll(id, { once: reason !== null });
  const said = useRef<string | null>(null);
  const [inPlace, setInPlace] = useState(false);

  const outcome = request ? outcomeOf(request.state, request.failure_reason, reason) : null;

  useEffect(() => {
    if (denied === "unauthenticated") router.replace("/signin");
    else if (request && !outcome) router.replace(`/requests/${id}`); // not decided yet: back to the review
  }, [denied, request, outcome, id, router]);

  // The first outcome is spoken by focus landing on the heading. Only a CHANGE while the screen is
  // open (Processing, then Paid) goes through the live region, so nothing is said twice.
  useEffect(() => {
    if (!request || !outcome || said.current === outcome.key) return;
    const first = said.current === null;
    said.current = outcome.key;
    if (first) return;
    setInPlace(true);
    const p = {
      payee: request.payee_name,
      amount: formatNaira(request.amount_kobo),
      amountWords: amountSpoken(request.amount_kobo),
    };
    announce(outcome.key === "paid" ? t("result.paidAnnounce", p) : t(outcome.title, p), {
      assertive: outcome.variant === "changed" || outcome.variant === "failed",
    });
  }, [request, outcome, announce, t]);

  if (denied === "not-found")
    return (
      <ResultView
        back="/home"
        variant="failed"
        who="customer"
        title={t("errors.notFound")}
        action={
          <Link href="/home" className={LINK_PRIMARY}>
            {t("common.done")}
          </Link>
        }
      />
    );
  if (!request || !outcome)
    return (
      <Screen back="/home" who="customer">
        <PageHeading title={t("result.checking")}>{t("result.checking")}</PageHeading>
      </Screen>
    );

  const params = {
    payee: request.payee_name,
    amount: formatNaira(request.amount_kobo),
    amountWords: amountSpoken(request.amount_kobo),
  };
  return (
    <ResultView
      back="/home"
      variant={outcome.variant}
      who="customer"
      title={t(outcome.title, params)}
      titleSpoken={outcome.key === "paid" ? t("result.paidAnnounce", params) : undefined}
      body={outcome.body ? t(outcome.body, params) : undefined}
      bodySpoken={
        outcome.key === "processing" ? t("result.processingBodySpoken", params) : undefined
      }
      quiet={inPlace}
      visual={
        outcome.key === "paid" ? (
          <>
            <p className="type-title m-0">{t("result.paidShort")}</p>
            <HeroAmount kobo={request.amount_kobo} unit={t("common.unit")} />
            <p className="type-body m-0 text-zolo-secondary">{t("result.paidFrom", params)}</p>
          </>
        ) : undefined
      }
      extra={
        outcome.variant === "processing" ? (
          <HeroAmount kobo={request.amount_kobo} unit={t("common.unit")} />
        ) : undefined
      }
      action={
        outcome.variant === "processing" ? (
          <Link href="/home" className={LINK_SECONDARY}>
            {t("pay.back")}
          </Link>
        ) : outcome.retry ? (
          <>
            <Link href="/pay/code" className={LINK_PRIMARY}>
              {t("common.tryAgain")}
            </Link>
            <Link href="/home" className={LINK_SECONDARY}>
              {t("common.done")}
            </Link>
          </>
        ) : (
          <Link href="/home" className={LINK_PRIMARY}>
            {t("common.done")}
          </Link>
        )
      }
    />
  );
}
