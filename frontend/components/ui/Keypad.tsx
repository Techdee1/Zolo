"use client";

import { Delete } from "lucide-react";
import type { Digit } from "@/lib/format/amount-entry";
import { cn } from "@/lib/cn";

/**
 * A keypad for typing an AMOUNT, and only an amount. Zolo never asks for a PIN, a card number or
 * an OTP, so there is no masking, no "secure" mode and no way to use this for one.
 *
 * Real buttons, each with its own name, in a labelled group; keys are at least 56px with 8px
 * between them; every key works with a single tap. Press feedback is the same instant scale as
 * Button (none under reduced motion). No vibration per key: haptics are for meaningful moments.
 */
export type KeypadLabels = {
  group: string; // "Amount keypad"
  clear: string; // "Clear amount"
  backspace: string; // "Delete last digit"
};

export type KeypadProps = {
  onDigit: (digit: Digit) => void;
  onBackspace: () => void;
  onClear: () => void;
  labels: KeypadLabels;
  className?: string;
};

const KEY =
  "inline-flex min-h-14 items-center justify-center rounded-zolo-card " +
  "press bg-zolo-elevated text-zolo-text shadow-zolo-card touch-manipulation select-none tabular-nums";
const DIGIT = cn(KEY, "type-title");

const ROWS: Digit[][] = [
  [1, 2, 3],
  [4, 5, 6],
  [7, 8, 9],
];

export function Keypad({ onDigit, onBackspace, onClear, labels, className }: KeypadProps) {
  return (
    <div role="group" aria-label={labels.group} className={cn("grid grid-cols-3 gap-2", className)}>
      {ROWS.flat().map((d) => (
        <button key={d} type="button" className={DIGIT} onClick={() => onDigit(d)}>
          {d}
        </button>
      ))}
      <button
        type="button"
        className={cn(KEY, "type-body min-w-0 font-semibold [overflow-wrap:anywhere]")}
        onClick={onClear}
      >
        {labels.clear}
      </button>
      <button type="button" className={DIGIT} onClick={() => onDigit(0)}>
        0
      </button>
      <button type="button" className={DIGIT} aria-label={labels.backspace} onClick={onBackspace}>
        <Delete aria-hidden="true" size={24} strokeWidth={1.75} />
      </button>
    </div>
  );
}
