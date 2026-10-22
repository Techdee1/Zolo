"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { PageHeading } from "@/components/PageHeading";
import { Screen } from "@/components/Screen";
import { QrCode } from "@/components/QrCode";
import { ResultView } from "@/components/ResultView";
import { AmountDisplay, HeroAmount } from "@/components/ui/AmountDisplay";
import { Badge } from "@/components/ui/Badge";
import { useAnnounce } from "@/components/ui/LiveRegion";
import { TimeLeft } from "@/components/ui/TimeLeft";
import { amountSpoken } from "@/lib/format/words";
import { useT } from "@/lib/i18n";
import { getAgentRequest, type StoredAgentRequest } from "@/lib/session-hint";
import { LINK_PRIMARY } from "@/lib/styles";
import { useRequestPoll } from "@/lib/use-request-poll";

/** The agent's page while a customer decides. It shows the code, then the outcome, and never "Paid" early. */
export function AgentWaiting({ id }: { id: string }) {
  const t = useT();
  const router = useRouter();
  const announce = useAnnounce();
  const { request, offline, denied } = useRequestPoll(id);
  // undefined until read, so the "code is gone" note never flashes while we look.
  const [stored, setStored] = useState<StoredAgentRequest | null | undefined>(undefined);
  const [paidAt, setPaidAt] = useState<string | null>(null);
  const said = useRef<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => setStored(getAgentRequest(id)), 0);
    return () => clearTimeout(timer);
  }, [id]);

  useEffect(() => {
    if (denied === "unauthenticated") router.replace("/signin");
  }, [denied, router]);

  const state = request?.state;
  const phase =
    state === undefined
      ? "loading"
      : state === "SETTLED"
        ? "paid"
        : state === "SUBMITTED" || state === "APPROVED"
          ? "processing"
          : state === "DECLINED"
            ? "declined"
            : state === "EXPIRED"
              ? "expired"
              : state === "FAILED"
                ? "failed"
                : request?.claimed && state === "READ_BACK"
                  ? "reviewing"
                  : "waiting";

  // One polite announcement per change of phase: never every poll.
  useEffect(() => {
    if (!request || said.current === phase) return;
    const first = said.current === null;
    said.current = phase;
    if (phase === "paid") {
      // When we first saw Paid (the API gives no settled-at time), as a clock time.
      setTimeout(
        () =>
          setPaidAt(
            new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit" }).format(
              new Date(),
            ),
          ),
        0,
      );
      announce(t("agent.paidAnnounce", { amountWords: amountSpoken(request.amount_kobo) }));
    } else if (phase === "processing") announce(t("agent.processing"));
    else if (phase === "declined") announce(t("agent.declined"));
    else if (phase === "expired") announce(t("agent.expired"));
    else if (phase === "failed") announce(t("agent.failed"));
    else if (phase === "reviewing" && !first) announce(t("agent.stateReviewing"));
  }, [phase, request, announce, t]);

  const newRequest = (
    <Link href="/agent" className={LINK_PRIMARY}>
      {t("agent.newRequest")}
    </Link>
  );

  if (denied === "not-found")
    return (
      <ResultView variant="failed" who="agent" title={t("errors.notFound")} action={newRequest} />
    );
  if (!request)
    return (
      <Screen who="agent">
        <PageHeading title={t("agent.waitingTitle")}>{t("agent.waitingTitle")}</PageHeading>
      </Screen>
    );

  if (phase === "paid")
    return (
      <ResultView
        quiet
        variant="paid"
        who="agent"
        title={t("agent.paid")}
        body={t("agent.paidAt", { time: paidAt ?? "" })}
        bodySpoken={t("agent.paidBodySpoken", {
          amountWords: amountSpoken(request.amount_kobo),
          time: paidAt ?? "",
        })}
        visual={
          <>
            <p className="type-title m-0">{t("agent.paid")}</p>
            <HeroAmount kobo={request.amount_kobo} unit={t("common.unit")} />
          </>
        }
        action={newRequest}
      />
    );
  if (phase === "processing")
    return (
      <ResultView
        quiet
        variant="processing"
        who="agent"
        title={t("agent.processing")}
        body={t("agent.processingBody")}
        extra={<HeroAmount kobo={request.amount_kobo} unit={t("common.unit")} />}
        action={null}
      />
    );
  if (phase === "declined" || phase === "expired" || phase === "failed")
    return (
      <ResultView
        quiet
        variant={phase}
        who="agent"
        title={t(`agent.${phase}`)}
        action={newRequest}
      />
    );

  const code = stored?.claim_code ?? null;
  return (
    <Screen who="agent">
      <PageHeading title={t("agent.waitingTitle")}>{t("agent.waitingTitle")}</PageHeading>

      <section className="grid gap-5 rounded-zolo-card bg-zolo-elevated p-6 shadow-zolo-card">
        <AmountDisplay kobo={request.amount_kobo} unit={t("common.unit")} size="large" showWords />

        {code ? (
          <div
            aria-labelledby="code-label"
            role="group"
            className="grid justify-items-center gap-3 border-t border-zolo-separator pt-5 text-center"
          >
            <h2 id="code-label" className="type-secondary m-0 font-semibold">
              {t("agent.yourCode")}
            </h2>
            {/* Digits are read one at a time ("4, 0, 0, 1"), not as "four thousand and one". */}
            <p
              className="type-hero m-0 tracking-[0.12em]"
              aria-label={t("agent.codeSpoken", { digits: [...code].join(", ") })}
              role="img"
            >
              {code}
            </p>
            <p className="type-secondary m-0">{t("agent.codeAloud")}</p>
            {stored ? <QrCode value={stored.qr_payload} /> : null}
          </div>
        ) : stored === null ? (
          <p className="type-body m-0">{t("agent.noCode")}</p>
        ) : null}
      </section>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Badge variant={phase === "reviewing" ? "processing" : "waiting"}>
          {phase === "reviewing" ? t("agent.stateReviewing") : t("agent.stateWaiting")}
        </Badge>
        <TimeLeft
          expiresAt={request.expires_at}
          messages={{
            label: t("common.timeLeft"),
            oneMinute: t("common.oneMinute"),
            fifteenSeconds: t("common.fifteenSeconds"),
            expired: t("common.timeUp"),
          }}
        />
      </div>

      <p className="type-headline m-0 rounded-zolo-card border border-zolo-separator bg-zolo-elevated p-4">
        {t("agent.waitForPaid")}
      </p>
      {offline ? <p className="type-secondary">{t("common.offline")}</p> : null}
    </Screen>
  );
}
