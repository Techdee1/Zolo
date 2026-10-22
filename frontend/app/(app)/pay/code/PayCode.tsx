"use client";

import { ArrowLeft, HandCoins } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { PageHeading } from "@/components/PageHeading";
import { Screen } from "@/components/Screen";
import { useAnnounce } from "@/components/ui/LiveRegion";
import { claimByCode } from "@/lib/api/endpoints";
import { isApiError } from "@/lib/api/client";
import { genericErrorKey, redirectIfSignedOut } from "@/lib/errors";
import { useT, type MessageKey } from "@/lib/i18n";
import { setLastRequestId } from "@/lib/session-hint";

/**
 * The customer types the agent's 4-digit code. It is a plain text field with the system's numeric
 * keyboard (not a custom pad), it is not secret (so it is not masked), and it submits itself on the
 * fourth digit, so there is no second tap. The code is never a PIN, and the screen never says it is.
 *
 * `initialCode` comes from the agent's QR (`/claim?code=1234`): the field starts filled in and is
 * submitted once, as if typed. Signed out, the customer comes back here after signing in.
 */
export function PayCode({ initialCode }: { initialCode?: string } = {}) {
  const t = useT();
  const router = useRouter();
  const announce = useAnnounce();
  const inputId = useId();
  const hintId = useId();
  const errorId = useId();
  const [code, setCode] = useState(initialCode ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<MessageKey | null>(null);
  const claimedInitial = useRef(false);

  useEffect(() => {
    // Once only, even when React runs effects twice in development.
    if (!initialCode || claimedInitial.current) return;
    claimedInitial.current = true;
    void submit(initialCode);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once, for the code in the link
  }, [initialCode]);

  async function submit(digits: string) {
    setBusy(true);
    setError(null);
    try {
      const request = await claimByCode(digits);
      setLastRequestId(request.id);
      router.push(`/requests/${request.id}`);
    } catch (e) {
      if (redirectIfSignedOut(e, router, initialCode ? `/claim?code=${initialCode}` : undefined))
        return;
      const key: MessageKey = isApiError(e, "CODE_NOT_FOUND")
        ? "pay.notFound"
        : isApiError(e, "REQUEST_EXPIRED")
          ? "pay.expired"
          : isApiError(e, "VALIDATION_ERROR")
            ? "pay.invalid"
            : genericErrorKey(e);
      setError(key);
      announce(t(key), { assertive: true });
      setBusy(false);
    }
  }

  return (
    <Screen
      back="/home"
      who="customer"
      hero={
        <div className="grid gap-3">
          <span aria-hidden="true" className="icon-tile size-14 rounded-[18px] text-zolo-text">
            <HandCoins size={28} strokeWidth={1.75} />
          </span>
          <PageHeading title={t("pay.title")} className="type-display">
            {t("pay.title")}
          </PageHeading>
          <p id={hintId} className="type-body m-0 text-zolo-secondary">
            {t("pay.hint")}
          </p>
        </div>
      }
    >
      <div className="rise grid gap-3">
        <label htmlFor={inputId} className="section-title">
          {t("pay.label")}
        </label>
        {/* Four slots for the eye; one plain text field (lying over them) for the hand and the ear. */}
        <div className="code-slots" data-invalid={error ? "" : undefined}>
          {[0, 1, 2, 3].map((i) => (
            <span
              key={i}
              aria-hidden="true"
              className="code-slot"
              data-active={i === Math.min(code.length, 3) ? "" : undefined}
            >
              {code[i] ?? ""}
            </span>
          ))}
          <input
            id={inputId}
            type="text"
            inputMode="numeric"
            pattern="[0-9]*"
            maxLength={4}
            autoComplete="off"
            autoCorrect="off"
            spellCheck={false}
            value={code}
            disabled={busy}
            aria-invalid={error ? true : undefined}
            aria-describedby={[hintId, error ? errorId : null].filter(Boolean).join(" ")}
            onChange={(e) => {
              const digits = e.target.value.replace(/\D/g, "").slice(0, 4);
              setCode(digits);
              setError(null);
              if (digits.length === 4) void submit(digits);
            }}
          />
        </div>
        <p
          id={errorId}
          className={`type-body m-0 min-h-6 ${error ? "text-zolo-critical" : "text-zolo-secondary"}`}
        >
          {error ? t(error) : busy ? t("pay.checking") : ""}
        </p>
      </div>
      <Link
        href="/home"
        className="press type-body inline-flex min-h-(--target-min) items-center gap-2 justify-self-start rounded-zolo-control pe-3 font-semibold text-zolo-secondary"
      >
        <ArrowLeft aria-hidden="true" size={20} strokeWidth={2} />
        {t("pay.back")}
      </Link>
    </Screen>
  );
}
