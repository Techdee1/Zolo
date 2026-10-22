"use client";

import { Wrench } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Sheet } from "@/components/ui/Sheet";
import { useT } from "@/lib/i18n";

const ROW =
  "press flex min-h-(--target-min) items-center rounded-zolo-control bg-zolo-grouped px-4 type-body text-zolo-text";

/**
 * Demo tools, kept out of the customer's screens: a small button that opens a sheet. It is only
 * rendered when the demo flag is on, so a real customer never sees it.
 */
export function DemoMenu() {
  const t = useT();
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        className="press grid size-(--target-min) place-items-center rounded-full text-zolo-secondary"
      >
        <Wrench aria-hidden="true" size={20} strokeWidth={1.75} />
        <span className="sr-only">{t("demoMenu.open")}</span>
      </button>
      <Sheet
        open={open}
        onClose={() => setOpen(false)}
        title={t("demoMenu.title")}
        closeLabel={t("demoMenu.close")}
      >
        <nav aria-label={t("demoMenu.title")} className="grid gap-2">
          <Link href="/signin" className={ROW} onClick={() => setOpen(false)}>
            {t("demoMenu.switchUser")}
          </Link>
          <Link href="/demo" className={ROW} onClick={() => setOpen(false)}>
            {t("demoMenu.console")}
          </Link>
        </nav>
      </Sheet>
    </>
  );
}
