import {
  AlertTriangle,
  BadgeCheck,
  CheckCircle2,
  Clock,
  Hourglass,
  OctagonAlert,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/cn";

/**
 * A status label. It ALWAYS has an icon and words: colour is never the only signal. The icon is
 * decoration (aria-hidden); the words carry the meaning.
 *
 * `processing` is "the approval went through but the bank has not confirmed". It deliberately has
 * no check mark and no success colour: it must never look like "Paid".
 */
export type BadgeVariant =
  | "verified"
  | "paid"
  | "waiting"
  | "processing"
  | "expiring"
  | "declined"
  | "expired"
  | "changed"
  | "failed";

export const STYLE: Record<BadgeVariant, { icon: LucideIcon; tone: string }> = {
  verified: { icon: BadgeCheck, tone: "text-zolo-success" },
  paid: { icon: CheckCircle2, tone: "text-zolo-success" },
  waiting: { icon: Clock, tone: "text-zolo-secondary" },
  processing: { icon: Hourglass, tone: "text-zolo-warning" },
  expiring: { icon: Clock, tone: "text-zolo-warning" },
  declined: { icon: XCircle, tone: "text-zolo-secondary" },
  expired: { icon: Clock, tone: "text-zolo-secondary" },
  changed: { icon: OctagonAlert, tone: "text-zolo-critical" },
  failed: { icon: AlertTriangle, tone: "text-zolo-critical" },
};

export function Badge({
  variant,
  children,
  className,
}: {
  variant: BadgeVariant;
  children: React.ReactNode;
  className?: string;
}) {
  const { icon: Icon, tone } = STYLE[variant];
  return (
    <span
      data-variant={variant}
      className={cn(
        "type-caption inline-flex items-center gap-1.5 rounded-full border border-zolo-separator bg-zolo-elevated px-3 py-1",
        tone,
        className,
      )}
    >
      <Icon aria-hidden="true" size={16} strokeWidth={1.75} />
      <span>{children}</span>
    </span>
  );
}
