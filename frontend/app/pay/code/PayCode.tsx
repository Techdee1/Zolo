"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import { PageHeading } from "@/components/PageHeading";
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
 */
export function PayCode() {
  const t = useT();
  const router = useRouter();
  const announce = useAnnounce();
  const inputId = useId();
  const hintId = useId();
  const errorId = useId();
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<MessageKey | null>(null);

  async function submit(digits: string) {
    setBusy(true);
    setError(null);
    try {
      const request = await claimByCode(digits);
      setLastRequestId(request.id);
      router.push(`/requests/${request.id}`);
    } catch (e) {
      if (redirectIfSignedOut(e, router)) return;
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
    <main id="main" className="screen grid gap-6">
      <PageHeading title={t("pay.title")}>{t("pay.title")}</PageHeading>
      <div className="grid gap-2">
        <label htmlFor={inputId} className="type-headline">
          {t("pay.label")}
        </label>
        <p id={hintId} className="type-secondary">
          {t("pay.hint")}
        </p>
        <input
          id={inputId}
          className="type-code min-h-(--target-primary) w-full rounded-zolo-control border border-zolo-separator bg-zolo-grouped px-4 text-center tracking-[0.5em] text-zolo-text"
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
        <p id={errorId} className="type-body min-h-6 text-zolo-critical">
          {error ? t(error) : busy ? t("pay.checking") : ""}
        </p>
      </div>
      <Link href="/" className="type-body text-zolo-secondary underline underline-offset-4">
        {t("pay.back")}
      </Link>
    </main>
  );
}
