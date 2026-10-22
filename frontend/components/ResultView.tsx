"use client";

import { useLayoutEffect, useRef, type ReactNode } from "react";
import { animate } from "motion";
import { PageHeading } from "@/components/PageHeading";
import { SaidText } from "@/components/SaidText";
import { Screen } from "@/components/Screen";
import { STYLE, type BadgeVariant } from "@/components/ui/Badge";
import { FADE_SECONDS, SPRING, toSpring } from "@/lib/motion";

/**
 * One outcome per screen: a large icon, one line that says what happened and whether money moved,
 * a second line on what to do, and ONE next action at the bottom.
 *
 * Colour never carries the meaning alone: the icon and the words always do. Paid gets a short,
 * calm settle-in (opacity and transform only; just a fade under reduced motion), and the icon
 * lands a beat after the card, so the eye is led from the words to the check.
 */
export function ResultView({
  variant,
  who,
  title,
  titleSpoken,
  body,
  bodySpoken,
  extra,
  visual,
  action,
  quiet = false,
}: {
  variant: BadgeVariant;
  who: "customer" | "agent";
  title: string;
  /** The title with its amount in words, for screen readers (the visible title has the digits). */
  titleSpoken?: string;
  body?: string;
  bodySpoken?: string;
  extra?: ReactNode;
  /** A designed version of the title for the eye (say, "Paid", the big amount, "to Bisi"). When
   * given, the title above stays as the h1 for assistive tech and is not shown twice. */
  visual?: ReactNode;
  action: ReactNode;
  /** Do not move focus here: the screen is changing in place and the live region says so. */
  quiet?: boolean;
}) {
  const card = useRef<HTMLDivElement>(null);
  const icon = useRef<HTMLSpanElement>(null);
  const { icon: Icon, tone } = STYLE[variant];

  // Before the first paint, so "Paid" never flashes at full strength and then fades in.
  useLayoutEffect(() => {
    const el = card.current;
    const badge = icon.current;
    if (!el || !badge || variant !== "paid") return;
    // Asked directly: a hook answers "unknown" on the first render and would restart the animation.
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    const controls = reduced
      ? [animate(el, { opacity: [0, 1] }, { duration: FADE_SECONDS })]
      : [
          animate(
            el,
            { opacity: [0, 1], transform: ["translateY(8px)", "translateY(0px)"] },
            toSpring(SPRING.default),
          ),
          animate(
            badge,
            { transform: ["scale(0.8)", "scale(1)"] },
            { ...toSpring(SPRING.default), delay: 0.12 },
          ),
        ];
    return () => controls.forEach((c) => c.stop());
  }, [variant]);

  return (
    <Screen who={who} className="min-h-[calc(100dvh-var(--space-8))] grid-rows-[auto_1fr_auto]">
      <div
        ref={card}
        data-result={variant}
        className="grid content-center justify-items-center gap-4 py-8 text-center"
      >
        <span
          ref={icon}
          data-variant={variant}
          className={`grid size-20 place-items-center rounded-full bg-zolo-elevated shadow-zolo-card ${tone}`}
        >
          <Icon aria-hidden="true" size={40} strokeWidth={1.5} />
        </span>
        <PageHeading
          title={title}
          manualFocus={quiet}
          className={visual ? "sr-only" : "type-title mt-2"}
        >
          {titleSpoken ? <SaidText visible={title} spoken={titleSpoken} /> : title}
        </PageHeading>
        {visual ? (
          <div aria-hidden="true" className="grid justify-items-center gap-1">
            {visual}
          </div>
        ) : null}
        {extra}
        {body ? (
          <p className="type-body m-0 max-w-[22rem] text-zolo-secondary">
            {bodySpoken ? <SaidText visible={body} spoken={bodySpoken} /> : body}
          </p>
        ) : null}
      </div>
      <div className="action-bar grid gap-3">{action}</div>
    </Screen>
  );
}
