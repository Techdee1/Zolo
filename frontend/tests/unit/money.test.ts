import { describe, expect, it } from "vitest";
import { MAX_NAIRA_ENTRY, appendDigit, deleteDigit } from "@/lib/format/amount-entry";
import {
  InvalidAmountError,
  assertKobo,
  formatNaira,
  groupDigits,
  nairaToKobo,
  splitKobo,
} from "@/lib/format/money";

describe("formatNaira (integer kobo in, text out)", () => {
  it.each([
    [0, "₦0"],
    [100, "₦1"],
    [1_500_000, "₦15,000"],
    [5_100_000, "₦51,000"],
    [10_000_000, "₦100,000"],
    [123_456_700, "₦1,234,567"],
    [100_000_000_000, "₦1,000,000,000"],
  ])("%i kobo is %s", (kobo, text) => expect(formatNaira(kobo)).toBe(text));

  it("shows kobo only when there are some, always two digits", () => {
    expect(formatNaira(1)).toBe("₦0.01");
    expect(formatNaira(1_500_050)).toBe("₦15,000.50");
    expect(formatNaira(1_500_005)).toBe("₦15,000.05");
    expect(formatNaira(99)).toBe("₦0.99");
  });

  it("is exact at the largest integer JavaScript can hold (no float rounding)", () => {
    expect(formatNaira(Number.MAX_SAFE_INTEGER)).toBe("₦90,071,992,547,409.91");
  });

  it("uses a fixed format, never the machine's locale", () => {
    expect(formatNaira(123_456_700)).toBe("₦1,234,567");
  });
});

describe("amounts that are not valid are refused, never rendered", () => {
  it.each([
    ["a float", 1500000.5],
    ["a negative", -100],
    ["NaN", Number.NaN],
    ["Infinity", Number.POSITIVE_INFINITY],
    ["a string", "1500000"],
    ["null", null],
    ["undefined", undefined],
    ["past the safe integer limit", Number.MAX_SAFE_INTEGER + 2],
  ])("%s", (_label, value) => {
    expect(() => assertKobo(value)).toThrow(InvalidAmountError);
    expect(() => formatNaira(value as number)).toThrow(InvalidAmountError);
  });
});

describe("splitting and grouping", () => {
  it("splits kobo into naira and kobo without division by float", () => {
    expect(splitKobo(1_500_050)).toEqual({ naira: 15_000n, kobo: 50 });
    expect(splitKobo(99)).toEqual({ naira: 0n, kobo: 99 });
  });
  it("groups digits in threes", () => {
    expect([1n, 12n, 123n, 1234n, 123456n, 1234567n].map(groupDigits)).toEqual([
      "1",
      "12",
      "123",
      "1,234",
      "123,456",
      "1,234,567",
    ]);
  });
});

describe("nairaToKobo", () => {
  it("multiplies whole naira by 100", () => expect(nairaToKobo(15_000)).toBe(1_500_000));
  it("refuses anything that would not stay exact", () => {
    for (const bad of [1.5, -1, Number.NaN, Number.MAX_SAFE_INTEGER]) {
      expect(() => nairaToKobo(bad)).toThrow(InvalidAmountError);
    }
  });
});

describe("keypad amount entry (whole naira)", () => {
  const type = (digits: number[]) => digits.reduce((n, d) => appendDigit(n, d as 0, 100_000), 0);
  it("types left to right", () => expect(type([1, 5, 0, 0, 0])).toBe(15_000));
  it("ignores leading zeros", () => expect(type([0, 0, 5])).toBe(5));
  it("refuses a digit that would pass the cap, so the screen never shows an amount it cannot send", () => {
    expect(type([1, 0, 0, 0, 0, 0])).toBe(100_000);
    expect(appendDigit(100_000, 0)).toBe(100_000);
    expect(appendDigit(99_999, 9)).toBe(99_999);
    expect(MAX_NAIRA_ENTRY).toBe(100_000);
  });
  it("deletes the last digit, down to zero", () => {
    expect(deleteDigit(15_000)).toBe(1_500);
    expect(deleteDigit(7)).toBe(0);
    expect(deleteDigit(0)).toBe(0);
  });
  it("always stays an integer", () => {
    for (let n = 0; n < 2000; n += 7) expect(Number.isInteger(deleteDigit(n))).toBe(true);
  });
});
