"use client";

import { BadgeCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { PageHeading } from "@/components/PageHeading";
import { Screen } from "@/components/Screen";
import { SaidText } from "@/components/SaidText";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useAnnounce } from "@/components/ui/LiveRegion";
import { TimeLeft } from "@/components/ui/TimeLeft";
import { ApiError, isApiError, NetworkError } from "@/lib/api/client";
import { approve, decline, getChallenge, getReadback, getRequest } from "@/lib/api/endpoints";
import type { ReadbackOut } from "@/lib/api/types";
import { API_BASE } from "@/lib/env";
import { genericErrorKey, redirectIfSignedOut } from "@/lib/errors";
import { formatNaira } from "@/lib/format/money";
import { amountSpoken } from "@/lib/format/words";
import { useLocale, useT, type MessageKey } from "@/lib/i18n";
import { readbackFor } from "@/lib/readback-lang";
import { classifyPasskeyError, signWithPasskey } from "@/lib/passkeys";
import { usePasskeyKnown, setPasskeyKnown } from "@/lib/passkey-status";
import { resultPath } from "@/lib/result-reason";
import { useReadbackVoice, useVoiceMode } from "@/lib/use-readback-voice";

/** Only a clip the backend itself rendered is played, always through our own origin. */
const audioSrc = (url: string | null | undefined) =>
  url && /^\/voice\/audio\/[\w.-]+\.mp3$/.test(url) ? `${API_BASE}${url}` : null;

export function ReviewScreen({ id }: { id: string }) {
  const t = useT();
  const { lang, englishNote } = readbackFor(useLocale());
  const passkey = usePasskeyKnown();
  const router = useRouter();
  const announce = useAnnounce();
  const [readback, setReadback] = useState<ReadbackOut | null>(null);
  const [problem, setProblem] = useState<MessageKey | null>(null);
  const [busy, setBusy] = useState<"approve" | "decline" | null>(null);
  const [mode, setMode] = useVoiceMode();
  const readbackHeading = useRef<HTMLHeadingElement>(null);

  const go = useCallback(
    (reason?: Parameters<typeof resultPath>[1]) => router.replace(resultPath(id, reason)),
    [id, router],
  );

  // Fetch the readback once per visit: asking for it moves the request to READ_BACK on the server.
  useEffect(() => {
    const controller = new AbortController();
    getReadback(id, lang, { signal: controller.signal }).then(setReadback, (e: unknown) => {
      if (controller.signal.aborted || redirectIfSignedOut(e, router)) return;
      if (isApiError(e, "INTENT_CHANGED")) return go("changed");
      if (isApiError(e, "REQUEST_EXPIRED") || isApiError(e, "STATE_CONFLICT")) return go();
      setProblem(isApiError(e, "NOT_FOUND") ? "errors.notFound" : genericErrorKey(e));
    });
    return () => controller.abort();
  }, [id, lang, router, go]);

  const voice = useReadbackVoice({
    audioUrl: audioSrc(readback?.audio_url),
    mode,
    ready: readback !== null,
    focusReadback: () => readbackHeading.current?.focus(),
  });

  async function onApprove() {
    if (busy || !readback) return;
    setBusy("approve");
    setProblem(null);
    announce(t("review.askPasskey"));
    try {
      const options = await getChallenge(id);
      const assertion = await signWithPasskey(options);
      const done = await approve(id, assertion);
      router.replace(resultPath(done.id));
    } catch (e) {
      setBusy(null);
      if (redirectIfSignedOut(e, router)) return;
      if (e instanceof ApiError) {
        if (e.code === "NO_PASSKEY") {
          setPasskeyKnown(false);
          return router.push(`/setup/passkey?next=${encodeURIComponent(`/requests/${id}`)}`);
        }
        if (e.code === "INTENT_CHANGED") return go("changed");
        if (e.code === "LIMIT_EXCEEDED") return go("limit");
        if (
          e.code === "REQUEST_EXPIRED" ||
          e.code === "ALREADY_USED" ||
          e.code === "STATE_CONFLICT" ||
          e.code === "CHALLENGE_NOT_FOUND"
        ) {
          const now = await getRequest(id).catch(() => null);
          return now && now.state !== "READ_BACK"
            ? go()
            : fail(e.code === "REQUEST_EXPIRED" ? "common.timeUp" : "errors.generic");
        }
        return fail(e.code === "SIGNATURE_INVALID" ? "review.notYou" : genericErrorKey(e));
      }
      // The prompt itself: cancelled, no authenticator, and so on. Nothing reached the server.
      if (!(e instanceof NetworkError)) {
        return fail(
          classifyPasskeyError(e) === "cancelled" ? "review.cancelled" : "errors.generic",
        );
      }
      // The connection dropped AFTER we sent the approval: we do not know the outcome. Do not claim
      // failure; look it up.
      go("check");
    }
  }

  function fail(key: MessageKey) {
    setProblem(key);
    announce(t(key), { assertive: true });
  }

  async function onDecline() {
    if (busy) return;
    setBusy("decline");
    try {
      await decline(id);
      announce(t("review.declined"));
      go();
    } catch (e) {
      setBusy(null);
      if (redirectIfSignedOut(e, router)) return;
      if (isApiError(e, "REQUEST_EXPIRED")) return go();
      fail(genericErrorKey(e));
    }
  }

  if (!readback) {
    return (
      <Screen who="customer">
        <PageHeading title={t("review.loading")}>
          {problem ? t(problem) : t("review.loading")}
        </PageHeading>
      </Screen>
    );
  }

  const amount = formatNaira(readback.amount_kobo);
  const amountWords = amountSpoken(readback.amount_kobo);
  const params = { payee: readback.payee_name, amount, amountWords };
  const approveWaits = !voice.heard;

  return (
    <Screen who="customer">
      {/* The sentence a screen reader hears first. Sighted people get the hero card below, which says
          the same thing in a layout, so it is hidden from assistive tech to avoid saying it twice. */}
      <PageHeading title={t("review.title", params)} manualFocus className="sr-only">
        <SaidText visible={t("review.title", params)} spoken={t("review.titleSpoken", params)} />
      </PageHeading>

      <section className="grid gap-4 rounded-zolo-card bg-zolo-elevated p-6 shadow-zolo-card">
        <div aria-hidden="true" className="grid gap-1">
          <p className="type-title m-0">{readback.payee_name}</p>
          <p className="type-secondary m-0">{t("review.askingFor")}</p>
          <p className="type-hero m-0 mt-3 [overflow-wrap:anywhere]">{amount}</p>
          <p className="type-body m-0 mt-1 text-zolo-secondary">
            {readback.amount_words} {t("common.unit")}
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-zolo-separator pt-4">
          <Badge variant="verified">{t("common.verified")}</Badge>
          <TimeLeft
            expiresAt={readback.expires_at}
            messages={{
              label: t("common.timeLeft"),
              oneMinute: t("common.oneMinute"),
              fifteenSeconds: t("common.fifteenSeconds"),
              expired: t("common.timeUp"),
            }}
            onExpire={() => go()}
          />
        </div>
        <p className="type-secondary m-0">{t("review.bank")}</p>
      </section>

      <section className="grid gap-2 rounded-zolo-card bg-zolo-elevated p-6 shadow-zolo-card">
        <h2
          ref={readbackHeading}
          tabIndex={-1}
          aria-describedby="readback-text"
          className="type-secondary m-0 font-semibold outline-none"
        >
          {t("review.readbackHeading")}
        </h2>
        {/* Not a live region: the voice or the screen reader reads it once, on purpose. */}
        <p id="readback-text" className="type-body m-0">
          {readback.text}
        </p>
        {englishNote ? <p className="type-secondary m-0">{t("review.englishNote")}</p> : null}
        {voice.hasAudio ? (
          <div className="mt-2">
            <Button variant="secondary" onClick={voice.play}>
              {voice.blocked ? t("review.playFirst") : t("review.hearAgain")}
            </Button>
          </div>
        ) : null}
        {voice.blocked ? <p className="type-secondary m-0">{t("review.audioBlocked")}</p> : null}
      </section>

      {passkey === false ? (
        <section
          aria-labelledby="need-passkey"
          className="grid gap-3 rounded-zolo-card bg-zolo-elevated p-6 shadow-zolo-card"
        >
          <h2 id="need-passkey" className="type-headline m-0">
            {t("passkey.needTitle")}
          </h2>
          <p className="type-body m-0 text-zolo-secondary">{t("passkey.needBody")}</p>
          <Link
            href={`/setup/passkey?next=${encodeURIComponent(`/requests/${id}`)}`}
            className="press type-body inline-flex min-h-(--target-min) items-center justify-center rounded-zolo-control border border-zolo-separator bg-zolo-elevated px-6 font-semibold text-zolo-text shadow-zolo-card"
          >
            {t("passkey.needAction")}
          </Link>
        </section>
      ) : null}

      <div>
        <Button
          variant="tertiary"
          onClick={() => setMode(mode === "zolo" ? "reader" : "zolo")}
          aria-describedby="mode-now"
        >
          {mode === "zolo" ? t("review.modeReader") : t("review.modeZolo")}
        </Button>
        <p id="mode-now" className="sr-only">
          {mode === "zolo" ? t("review.modeZoloNow") : t("review.modeReaderNow")}
        </p>
      </div>

      {problem ? (
        <p className="type-body m-0 text-zolo-critical" data-testid="review-problem">
          {t(problem)}
        </p>
      ) : null}

      <div className="action-bar grid gap-3">
        {approveWaits ? (
          <p className="type-secondary m-0 text-center">{t("review.approveWait")}</p>
        ) : null}
        <Button
          variant="primary"
          icon={<BadgeCheck size={24} strokeWidth={1.75} />}
          disabled={approveWaits}
          disabledReason={t("review.approveWait")}
          loading={busy === "approve"}
          onClick={() => void onApprove()}
        >
          <SaidText
            visible={t("review.approve", params)}
            spoken={t("review.approveSpoken", params)}
          />
        </Button>
        <Button
          variant="secondary"
          fullWidth
          loading={busy === "decline"}
          onClick={() => void onDecline()}
        >
          {t("review.decline")}
        </Button>
      </div>
    </Screen>
  );
}
