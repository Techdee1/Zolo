import { describe, expect, it } from "vitest";
import { cn } from "@/lib/cn";

describe("cn", () => {
  it("joins class names and skips anything falsy", () => {
    expect(cn("a", false, undefined, null, "b", 0 && "x")).toBe("a b");
  });
  it("supports conditional objects", () => {
    expect(cn("base", { active: true, hidden: false })).toBe("base active");
  });
});
