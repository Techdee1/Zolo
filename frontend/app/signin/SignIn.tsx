"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { PageHeading } from "@/components/PageHeading";
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
  { role: "customer", name: "Amaka Obi", phone: "+2348011111111", to: "/" },
  { role: "agent", name: "Bisi Ventures", phone: "+2348022222222", to: "/agent" },
] as const;
const DEMO_CODE = "123456";

export function SignIn() {
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
      router.push(person.to);
    } catch (e) {
      const message =
        e instanceof Error && "status" in e ? t("signin.failed") : t(genericErrorKey(e));
      setError(message);
      announce(message, { assertive: true });
      setBusy(null);
    }
  }

  return (
    <main id="main" className="screen grid gap-6">
      <p className="wordmark">
        {t("app.name")} <span className="wordmark-sub">{t("app.forBank")}</span>
      </p>
      <PageHeading title={t("signin.title")}>{t("signin.title")}</PageHeading>
      <p className="type-body text-zolo-secondary">{t("signin.intro")}</p>
      <div className="grid gap-3">
        {PEOPLE.map((p) => (
          <Button
            key={p.role}
            variant="secondary"
            fullWidth
            loading={busy === p.role}
            onClick={() => void signIn(p)}
          >
            {t(p.role === "customer" ? "signin.customer" : "signin.agent", { name: p.name })}
          </Button>
        ))}
      </div>
      {error ? <p className="type-body text-zolo-critical">{error}</p> : null}
    </main>
  );
}
