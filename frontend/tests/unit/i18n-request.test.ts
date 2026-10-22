import { describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  cookie: undefined as string | undefined,
  accept: null as string | null,
}));
vi.mock("next/headers", () => ({
  cookies: async () => ({ get: () => (state.cookie ? { value: state.cookie } : undefined) }),
  headers: async () => ({ get: () => state.accept }),
}));
vi.mock("next-intl/server", () => ({ getRequestConfig: (fn: unknown) => fn }));

const config = async () =>
  (
    (await import("@/i18n/request")).default as unknown as () => Promise<{
      locale: string;
      messages: Record<string, unknown>;
    }>
  )();

describe("which language the server renders", () => {
  it("the cookie wins over the browser", async () => {
    state.cookie = "ha";
    state.accept = "yo";
    expect((await config()).locale).toBe("ha");
  });
  it("without a cookie, the browser's language, then English", async () => {
    state.cookie = undefined;
    state.accept = "ig-NG,en;q=0.5";
    expect((await config()).locale).toBe("ig");
    state.accept = "fr";
    expect((await config()).locale).toBe("en");
  });
  it("ignores a cookie that is not one of the five", async () => {
    state.cookie = "klingon";
    state.accept = null;
    expect((await config()).locale).toBe("en");
  });
  it("serves a language file over English, so a missing string is English and never a raw key", async () => {
    state.cookie = "yo";
    const { messages } = await config();
    expect((messages.home as { title: string }).title).toBe("Kí ni o fẹ́ ṣe?");
    expect((messages.demo as { title: string }).title).toBe("Demo console"); // not translated: falls back
  });
});
