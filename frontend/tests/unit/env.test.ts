import { describe, expect, it } from "vitest";
import { API_BASE, parseEnv } from "@/lib/env";

describe("parseEnv", () => {
  it("has safe defaults: every flag off", () => {
    expect(parseEnv({})).toEqual({
      featureDemo: false,
      featureCardGuard: false,
      featureKitchenSink: false,
      useMocks: false,
    });
  });

  it("the API is a path on our own origin, never another host", () => {
    expect(API_BASE).toBe("/api");
    expect(API_BASE.startsWith("/")).toBe(true);
    expect(API_BASE).not.toMatch(/^[a-z]+:/i);
  });

  it("turns flags on only for the exact word 'true'", () => {
    const on = parseEnv({ NEXT_PUBLIC_FEATURE_DEMO: "true", NEXT_PUBLIC_USE_MOCKS: "true" });
    expect(on.featureDemo).toBe(true);
    expect(on.useMocks).toBe(true);
    expect(on.featureCardGuard).toBe(false);
    for (const wrong of ["1", "yes", "TRUE", "on"]) {
      expect(() => parseEnv({ NEXT_PUBLIC_FEATURE_DEMO: wrong })).toThrow();
    }
  });

  it("treats an empty value as unset", () => {
    expect(parseEnv({ NEXT_PUBLIC_FEATURE_DEMO: "" }).featureDemo).toBe(false);
  });
});
