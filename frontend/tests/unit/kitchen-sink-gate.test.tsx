import { describe, expect, it, vi } from "vitest";

// The gallery must not exist in a normal production build.
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
}));

describe("the /kitchen-sink page", () => {
  it("is a 404 unless its flag is on", async () => {
    vi.doMock("@/lib/env", () => ({ env: { featureKitchenSink: false } }));
    const { default: Page } = await import("@/app/kitchen-sink/page");
    expect(() => Page()).toThrow("NEXT_NOT_FOUND");
  });

  it("renders when the flag is on", async () => {
    vi.resetModules();
    vi.doMock("@/lib/env", () => ({ env: { featureKitchenSink: true } }));
    vi.doMock("@/app/kitchen-sink/KitchenSink", () => ({ KitchenSink: () => "gallery" }));
    const { default: Page } = await import("@/app/kitchen-sink/page");
    expect(() => Page()).not.toThrow();
  });
});
