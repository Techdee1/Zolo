"use client";

// A developer gallery, not product UI: its text is plain English on purpose. Real screens get
// their words from the message files (step 7).

import { useCallback, useEffect, useState } from "react";
import { AmountDisplay } from "@/components/ui/AmountDisplay";
import { Badge, type BadgeVariant } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Keypad } from "@/components/ui/Keypad";
import { useAnnounce } from "@/components/ui/LiveRegion";
import { Sheet } from "@/components/ui/Sheet";
import { TimeLeft } from "@/components/ui/TimeLeft";
import { appendDigit, deleteDigit } from "@/lib/format/amount-entry";
import { nairaToKobo } from "@/lib/format/money";

const BADGES: Array<[BadgeVariant, string]> = [
  ["verified", "Verified by bank"],
  ["paid", "Paid"],
  ["waiting", "Waiting"],
  ["processing", "Processing"],
  ["expiring", "Expiring soon"],
  ["declined", "Declined"],
  ["expired", "Expired"],
  ["changed", "Changed after you heard it"],
  ["failed", "Failed"],
];

const TIME_MESSAGES = {
  label: "Time left",
  oneMinute: "One minute left.",
  fifteenSeconds: "Fifteen seconds left.",
  expired: "Time is up.",
};

function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section aria-labelledby={id} className="mt-12 grid grid-cols-[minmax(0,1fr)] gap-4">
      <h2 id={id} className="type-headline">
        {title}
      </h2>
      {children}
    </section>
  );
}

export function KitchenSink() {
  const announce = useAnnounce();
  const [clicks, setClicks] = useState(0);
  const [naira, setNaira] = useState(0);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [expiresAt, setExpiresAt] = useState<number | null>(null);
  const [timeIsUp, setTimeIsUp] = useState(false);

  // Computed after mount, so the server and the browser never disagree about "now".
  useEffect(() => {
    const id = setTimeout(() => setExpiresAt(Date.now() + 105_000), 0);
    return () => clearTimeout(id);
  }, []);
  const restart = () => {
    setTimeIsUp(false);
    setExpiresAt(Date.now() + 120_000);
  };
  const onExpire = useCallback(() => setTimeIsUp(true), []);

  return (
    <main id="main" className="screen pb-24">
      <p className="wordmark">
        Zolo <span className="wordmark-sub">for Zenith Bank</span>
      </p>
      <h1 className="type-title">Component gallery</h1>
      <p className="type-secondary mt-2">
        Every component in every state. Not part of the product.
      </p>

      <Section id="buttons" title="Buttons">
        <Button variant="primary" onClick={() => setClicks((c) => c + 1)}>
          Approve ₦15,000
        </Button>
        <Button variant="primary" disabled disabledReason="Listen to the request first">
          Approve ₦15,000 (not yet)
        </Button>
        <Button variant="secondary" onClick={() => setClicks((c) => c + 1)}>
          Hear again
        </Button>
        <Button variant="tertiary" onClick={() => setClicks((c) => c + 1)}>
          No, decline am
        </Button>
        <Button variant="secondary" loading>
          Requesting
        </Button>
        <p role="status" className="type-secondary" data-testid="click-count">
          Button taps: {clicks}
        </p>
      </Section>

      <Section id="amounts" title="Amounts">
        <AmountDisplay kobo={1_500_000} unit="naira" showWords />
        <div>
          <p className="type-secondary">Large</p>
          <AmountDisplay kobo={5_000_000} unit="naira" size="large" />
        </div>
        <p className="type-body">
          You sent <AmountDisplay kobo={1_850_000} unit="naira" size="inline" className="inline" />{" "}
          to Mama Chi Stores.
        </p>
        <AmountDisplay kobo={1_500_050} unit="naira" size="large" />
        <AmountDisplay kobo={0} unit="naira" size="large" />
      </Section>

      <Section id="keypad" title="Amount keypad">
        <AmountDisplay kobo={nairaToKobo(naira)} unit="naira" showWords />
        <Keypad
          labels={{ group: "Amount keypad", clear: "Clear", backspace: "Delete last digit" }}
          onDigit={(d) => setNaira((n) => appendDigit(n, d))}
          onBackspace={() => setNaira(deleteDigit)}
          onClear={() => setNaira(0)}
        />
        <Button variant="primary" disabled={naira === 0} disabledReason="Type an amount first">
          Request
        </Button>
      </Section>

      <Section id="badges" title="Badges">
        <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
          {BADGES.map(([variant, label]) => (
            <li key={variant}>
              <Badge variant={variant}>{label}</Badge>
            </li>
          ))}
        </ul>
      </Section>

      <Section id="time" title="Time left">
        {expiresAt === null ? null : (
          <TimeLeft expiresAt={expiresAt} messages={TIME_MESSAGES} onExpire={onExpire} />
        )}
        <p className="type-secondary" data-testid="time-state">
          {timeIsUp ? "Expired" : "Counting down"}
        </p>
        <Button variant="secondary" onClick={restart}>
          Restart the timer
        </Button>
      </Section>

      <Section id="live" title="Live region">
        <Button
          variant="secondary"
          onClick={() => announce("Paid. You sent ₦15,000 to Bisi Ventures.")}
        >
          Announce politely
        </Button>
        <Button
          variant="secondary"
          onClick={() => announce("Something went wrong. Nothing was sent.", { assertive: true })}
        >
          Announce an error
        </Button>
      </Section>

      <Section id="sheet" title="Sheet">
        <Button variant="secondary" onClick={() => setSheetOpen(true)}>
          Open the sheet
        </Button>
        <Sheet
          open={sheetOpen}
          onClose={() => setSheetOpen(false)}
          title="A sheet"
          closeLabel="Close the sheet"
        >
          <p className="type-body">Escape, the button and a tap outside all close it.</p>
        </Sheet>
      </Section>
    </main>
  );
}
