/**
 * Money is an integer number of kobo, end to end. These helpers never use floating point: amounts
 * are split with BigInt, so there is no rounding to get wrong. (ESLint bans parseFloat, toFixed and
 * Math.round in this folder.)
 */

export class InvalidAmountError extends Error {
  constructor(value: unknown) {
    super(`Not a valid amount in kobo: ${String(value)}`);
    this.name = "InvalidAmountError";
  }
}

/** A valid amount is a non-negative, safe integer. Anything else is refused, never rendered. */
export function assertKobo(value: unknown): asserts value is number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) {
    throw new InvalidAmountError(value);
  }
}

export function splitKobo(kobo: number): { naira: bigint; kobo: number } {
  assertKobo(kobo);
  const total = BigInt(kobo);
  return { naira: total / 100n, kobo: Number(total % 100n) };
}

/** 1234567 -> "1,234,567". A fixed format: no locale, so the server and the browser always agree. */
export function groupDigits(n: bigint): string {
  const digits = n.toString();
  let out = "";
  for (let i = 0; i < digits.length; i++) {
    if (i > 0 && (digits.length - i) % 3 === 0) out += ",";
    out += digits[i];
  }
  return out;
}

/** 1500000 -> "₦15,000". Kobo only appear when there are some: 1500050 -> "₦15,000.50". */
export function formatNaira(kobo: number): string {
  const parts = splitKobo(kobo);
  const fraction = parts.kobo === 0 ? "" : `.${String(parts.kobo).padStart(2, "0")}`;
  return `₦${groupDigits(parts.naira)}${fraction}`;
}

/** Whole naira to kobo, by integer multiplication. Refuses anything that would not stay exact. */
export function nairaToKobo(naira: number): number {
  if (!Number.isSafeInteger(naira) || naira < 0) throw new InvalidAmountError(naira);
  const kobo = naira * 100;
  if (!Number.isSafeInteger(kobo)) throw new InvalidAmountError(naira);
  return kobo;
}
