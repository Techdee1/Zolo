/**
 * The agent types an amount in whole naira on the keypad. Pure integer functions, so what is shown
 * is exactly what will be sent. (This keypad is for AMOUNTS only. Zolo never asks for a PIN.)
 */
export const MAX_NAIRA_ENTRY = 100_000; // the backend's hard per-payment cap

export type Digit = 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9;

/** Add a digit on the right. Ignored if it would pass the cap, so the screen never lies. */
export function appendDigit(naira: number, digit: Digit, max: number = MAX_NAIRA_ENTRY): number {
  const next = naira * 10 + digit;
  return Number.isSafeInteger(next) && next <= max ? next : naira;
}

/** Remove the last digit: 15000 -> 1500. */
export function deleteDigit(naira: number): number {
  return (naira - (naira % 10)) / 10;
}
