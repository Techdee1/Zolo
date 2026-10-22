"use client";

import { useLayoutEffect, useRef, type ReactNode } from "react";
import { animate } from "motion";
import { Badge, type BadgeVariant } from "@/components/ui/Badge";
import { PageHeading } from "@/components/PageHeading";
import { SaidText } from "@/components/SaidText";
import { FADE_SECONDS, SPRING, toSpring } from "@/lib/motion";

/**
 * One outcome per screen: a badge (icon and words), one line that says what happened and whether
 * money moved, a second line on what to do, and ONE next action. Used for the customer's result
 * and the agent's, so Paid, Processing, Declined, Expired and Failed always look and read the same.
 *
 * Colour never carries the meaning alone: every outcome has an icon and words. Paid gets a short
 * settle-in (opacity and transform only; just a fade under reduced motion).
 */
export function ResultView({
  variant,
  badge,
  title,
  titleSpoken,
  body,
  bodySpoken,
  extra,
  action,
  quiet = false,
}: {
  variant: BadgeVariant;
  badge: string;
  title: string;
  /** The title with its amount in words, for screen readers (the visible title has the digits). */
  titleSpoken?: string;
  body?: string;
  bodySpoken?: string;
  extra?: ReactNode;
  action: ReactNode;
  /** Do not move focus here: the screen is changing in place and the live region says so. */
  quiet?: boolean;
}) {
  const card = useRef<HTMLDivElement>(null);

  // Before the first paint, so "Paid" never flashes at full strength and then fades in.
  useLayoutEffect(() => {
    const el = card.current;
    if (!el || variant !== "paid") return;
    // Asked directly: a hook answers "unknown" on the first render and would restart the animation.
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    const controls = reduced
      ? animate(el, { opacity: [0, 1] }, { duration: FADE_SECONDS })
      : animate(
          el,
          { opacity: [0, 1], transform: ["scale(0.96)", "scale(1)"] },
          toSpring(SPRING.default),
        );
    return () => controls.stop();
  }, [variant]);

  return (
    <main id="main" className="screen grid gap-6" data-result={variant}>
      <div ref={card} className="grid gap-4">
        <Badge variant={variant}>{badge}</Badge>
        <PageHeading title={title} manualFocus={quiet} className="type-headline">
          {titleSpoken ? <SaidText visible={title} spoken={titleSpoken} /> : title}
        </PageHeading>
        {body ? (
          <p className="type-body text-zolo-secondary">
            {bodySpoken ? <SaidText visible={body} spoken={bodySpoken} /> : body}
          </p>
        ) : null}
        {extra}
      </div>
      <div className="grid gap-3">{action}</div>
    </main>
  );
}
