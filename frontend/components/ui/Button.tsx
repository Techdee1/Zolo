"use client";

import { useId, type ComponentProps, type ReactNode } from "react";
import { cn } from "@/lib/cn";

/**
 * - primary: the ONE red thing on a screen (the action that matters). Full width, 3.5rem tall.
 * - secondary: a calm filled button. tertiary: text only. Neither is red.
 *
 * Feedback is on pointer-DOWN (the button scales to 0.97 instantly, in CSS, so no JavaScript sits
 * on the input path) and commits on release; dragging away cancels. Under reduced motion the scale
 * is 1 (see --motion-press-scale), so nothing moves.
 *
 * A button that cannot be used yet is `aria-disabled`, NOT natively disabled: it stays in the tab
 * order, so a screen-reader user finds it and hears why (`disabledReason`) instead of never
 * learning it exists. Clicks are ignored while it is inactive.
 */
type Variant = "primary" | "secondary" | "tertiary" | "tile" | "chip";

export type ButtonProps = Omit<ComponentProps<"button">, "disabled" | "children" | "type"> & {
  children: ReactNode;
  variant?: Variant;
  /** Not usable yet. Always give a `disabledReason` so people hear why. */
  disabled?: boolean;
  disabledReason?: string;
  /** Busy: ignores clicks and says so (aria-busy). Nothing spins; "nothing loops". */
  loading?: boolean;
  icon?: ReactNode;
  type?: "button" | "submit";
  fullWidth?: boolean;
};

const BASE =
  "press relative inline-flex select-none items-center gap-2 " +
  "type-body font-semibold touch-manipulation " +
  "aria-disabled:cursor-not-allowed aria-disabled:active:scale-100";

// Each variant owns its shape, padding and alignment, so no two classes ever set the same thing.
const VARIANTS: Record<Variant, string> = {
  primary:
    "min-h-(--target-primary) w-full justify-center rounded-[16px] px-6 bg-zolo-brand text-zolo-on-brand shadow-zolo-primary " +
    "active:bg-zolo-brand-pressed " +
    "aria-disabled:border aria-disabled:border-zolo-separator aria-disabled:bg-zolo-elevated " +
    "aria-disabled:text-zolo-secondary aria-disabled:shadow-none aria-disabled:active:bg-zolo-elevated",
  secondary:
    "min-h-(--target-min) justify-center rounded-zolo-control px-6 bg-zolo-elevated text-zolo-text border border-zolo-separator shadow-zolo-card " +
    "aria-disabled:text-zolo-secondary",
  tertiary:
    "min-h-(--target-min) justify-center rounded-zolo-control px-6 bg-transparent text-zolo-text underline-offset-4 hover:underline aria-disabled:text-zolo-secondary",
  /** A whole card that is one button (the sign-in people): content laid out by the caller. */
  tile:
    "min-h-20 w-full justify-start rounded-zolo-card px-4 py-3 text-left bg-zolo-elevated text-zolo-text shadow-zolo-card " +
    "[&>span:last-child]:w-full aria-disabled:text-zolo-secondary",
  /** A quick choice in a row (the amount chips). */
  chip:
    "min-h-(--target-min) w-full justify-center rounded-full px-3 bg-zolo-elevated text-zolo-text border border-zolo-separator shadow-zolo-card tabular-nums " +
    "aria-disabled:text-zolo-secondary",
};

export function Button({
  variant = "secondary",
  disabled = false,
  disabledReason,
  loading = false,
  icon,
  type = "button",
  fullWidth,
  onClick,
  className,
  children,
  ...rest
}: ButtonProps) {
  const reasonId = useId();
  const inactive = disabled || loading;
  const describedBy = [rest["aria-describedby"], disabled && disabledReason ? reasonId : null]
    .filter(Boolean)
    .join(" ");

  return (
    <>
      <button
        {...rest}
        type={type}
        aria-disabled={inactive || undefined}
        aria-busy={loading || undefined}
        aria-describedby={describedBy || undefined}
        data-variant={variant}
        className={cn(
          BASE,
          VARIANTS[variant],
          fullWidth && variant !== "primary" && "w-full",
          className,
        )}
        onClick={(event) => {
          if (inactive) {
            event.preventDefault();
            return;
          }
          onClick?.(event);
        }}
      >
        {icon ? <span aria-hidden="true">{icon}</span> : null}
        <span>{children}</span>
      </button>
      {/* Beside the button, not inside it: inside, it would become part of the button's NAME and
          be read twice. aria-describedby makes it the DESCRIPTION. */}
      {disabled && disabledReason ? (
        <span id={reasonId} className="sr-only">
          {disabledReason}
        </span>
      ) : null}
    </>
  );
}
