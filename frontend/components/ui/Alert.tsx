import { AlertTriangle } from "lucide-react";
import type { ComponentProps } from "react";
import { cn } from "@/lib/cn";

/**
 * Something went wrong, said in a tinted card with a warning icon. The words carry the meaning (the
 * icon is decoration), and they stay in the normal text colour on the tint, so they are as easy to
 * read as anything else on the screen. Announcing it is the caller's job (through the live region).
 */
export function Alert({ className, children, ...rest }: ComponentProps<"p">) {
  return (
    <p {...rest} className={cn("callout critical type-body m-0", className)}>
      <AlertTriangle
        aria-hidden="true"
        size={22}
        strokeWidth={1.75}
        className="mt-0.5 shrink-0 text-zolo-critical"
      />
      <span>{children}</span>
    </p>
  );
}
