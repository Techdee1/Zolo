"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { PageHeading } from "@/components/PageHeading";
import { Screen } from "@/components/Screen";
import { SaidText } from "@/components/SaidText";
import { AmountDisplay } from "@/components/ui/AmountDisplay";
import { Button } from "@/components/ui/Button";
import { Keypad } from "@/components/ui/Keypad";
import { useAnnounce } from "@/components/ui/LiveRegion";
import { createAgentRequest } from "@/lib/api/endpoints";
import { redirectIfSignedOut, genericErrorKey } from "@/lib/errors";
import { appendDigit, deleteDigit } from "@/lib/format/amount-entry";
import { formatNaira, nairaToKobo } from "@/lib/format/money";
import { amountSpoken } from "@/lib/format/words";
import { useT } from "@/lib/i18n";
import { getSessionHint, setAgentRequest } from "@/lib/session-hint";

const CHIPS = [5_000, 10_000, 20_000] as const;

export function AgentNewRequest() {
  const t = useT();
  const router = useRouter();
  const announce = useAnnounce();
  const [naira, setNaira] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState<string | null>(null);
  // One key per amount: a retry after a dropped connection cannot create a second request.
  const key = useRef<string>("");

  useEffect(() => {
    const id = setTimeout(() => setName(getSessionHint()?.name ?? null), 0);
    return () => clearTimeout(id);
  }, []);

  // A blind agent hears the whole amount after they stop typing, not after every key.
  useEffect(() => {
    const id = setTimeout(
      () => announce(t("agent.amountNow", { amountWords: amountSpoken(nairaToKobo(naira)) })),
      600,
    );
    return () => clearTimeout(id);
  }, [naira, announce, t]);

  const change = (next: number) => {
    key.current = "";
    setError(null);
    setNaira(next);
  };

  async function submit() {
    if (busy || naira === 0) return;
    setBusy(true);
    setError(null);
    key.current ||= crypto.randomUUID();
    try {
      const made = await createAgentRequest(nairaToKobo(naira), key.current);
      setAgentRequest(made);
      router.push(`/agent/requests/${made.id}`);
    } catch (e) {
      if (redirectIfSignedOut(e, router)) return;
      const message = t(genericErrorKey(e));
      setError(message);
      announce(message, { assertive: true });
      setBusy(false);
    }
  }

  const kobo = nairaToKobo(naira);
  return (
    <Screen who="agent">
      <div className="grid gap-1">
        <PageHeading title={t("agent.title")} className="type-display">
          {t("agent.title")}
        </PageHeading>
        {name ? <p className="type-secondary m-0">{t("agent.business", { name })}</p> : null}
      </div>

      <section
        aria-label={t("agent.amountLabel")}
        className="rounded-zolo-card bg-zolo-elevated p-6 shadow-zolo-card"
      >
        <AmountDisplay kobo={kobo} unit={t("common.unit")} showWords />
      </section>

      <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
        {CHIPS.map((c) => (
          <li key={c}>
            <Button variant="secondary" onClick={() => change(c)}>
              <SaidText
                visible={formatNaira(nairaToKobo(c))}
                spoken={t("agent.chip", { amountWords: amountSpoken(nairaToKobo(c)) })}
              />
            </Button>
          </li>
        ))}
      </ul>

      <Keypad
        labels={{
          group: t("agent.keypad"),
          clear: t("agent.clear"),
          backspace: t("agent.backspace"),
        }}
        onDigit={(d) => change(appendDigit(naira, d))}
        onBackspace={() => change(deleteDigit(naira))}
        onClear={() => change(0)}
      />

      {error ? (
        <p className="type-body text-zolo-critical" role="presentation">
          {error}
        </p>
      ) : null}

      <div className="action-bar">
        <Button
          variant="primary"
          disabled={naira === 0}
          disabledReason={t("agent.requestNeedsAmount")}
          loading={busy}
          onClick={() => void submit()}
        >
          {naira === 0 ? (
            t("agent.requestEmpty")
          ) : (
            <SaidText
              visible={t("agent.request", { amount: formatNaira(kobo) })}
              spoken={t("agent.requestSpoken", { amountWords: amountSpoken(kobo) })}
            />
          )}
        </Button>
      </div>
    </Screen>
  );
}
