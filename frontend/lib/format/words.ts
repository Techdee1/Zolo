/**
 * Amounts in English words, for screen readers (screen readers mangle "₦15,000").
 *
 * It follows the backend's own number-to-words (backend/zolo/ai/nlu/words.py): space separated, no
 * "and" inside the number, up to 999,999,999,999 naira. A test compares it with 700+ amounts the
 * backend produced, so the words on a screen and the words in the spoken readback agree.
 */
import { splitKobo } from "./money";

const UNITS = [
  "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
  "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen",
]; // prettier-ignore
const TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"];
const SCALES: ReadonlyArray<readonly [bigint, string]> = [
  [1_000_000_000n, "billion"],
  [1_000_000n, "million"],
  [1_000n, "thousand"],
];
const MAX_NAIRA = 999_999_999_999n;

function below1000(n: number): string[] {
  const out: string[] = [];
  let rest = n;
  if (rest >= 100) {
    out.push(UNITS[Math.trunc(rest / 100)]!, "hundred");
    rest %= 100;
  }
  if (rest >= 20) {
    out.push(TENS[Math.trunc(rest / 10)]!);
    rest %= 10;
    if (rest) out.push(UNITS[rest]!);
  } else if (rest || out.length === 0) {
    out.push(UNITS[rest]!);
  }
  return out;
}

export function intToWords(value: bigint): string {
  if (value < 0n || value > MAX_NAIRA) throw new RangeError("amount out of range for words");
  if (value === 0n) return "zero";
  const parts: string[] = [];
  let n = value;
  for (const [size, name] of SCALES) {
    if (n >= size) {
      parts.push(...below1000(Number(n / size)), name);
      n %= size;
    }
  }
  if (n > 0n) parts.push(...below1000(Number(n)));
  return parts.join(" ");
}

/** The number part only, e.g. "fifteen thousand". Whole naira, like the readback. */
export function nairaWords(kobo: number): string {
  return intToWords(splitKobo(kobo).naira);
}

/** What a screen reader should say: "fifteen thousand naira", or "... naira and fifty kobo". */
export function amountSpoken(kobo: number): string {
  const { naira, kobo: rest } = splitKobo(kobo);
  const nairaPart = `${intToWords(naira)} naira`;
  return rest === 0 ? nairaPart : `${nairaPart} and ${intToWords(BigInt(rest))} kobo`;
}
