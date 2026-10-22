import { describe, expect, it } from "vitest";
import { API_BASE, parseEnv } from "@/lib/env";

describe("parseEnv", () => {
  it("has safe defaults: every flag off", () => {
    expect(parseEnv({})).toEqual({
      featureDemo: false,
      featureCardGuard: false,
      featureKitchenSink: false,
      useMocks: false,
      demoVideoUrl: undefined,
      repoUrl: undefined,
      teamName: "Overclock",
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

  it("landing links are optional and https only", () => {
    expect(parseEnv({}).demoVideoUrl).toBeUndefined();
    expect(parseEnv({ NEXT_PUBLIC_REPO_URL: "https://github.com/x/y" }).repoUrl).toBe(
      "https://github.com/x/y",
    );
    for (const bad of ["javascript:alert(1)", "http://example.com", "not a url", "//evil.com"]) {
      expect(() => parseEnv({ NEXT_PUBLIC_DEMO_VIDEO_URL: bad }), bad).toThrow();
    }
  });

  it("treats an empty value as unset", () => {
    expect(parseEnv({ NEXT_PUBLIC_FEATURE_DEMO: "" }).featureDemo).toBe(false);
  });
});
