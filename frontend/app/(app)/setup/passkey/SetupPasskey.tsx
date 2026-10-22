"use client";

import { BadgeCheck, EyeOff, Fingerprint, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { PageHeading } from "@/components/PageHeading";
import { Screen } from "@/components/Screen";
import { Alert } from "@/components/ui/Alert";
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
    <Screen
      back={next}
      who="customer"
      hero={
        <div className="grid gap-3">
          <span aria-hidden="true" className="icon-tile size-14 rounded-[18px] text-zolo-text">
            <Fingerprint size={30} strokeWidth={1.75} />
          </span>
          <PageHeading title={t("passkey.title")} className="type-display">
            {t("passkey.title")}
          </PageHeading>
        </div>
      }
    >
      <ul className="surface rows inset rise m-0 list-none p-0">
        {(
          [
            [Fingerprint, "passkey.what", "text-zolo-text"],
            [ShieldCheck, "passkey.never", "text-zolo-success"],
            [EyeOff, "passkey.private", "text-zolo-secondary"],
          ] as const
        ).map(([Icon, key, tone]) => (
          <li key={key} className="flex items-start gap-4 p-4">
            <span aria-hidden="true" className={`icon-tile ${tone}`}>
              <Icon size={22} strokeWidth={1.75} />
            </span>
            <p className="type-body m-0 self-center">{t(key)}</p>
          </li>
        ))}
      </ul>

      {blocked ? (
        <Alert>{t(support === "unsupported" ? "passkey.unsupported" : "passkey.noLock")}</Alert>
      ) : null}
      {error ? <Alert>{t(error)}</Alert> : null}

      {done ? (
        <p className="surface type-headline m-0 flex items-center gap-3 p-4">
          <span aria-hidden="true" className="icon-tile round text-zolo-success">
            <BadgeCheck size={22} strokeWidth={1.75} />
          </span>
          {t(done)}
        </p>
      ) : null}

      <div className="action-bar mt-auto">
        {done ? (
          <Link href={next} className={LINK_PRIMARY}>
            {t("common.done")}
          </Link>
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
      </div>
    </Screen>
  );
}
