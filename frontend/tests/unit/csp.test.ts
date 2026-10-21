import { describe, expect, it } from "vitest";
import { buildCsp } from "@/proxy";

const directive = (csp: string, name: string) =>
  csp
    .split("; ")
    .find((d) => d.startsWith(`${name} `))
    ?.slice(name.length + 1);

describe("Content Security Policy", () => {
  const prod = buildCsp("NONCE123", { dev: false, upgrade: false });

  it("allows scripts only from this origin with the per-request nonce", () => {
    const scripts = directive(prod, "script-src") ?? "";
    expect(scripts).toContain("'self'");
    expect(scripts).toContain("'nonce-NONCE123'");
    expect(scripts).not.toContain("'unsafe-inline'");
    expect(scripts).not.toContain("'unsafe-eval'");
  });

  it("allows eval only in development, where React needs it", () => {
    expect(directive(buildCsp("n", { dev: true, upgrade: false }), "script-src")).toContain(
      "'unsafe-eval'",
    );
  });

  it("limits network and audio to this origin and the API", () => {
    expect(directive(prod, "connect-src")).toBe("'self' http://localhost:8000");
    expect(directive(prod, "media-src")).toContain("http://localhost:8000");
    expect(directive(prod, "default-src")).toBe("'self'");
  });

  it("blocks plugins, framing and base-tag tricks", () => {
    expect(directive(prod, "object-src")).toBe("'none'");
    expect(directive(prod, "frame-ancestors")).toBe("'none'");
    expect(directive(prod, "base-uri")).toBe("'self'");
    expect(directive(prod, "form-action")).toBe("'self'");
  });

  it("only allows inline style ATTRIBUTES, never inline style elements", () => {
    expect(directive(prod, "style-src")).toBe("'self' 'nonce-NONCE123'");
    expect(directive(prod, "style-src-attr")).toBe("'unsafe-inline'");
  });

  it("upgrades insecure requests only when asked", () => {
    expect(prod).not.toContain("upgrade-insecure-requests");
    expect(buildCsp("n", { dev: false, upgrade: true })).toContain("upgrade-insecure-requests");
  });
});
