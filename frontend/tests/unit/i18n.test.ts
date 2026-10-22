import { describe, expect, it } from "vitest";
import en from "@/messages/en.json";
import { fill, lookup, t } from "@/lib/i18n";
import { readbackFor } from "@/lib/readback-lang";
import { safeNext } from "@/lib/session-hint";

describe("messages", () => {
  it("fill replaces placeholders and refuses to show a half-filled sentence", () => {
    expect(fill("Paid {amount} to {payee}", { amount: "₦1", payee: "B" })).toBe("Paid ₦1 to B");
    expect(() => fill("Paid {amount}", {})).toThrow(/Missing value "amount"/);
  });
  it("an unknown key throws instead of rendering nothing", () => {
    expect(() => lookup(en, "nope.nothing")).toThrow(/Missing message/);
  });
  it("no message asks for a PIN, a card number or an OTP", () => {
    const all = JSON.stringify(en).toLowerCase();
    expect(all).not.toMatch(/enter your (pin|card|otp)|card number\b(?!\.)/);
    expect(t("passkey.never")).toMatch(/never asks for your PIN or your card number/);
  });
  it("the PRD's own sentences are used word for word", () => {
    expect(t("result.paid", { amount: "₦15,000", payee: "Bisi Ventures" })).toBe(
      "Paid. You sent ₦15,000 to Bisi Ventures.",
    );
    expect(t("result.changed")).toBe("This payment changed after you heard it. Nothing was sent.");
    expect(t("agent.waitForPaid")).toBe("Give cash only after you see Paid.");
    expect(t("result.processing")).toBe("Processing. Don't hand over goods yet.");
  });
});

describe("readback language", () => {
  it("speaks English or Pidgin, and never a language the backend would refuse", () => {
    expect(readbackFor("en")).toEqual({ lang: "en", englishNote: false });
    expect(readbackFor("pcm")).toEqual({ lang: "pcm", englishNote: false });
    for (const l of ["yo", "ha", "ig"] as const)
      expect(readbackFor(l)).toEqual({ lang: "en", englishNote: true });
  });
});

describe("safeNext", () => {
  it("only follows paths on this site", () => {
    expect(safeNext("/requests/abc")).toBe("/requests/abc");
    for (const bad of [
      "//evil.com",
      "https://evil.com",
      "javascript:alert(1)",
      "/\\evil",
      undefined,
    ]) {
      expect(safeNext(bad)).toBe("/");
    }
  });
});
