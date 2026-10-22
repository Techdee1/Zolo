"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { PageHeading } from "@/components/PageHeading";
import { QrCode } from "@/components/QrCode";
import { ResultView } from "@/components/ResultView";
import { AmountDisplay } from "@/components/ui/AmountDisplay";
import { Badge } from "@/components/ui/Badge";
import { useAnnounce } from "@/components/ui/LiveRegion";
import { TimeLeft } from "@/components/ui/TimeLeft";
import { formatNaira } from "@/lib/format/money";
import { amountSpoken } from "@/lib/format/words";
import { useT } from "@/lib/i18n";
import { getAgentRequest, type StoredAgentRequest } from "@/lib/session-hint";
import { useRequestPoll } from "@/lib/use-request-poll";

const buttonLink =
  "inline-flex min-h-(--target-primary) w-full items-center justify-center rounded-zolo-control " +
  "bg-zolo-brand px-6 type-body font-semibold text-zolo-on-brand touch-manipulation " +
  "transition-transform duration-100 ease-out active:scale-(--motion-press-scale)";

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
    <Link href="/agent" className={buttonLink}>
      {t("agent.newRequest")}
    </Link>
  );

  if (denied === "not-found")
    return (
      <ResultView
        variant="failed"
        badge={t("agent.badge.failed")}
        title={t("errors.notFound")}
        action={newRequest}
      />
    );
  if (!request)
    return (
      <main id="main" className="screen">
        <PageHeading title={t("agent.waitingTitle")}>{t("agent.waitingTitle")}</PageHeading>
      </main>
    );

  const amount = formatNaira(request.amount_kobo);
  if (phase === "paid")
    return (
      <ResultView
        quiet
        variant="paid"
        badge={t("agent.badge.paid")}
        title={t("agent.paid")}
        body={t("agent.paidBody", { amount, time: paidAt ?? "" })}
        bodySpoken={t("agent.paidBodySpoken", {
          amountWords: amountSpoken(request.amount_kobo),
          time: paidAt ?? "",
        })}
        extra={<AmountDisplay kobo={request.amount_kobo} unit={t("common.unit")} showWords />}
        action={newRequest}
      />
    );
  if (phase === "processing")
    return (
      <ResultView
        quiet
        variant="processing"
        badge={t("agent.badge.processing")}
        title={t("agent.processing")}
        body={t("agent.processingBody")}
        extra={<AmountDisplay kobo={request.amount_kobo} unit={t("common.unit")} showWords />}
        action={null}
      />
    );
  if (phase === "declined" || phase === "expired" || phase === "failed")
    return (
      <ResultView
        quiet
        variant={phase}
        badge={t(`agent.badge.${phase}`)}
        title={t(`agent.${phase}`)}
        action={newRequest}
      />
    );

  const code = stored?.claim_code ?? null;
  return (
    <main id="main" className="screen grid gap-6">
      <PageHeading title={t("agent.waitingTitle")}>{t("agent.waitingTitle")}</PageHeading>
      <AmountDisplay kobo={request.amount_kobo} unit={t("common.unit")} showWords />

      {code ? (
        <section aria-labelledby="code-label" className="grid justify-items-start gap-3">
          <h2 id="code-label" className="type-secondary">
            {t("agent.yourCode")}
          </h2>
          {/* Digits are read one at a time ("4, 0, 0, 1"), not as "four thousand and one". */}
          <p
            className="type-code m-0"
            aria-label={t("agent.codeSpoken", { digits: [...code].join(", ") })}
            role="img"
          >
            {code}
          </p>
          <p className="type-secondary">{t("agent.codeAloud")}</p>
          {stored ? <QrCode value={stored.qr_payload} /> : null}
        </section>
      ) : stored === null ? (
        <p className="type-body">{t("agent.noCode")}</p>
      ) : null}

      <div className="grid gap-2">
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

      <p className="type-headline">{t("agent.waitForPaid")}</p>
      {offline ? <p className="type-secondary">{t("common.offline")}</p> : null}
    </main>
  );
}
