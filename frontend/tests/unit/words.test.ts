import { describe, expect, it } from "vitest";
import fixtures from "./fixtures/amount-words.json";
import { amountSpoken, intToWords, nairaWords } from "@/lib/format/words";

describe("amount words agree with the BACKEND's own number-to-words", () => {
  it(`all ${fixtures.cases.length} amounts the backend produced come out word for word`, () => {
    const wrong = fixtures.cases
      .filter((c) => nairaWords(c.kobo) !== c.words)
      .map((c) => `${c.kobo} kobo: got "${nairaWords(c.kobo)}", backend says "${c.words}"`);
    expect(wrong).toEqual([]);
  });

  it("covers the awkward places: teens, tens, hundreds, thousands and millions", () => {
    const kobo = new Set(fixtures.cases.map((c) => c.kobo));
    for (const naira of [0, 13, 15, 30, 50, 100, 1000, 15000, 51000, 1000000, 999999999]) {
      expect(kobo.has(naira * 100), `${naira} is in the fixtures`).toBe(true);
    }
  });
});

describe("spoken amounts", () => {
  it("fifteen thousand naira", () =>
    expect(amountSpoken(1_500_000)).toBe("fifteen thousand naira"));
  it("fifteen and fifty are different words, which is the whole point", () => {
    expect(amountSpoken(1_500_000)).not.toBe(amountSpoken(5_000_000));
    expect(amountSpoken(5_000_000)).toBe("fifty thousand naira");
  });
  it("says one naira, not one nairas", () => expect(amountSpoken(100)).toBe("one naira"));
  it("adds kobo when there are some", () => {
    expect(amountSpoken(1_500_050)).toBe("fifteen thousand naira and fifty kobo");
    expect(amountSpoken(1)).toBe("zero naira and one kobo");
  });
  it("zero is zero naira", () => expect(amountSpoken(0)).toBe("zero naira"));
  it("refuses what it cannot say rather than guessing", () => {
    expect(() => intToWords(-1n)).toThrow(RangeError);
    expect(() => intToWords(1_000_000_000_000n)).toThrow(RangeError);
  });
});
