"use client";

import { Phone, PhoneOff } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { PageHeading } from "@/components/PageHeading";
import { Screen } from "@/components/Screen";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { useAnnounce } from "@/components/ui/LiveRegion";
import { ApiError, isApiError } from "@/lib/api/client";
import { pressPhoneKeys, startPhoneCall } from "@/lib/api/endpoints";
import type { PhoneCallOut } from "@/lib/api/types";
import { API_BASE } from "@/lib/env";
import { genericErrorKey, redirectIfSignedOut } from "@/lib/errors";
import { useT, type MessageKey } from "@/lib/i18n";
import { resultPath } from "@/lib/result-reason";
import { LINK_PRIMARY } from "@/lib/styles";
import { useVoiceMode } from "@/lib/use-readback-voice";

type Prompt = PhoneCallOut["prompts"][number];

const audioSrc = (url: string | null | undefined) =>
  url && /^\/voice\/audio\/[\w.-]+\.mp3$/.test(url) ? `${API_BASE}${url}` : null;

/** Plays one prompt: its recording when there is one, else the browser's own voice reads the text. */
function speak(
  prompt: Prompt,
  lang: string,
  stop: { current: (() => void) | null },
): Promise<void> {
  return new Promise((resolve) => {
    const src = audioSrc(prompt.audio_url);
    const finish = () => {
      stop.current = null;
      resolve();
    };
    if (src) {
      const el = new Audio(src);
      stop.current = () => {
        el.pause();
        finish();
      };
      el.onended = finish;
      el.onerror = finish;
      el.play().catch(finish);
      return;
    }
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return finish();
    const u = new SpeechSynthesisUtterance(prompt.text);
    u.lang = lang === "yo" ? "yo-NG" : "en-NG";
    u.onend = finish;
    u.onerror = finish;
    stop.current = () => {
      window.speechSynthesis.cancel();
      finish();
    };
    window.speechSynthesis.speak(u);
  });
}

/**
 * The call, simulated in the app: Zolo "rings", the customer answers, hears the same readback and
 * picks 1, 2 or 9 on the keypad, then types the Zolo PIN. All the rules live on the server (the
 * same two calls would drive a real phone line); this screen only shows and plays what it says.
 * A voice never approves on its own: approval needs the PIN, typed.
 */
export function CallScreen({ id }: { id: string }) {
  const t = useT();
  const router = useRouter();
  const announce = useAnnounce();
  const [mode] = useVoiceMode();
  const [call, setCall] = useState<PhoneCallOut | null>(null);
  const [lines, setLines] = useState<Prompt[]>([]);
  const [error, setError] = useState<MessageKey | null>(null);
  const [busy, setBusy] = useState(false);
  const [pin, setPin] = useState("");
  const stop = useRef<(() => void) | null>(null);
  const alive = useRef(true);
  const pinField = useRef<HTMLInputElement>(null);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      // the latest playing prompt, not the one from when this effect ran
      // eslint-disable-next-line react-hooks/exhaustive-deps
      stop.current?.();
    };
  }, []);

  const asksForPin = call?.expects === "pin";
  useEffect(() => {
    if (asksForPin) pinField.current?.focus();
  }, [asksForPin]);

  const play = useCallback(
    async (prompts: Prompt[], lang: string) => {
      setLines((old) => [...old, ...prompts]);
      if (mode === "reader") return;
      for (const p of prompts) {
        if (!alive.current) return;
        await speak(p, lang, stop);
      }
    },
    [mode],
  );

  function failWith(e: unknown) {
    if (redirectIfSignedOut(e, router)) return;
    if (isApiError(e, "REQUEST_EXPIRED")) return router.replace(resultPath(id));
    let key: MessageKey = genericErrorKey(e);
    if (e instanceof ApiError) {
      if (e.code === "RATE_LIMITED") key = "phone.tooMany";
      else if (e.code === "STATE_CONFLICT")
        key = /set up/i.test(e.message)
          ? "phone.notReady"
          : /locked/i.test(e.message)
            ? "phone.locked"
            : /paused/i.test(e.message)
              ? "phone.paused"
              : "phone.failed";
      else if (e.code === "NOT_FOUND") key = "phone.failed";
    }
    setError(key);
    announce(t(key), { assertive: true });
  }

  async function answer() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const started = await startPhoneCall(id);
      setCall(started);
      await play(started.prompts, started.lang);
    } catch (e) {
      failWith(e);
    } finally {
      setBusy(false);
    }
  }

  async function press(digits: string) {
    if (busy || !call) return;
    stop.current?.();
    setBusy(true);
    setError(null);
    try {
      const next = await pressPhoneKeys(call.call_id, digits);
      setCall(next);
      setPin("");
      await play(next.prompts, next.lang);
      if (next.done && alive.current) router.replace(resultPath(id));
    } catch (e) {
      failWith(e);
    } finally {
      setBusy(false);
    }
  }

  function sendPin(e: FormEvent) {
    e.preventDefault();
    if (pin.length === 4) void press(pin);
  }

  function hangUp() {
    stop.current?.();
    router.replace(`/requests/${encodeURIComponent(id)}`);
  }

  const live = call !== null && !call.done;
  return (
    <Screen
      back={`/requests/${encodeURIComponent(id)}`}
      who="customer"
      hero={
        <div className="grid gap-3">
          <span aria-hidden="true" className="icon-tile size-14 rounded-[18px] text-zolo-text">
            <Phone size={30} strokeWidth={1.75} />
          </span>
          <PageHeading title={t("phone.callTitle")} className="type-display">
            {call ? t("phone.callTitle") : t("phone.ringing")}
          </PageHeading>
        </div>
      }
    >
      <p className="type-secondary m-0">{t("phone.demoNote")}</p>

      {lines.length > 0 ? (
        <section aria-label={t("phone.transcript")} className="surface rise grid gap-3 p-5">
          <ol
            className="m-0 grid list-none gap-3 p-0"
            aria-live={mode === "reader" ? "polite" : "off"}
          >
            {lines.map((l, i) => (
              <li key={`${l.key}-${i}`} className="type-body">
                {l.text}
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {error ? (
        <Alert>
          {t(error)}{" "}
          <Link href={`/requests/${encodeURIComponent(id)}`} className="underline">
            {t("phone.usePasskey")}
          </Link>
        </Alert>
      ) : null}

      {call?.expects === "choice" ? (
        <div className="grid gap-3" role="group" aria-label={t("phone.listening")}>
          <Button variant="primary" loading={busy} onClick={() => void press("1")}>
            {t("phone.approve")}
          </Button>
          <Button variant="secondary" fullWidth loading={busy} onClick={() => void press("2")}>
            {t("phone.decline")}
          </Button>
          <Button variant="tertiary" onClick={() => void press("9")}>
            {t("phone.repeat")}
          </Button>
        </div>
      ) : null}

      {call?.expects === "pin" ? (
        <form onSubmit={sendPin} className="grid gap-3">
          <label className="grid gap-1">
            <span className="type-headline">{t("phone.pinPrompt")}</span>
            <input
              className="type-body min-h-(--target-min) w-full rounded-zolo-control border border-zolo-separator bg-zolo-elevated px-4 text-zolo-text"
              type="password"
              inputMode="numeric"
              autoComplete="off"
              pattern="[0-9]{4}"
              maxLength={4}
              value={pin}
              ref={pinField}
              onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
            />
          </label>
          <Button
            variant="primary"
            type="submit"
            loading={busy}
            disabled={pin.length !== 4}
            disabledReason={t("phone.pinPrompt")}
          >
            {t("phone.pinSend")}
          </Button>
        </form>
      ) : null}

      <div className="action-bar mt-auto grid gap-3">
        {call === null ? (
          <Button
            variant="primary"
            icon={<Phone size={24} strokeWidth={1.75} />}
            loading={busy}
            onClick={() => void answer()}
          >
            {t("phone.answer")}
          </Button>
        ) : null}
        {call?.done ? (
          <Link href={resultPath(id)} className={LINK_PRIMARY}>
            {t("common.done")}
          </Link>
        ) : (
          <Button
            variant="secondary"
            fullWidth
            icon={<PhoneOff size={22} strokeWidth={1.75} />}
            onClick={hangUp}
          >
            {t(live ? "phone.hangUp" : "phone.usePasskey")}
          </Button>
        )}
      </div>
    </Screen>
  );
}
