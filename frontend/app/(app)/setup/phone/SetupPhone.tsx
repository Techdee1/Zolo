"use client";

import { BadgeCheck, Phone, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { PageHeading } from "@/components/PageHeading";
import { Screen } from "@/components/Screen";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { useAnnounce } from "@/components/ui/LiveRegion";
import { isApiError } from "@/lib/api/client";
import { enrolPhone } from "@/lib/api/endpoints";
import { genericErrorKey, redirectIfSignedOut } from "@/lib/errors";
import { useT, type MessageKey } from "@/lib/i18n";
import { LINK_PRIMARY } from "@/lib/styles";

const FIELD =
  "type-body min-h-(--target-min) w-full rounded-zolo-control border border-zolo-separator " +
  "bg-zolo-elevated px-4 text-zolo-text";

/**
 * Sets the number Zolo rings and a four digit Zolo PIN for phone approval. The PIN is only ever
 * typed here and on the call; the server keeps a salted hash and nothing else.
 */
export function SetupPhone({ next }: { next: string }) {
  const t = useT();
  const router = useRouter();
  const announce = useAnnounce();
  const [phone, setPhone] = useState("");
  const [pin, setPin] = useState("");
  const [language, setLanguage] = useState<"en" | "pcm" | "yo">("en");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<MessageKey | null>(null);

  async function save(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await enrolPhone(phone.replace(/[\s-]/g, ""), pin, language);
      setDone(true);
      announce(t("phone.saved"));
    } catch (err) {
      if (redirectIfSignedOut(err, router)) return;
      const key: MessageKey = isApiError(err)
        ? err.code === "VALIDATION_ERROR" && err.status === 422
          ? /pin|stronger/i.test(err.message)
            ? "phone.weakPin"
            : "phone.badNumber"
          : err.code === "STATE_CONFLICT"
            ? "phone.numberTaken"
            : genericErrorKey(err)
        : "errors.generic";
      setError(key);
      announce(t(key), { assertive: true });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen
      back={next}
      who="customer"
      hero={
        <div className="grid gap-3">
          <span aria-hidden="true" className="icon-tile size-14 rounded-[18px] text-zolo-text">
            <Phone size={30} strokeWidth={1.75} />
          </span>
          <PageHeading title={t("phone.setupTitle")} className="type-display">
            {t("phone.setupTitle")}
          </PageHeading>
        </div>
      }
    >
      <ul className="surface rows inset rise m-0 list-none p-0">
        {(
          [
            [Phone, "phone.setupWhat", "text-zolo-text"],
            [ShieldCheck, "phone.setupPin", "text-zolo-success"],
            [BadgeCheck, "phone.setupLimit", "text-zolo-secondary"],
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

      <form onSubmit={(e) => void save(e)} className="grid gap-4">
        <label className="grid gap-1">
          <span className="type-headline">{t("phone.numberLabel")}</span>
          <input
            className={FIELD}
            type="tel"
            inputMode="tel"
            autoComplete="tel"
            required
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            aria-describedby="phone-hint"
          />
          <span id="phone-hint" className="type-secondary">
            {t("phone.numberHint")}
          </span>
        </label>
        <label className="grid gap-1">
          <span className="type-headline">{t("phone.pinLabel")}</span>
          <input
            className={FIELD}
            type="password"
            inputMode="numeric"
            autoComplete="off"
            pattern="[0-9]{4}"
            maxLength={4}
            required
            value={pin}
            onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
            aria-describedby="pin-hint"
          />
          <span id="pin-hint" className="type-secondary">
            {t("phone.pinHint")}
          </span>
        </label>
        <fieldset className="grid gap-2 border-0 p-0">
          <legend className="type-headline mb-1">{t("phone.languageLabel")}</legend>
          {(["en", "pcm", "yo"] as const).map((l) => (
            <label key={l} className="type-body flex min-h-(--target-min) items-center gap-3">
              <input
                type="radio"
                name="call-language"
                checked={language === l}
                onChange={() => setLanguage(l)}
              />
              {t(l === "en" ? "phone.langEn" : l === "pcm" ? "phone.langPcm" : "phone.langYo")}
            </label>
          ))}
        </fieldset>

        {error ? <Alert>{t(error)}</Alert> : null}
        {done ? (
          <p className="surface type-headline m-0 flex items-center gap-3 p-4">
            <span aria-hidden="true" className="icon-tile round text-zolo-success">
              <BadgeCheck size={22} strokeWidth={1.75} />
            </span>
            {t("phone.saved")}
          </p>
        ) : null}

        <div className="action-bar mt-auto">
          {done ? (
            <Link href={next} className={LINK_PRIMARY}>
              {t("common.done")}
            </Link>
          ) : (
            <Button variant="primary" type="submit" loading={busy}>
              {busy ? t("phone.saving") : t("phone.save")}
            </Button>
          )}
        </div>
      </form>
    </Screen>
  );
}
