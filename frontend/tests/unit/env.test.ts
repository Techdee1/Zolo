import { describe, expect, it } from "vitest";
import { parseEnv } from "@/lib/env";

describe("parseEnv", () => {
  it("has safe defaults: local API, every flag off", () => {
    expect(parseEnv({})).toEqual({
      apiBaseUrl: "http://localhost:8000",
      featureDemo: false,
      featureCardGuard: false,
      useMocks: false,
    });
  });

  it("reads the API address and strips trailing slashes", () => {
    expect(parseEnv({ NEXT_PUBLIC_API_BASE_URL: "https://api.zolo.example///" }).apiBaseUrl).toBe(
      "https://api.zolo.example",
    );
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

  it("refuses an API address that is not a URL, instead of guessing", () => {
    expect(() => parseEnv({ NEXT_PUBLIC_API_BASE_URL: "not a url" })).toThrow();
  });

  it("treats an empty value as unset", () => {
    expect(
      parseEnv({ NEXT_PUBLIC_API_BASE_URL: "", NEXT_PUBLIC_FEATURE_DEMO: "" }).apiBaseUrl,
    ).toBe("http://localhost:8000");
  });
});
