"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { DemoMenu } from "@/components/DemoMenu";
import { cn } from "@/lib/cn";
import { env } from "@/lib/env";
import { useT } from "@/lib/i18n";

/**
 * The frame every screen sits in: the Zolo wordmark on the left and, on the right, a small label
 * saying whose screen this is (Customer or Agent) with the demo tools when the demo flag is on.
 * No banner and no heavy header: the label is a quiet pill, and agent screens also carry a faint
 * graphite tint (see .app-frame in globals.css), so the two are told apart at a glance without
 * relying on colour alone.
 *
 * `hero` opens the screen with the dark band (see .hero in globals.css): the header moves into it,
 * and what the screen is about (its heading, the amount) sits on black, the strongest contrast
 * there is. Everything else follows below on the light page.
 *
 * `back` is where the arrow at the top left goes. Every screen has one, and it is a fixed place
 * (the screen's parent), not the browser's history: a customer who opened a QR link has no history,
 * and the payment screens replace theirs, so "back" would otherwise go nowhere or somewhere odd.
 */
export function Screen({
  back,
  who,
  hero,
  className,
  children,
}: {
  back: string;
  who?: "customer" | "agent";
  hero?: ReactNode;
  className?: string;
  children?: ReactNode;
}) {
  const t = useT();
  const header = (
    <header className="flex min-h-(--target-min) items-center justify-between gap-3">
      <div className="flex min-w-0 items-center gap-2">
        <Link href={back} className="back-button press">
          <ArrowLeft aria-hidden="true" size={22} strokeWidth={2} />
          <span className="sr-only">{t("common.back")}</span>
        </Link>
        <p className="wordmark">
          <span aria-hidden="true" className="brand-mark">
            Z
          </span>
          <span>
            {t("app.name")} <span className="wordmark-sub">{t("app.forBank")}</span>
          </span>
        </p>
      </div>
      <div className="flex items-center gap-1">
        {who ? (
          <span
            className={cn(
              "type-caption rounded-full border px-3 py-1",
              who === "agent"
                ? "border-zolo-separator bg-zolo-graphite text-zolo-on-brand"
                : "border-zolo-separator bg-zolo-elevated text-zolo-secondary",
            )}
          >
            {t(who === "agent" ? "role.agent" : "role.customer")}
          </span>
        ) : null}
        {env.featureDemo ? <DemoMenu /> : null}
      </div>
    </header>
  );
  return (
    <main id="main" data-role={who} className={cn("screen grid content-start gap-6", className)}>
      {hero ? (
        <div className="hero">
          {header}
          {hero}
        </div>
      ) : (
        header
      )}
      {children}
    </main>
  );
}
