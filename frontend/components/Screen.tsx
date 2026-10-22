import type { ReactNode } from "react";
import { DemoMenu } from "@/components/DemoMenu";
import { cn } from "@/lib/cn";
import { env } from "@/lib/env";
import { t } from "@/lib/i18n";

/**
 * The frame every screen sits in: the Zolo wordmark on the left and, on the right, a small label
 * saying whose screen this is (Customer or Agent) with the demo tools when the demo flag is on.
 * No banner and no heavy header: the label is a quiet pill, and agent screens also carry a faint
 * graphite tint (see .app-frame in globals.css), so the two are told apart at a glance without
 * relying on colour alone.
 */
export function Screen({
  who,
  className,
  children,
}: {
  who?: "customer" | "agent";
  className?: string;
  children: ReactNode;
}) {
  return (
    <main id="main" data-role={who} className={cn("screen grid content-start gap-6", className)}>
      <header className="flex min-h-(--target-min) items-center justify-between gap-3">
        <p className="wordmark">
          {t("app.name")} <span className="wordmark-sub">{t("app.forBank")}</span>
        </p>
        <div className="flex items-center gap-1">
          {who ? (
            <span
              className={cn(
                "type-caption rounded-full border px-3 py-1",
                who === "agent"
                  ? "border-transparent bg-zolo-graphite text-zolo-on-brand"
                  : "border-zolo-separator bg-zolo-elevated text-zolo-secondary",
              )}
            >
              {t(who === "agent" ? "role.agent" : "role.customer")}
            </span>
          ) : null}
          {env.featureDemo ? <DemoMenu /> : null}
        </div>
      </header>
      {children}
    </main>
  );
}
