"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { PageHeading } from "@/components/PageHeading";
import { Screen } from "@/components/Screen";
import { Button } from "@/components/ui/Button";
import { useAnnounce } from "@/components/ui/LiveRegion";
import { getRegisterOptions, verifyRegistration } from "@/lib/api/endpoints";
import { isApiError } from "@/lib/api/client";
import { genericErrorKey, redirectIfSignedOut } from "@/lib/errors";
import { useT, type MessageKey } from "@/lib/i18n";
import { LINK_PRIMARY } from "@/lib/styles";
import { setPasskeyKnown } from "@/lib/passkey-status";
import { classifyPasskeyError, createPasskey, passkeySupport } from "@/lib/passkeys";

/**
 * Makes the passkey that approves payments. Two sentences say what it is, one says Zolo never asks
 * for a PIN, and one asks the customer to set their screen lock in private. The browser then shows
 * its OWN prompt: Zolo draws no PIN pad and sees no secret.
 */
export function SetupPasskey({ next }: { next: string }) {
  const t = useT();
  const router = useRouter();
  const announce = useAnnounce();
  const [support, setSupport] = useState<"checking" | "ok" | "unsupported" | "no-lock">("checking");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<MessageKey | null>(null);
  const [error, setError] = useState<MessageKey | null>(null);

  useEffect(() => {
    let live = true;
    void passkeySupport().then((s) => live && setSupport(s));
    return () => {
      live = false;
    };
  }, []);

  function say(key: MessageKey, assertive: boolean) {
    announce(t(key), { assertive });
  }

  async function start() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const options = await getRegisterOptions();
      const credential = await createPasskey(options);
      const saved = await verifyRegistration(credential);
      const key: MessageKey = saved.replaced_previous ? "passkey.doneReplaced" : "passkey.done";
      setPasskeyKnown(true);
      setDone(key);
      say(key, false);
    } catch (e) {
      if (redirectIfSignedOut(e, router)) return;
      const key: MessageKey = isApiError(e)
        ? e.code === "PASSKEY_REGISTRATION_FAILED"
          ? "passkey.failed"
          : genericErrorKey(e)
        : (
            {
              cancelled: "passkey.cancelled",
              already: "passkey.already",
              unsupported: "passkey.noLock",
              other: "passkey.failed",
            } as const
          )[classifyPasskeyError(e)];
      if (key === "passkey.already") setPasskeyKnown(true); // the browser says this phone has it
      setError(key);
      say(key, true);
    } finally {
      setBusy(false);
    }
  }

  const blocked = support === "unsupported" || support === "no-lock";
  return (
    <Screen who="customer">
      <PageHeading title={t("passkey.title")}>{t("passkey.title")}</PageHeading>
      <div className="grid gap-3">
        <p className="type-body">{t("passkey.what")}</p>
        <p className="type-body">{t("passkey.never")}</p>
        <p className="type-body text-zolo-secondary">{t("passkey.private")}</p>
      </div>

      {blocked ? (
        <p className="type-body text-zolo-critical">
          {t(support === "unsupported" ? "passkey.unsupported" : "passkey.noLock")}
        </p>
      ) : null}
      {error ? <p className="type-body text-zolo-critical">{t(error)}</p> : null}

      {done ? (
        <>
          <p className="type-headline">{t(done)}</p>
          <Link href={next} className={LINK_PRIMARY}>
            {t("common.done")}
          </Link>
        </>
      ) : (
        <Button
          variant="primary"
          loading={busy}
          disabled={blocked}
          disabledReason={t("passkey.noLock")}
          onClick={() => void start()}
        >
          {busy ? t("passkey.working") : t("passkey.start")}
        </Button>
      )}
    </Screen>
  );
}
