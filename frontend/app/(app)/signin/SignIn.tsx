"use client";

import { ChevronRight } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { LanguagePicker } from "@/components/LanguagePicker";
import { PageHeading } from "@/components/PageHeading";
import { Screen } from "@/components/Screen";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { useAnnounce } from "@/components/ui/LiveRegion";
import { mockLogin } from "@/lib/api/endpoints";
import { genericErrorKey } from "@/lib/errors";
import { useT } from "@/lib/i18n";
import { setSessionHint } from "@/lib/session-hint";

/**
 * Demo sign-in. The backend has no account setup (agents are seeded) and no real phone login yet,
 * only `POST /auth/mock-login` with a fixed code. So instead of typing a phone number and a code,
 * you pick who you are. Nothing is typed, nothing secret is asked for.
 */
const PEOPLE = [
  { role: "customer", name: "Amaka Obi", phone: "+2348011111111", to: "/home" },
  { role: "agent", name: "Bisi Ventures", phone: "+2348022222222", to: "/agent" },
] as const;
const DEMO_CODE = "123456";

/** `next`: where a customer goes after signing in (already checked to be a path on this site).
 * Agents always go to their own screen. */
export function SignIn({ next }: { next?: string } = {}) {
  const t = useT();
  const router = useRouter();
  const announce = useAnnounce();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function signIn(person: (typeof PEOPLE)[number]) {
    setBusy(person.role);
    setError(null);
    try {
      const session = await mockLogin(person.phone, DEMO_CODE);
      setSessionHint({ role: session.role, name: session.display_name });
      router.push(person.role === "customer" && next ? next : person.to);
    } catch (e) {
      const message =
        e instanceof Error && "status" in e ? t("signin.failed") : t(genericErrorKey(e));
      setError(message);
      announce(message, { assertive: true });
      setBusy(null);
    }
  }

  return (
    <Screen
      back="/"
      hero={
        <div className="grid gap-3">
          <PageHeading title={t("signin.title")} className="type-display">
            {t("signin.title")}
          </PageHeading>
          <p className="type-body m-0 text-zolo-secondary">{t("signin.intro")}</p>
        </div>
      }
    >
      <div className="rise grid gap-3">
        {PEOPLE.map((p) => (
          <Button
            key={p.role}
            variant="tile"
            loading={busy === p.role}
            onClick={() => void signIn(p)}
          >
            {/* Seen: a person card. Heard: the one sentence, "I am a customer: Amaka Obi". */}
            <span aria-hidden="true" className="flex w-full items-center gap-4">
              <span className={`avatar ${p.role === "agent" ? "brand" : ""}`}>
                {p.name
                  .split(" ")
                  .map((w) => w[0])
                  .join("")
                  .slice(0, 2)}
              </span>
              <span className="grid flex-1 gap-0.5">
                <span className="type-headline">{p.name}</span>
                <span className="type-secondary">
                  {t(p.role === "customer" ? "role.customer" : "role.agent")}
                </span>
              </span>
              <ChevronRight size={22} className="text-zolo-secondary" />
            </span>
            <span className="sr-only">
              {t(p.role === "customer" ? "signin.customer" : "signin.agent", { name: p.name })}
            </span>
          </Button>
        ))}
      </div>
      {error ? <Alert>{error}</Alert> : null}
      <section className="surface rise p-5 [--rise:1]">
        <LanguagePicker />
      </section>
    </Screen>
  );
}
