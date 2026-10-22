import { cn } from "@/lib/cn";
import { assertKobo, formatNaira } from "@/lib/format/money";
import { amountSpoken } from "@/lib/format/words";

/**
 * An amount, from integer kobo. Sighted people see "₦15,000"; screen-reader users hear "fifteen
 * thousand naira" (screen readers mangle the symbol and the commas).
 *
 * How, without aria-label: ARIA does not allow a name on a plain span (axe flags it), so the digits
 * are aria-hidden and the words are real text next to them. With `showWords`, the words are also
 * shown under the amount (the review screen), and then they ARE the accessible text, so nothing is
 * read twice.
 *
 * `words` may carry the backend's own words (the readback's `amount_words`, e.g. "fifteen
 * thousand"), so the screen and the spoken readback use the same ones. An invalid amount throws:
 * money data that failed validation is never rendered.
 */
type Size = "hero" | "large" | "inline";

export type AmountDisplayProps = {
  kobo: number;
  /** The words for the number, without "naira". Defaults to our own, which match the backend's. */
  words?: string;
  /** The currency word, which is "naira" in every language. */
  unit: string;
  size?: Size;
  showWords?: boolean;
  className?: string;
};

const SIZES: Record<Size, string> = {
  hero: "type-amount",
  large: "type-headline tabular-nums",
  inline: "tabular-nums",
};

export function AmountDisplay({
  kobo,
  words,
  unit,
  size = "hero",
  showWords = false,
  className,
}: AmountDisplayProps) {
  assertKobo(kobo);
  const digits = formatNaira(kobo);
  const spoken = words ? `${words} ${unit}` : amountSpoken(kobo);

  return (
    <span className={cn(size !== "inline" && "block", className)}>
      <span aria-hidden="true" className={cn(SIZES[size], "[overflow-wrap:anywhere]")}>
        {digits}
      </span>
      {showWords ? (
        <span className="type-secondary mt-1 block">{spoken}</span>
      ) : (
        <span className="sr-only">{spoken}</span>
      )}
    </span>
  );
}
