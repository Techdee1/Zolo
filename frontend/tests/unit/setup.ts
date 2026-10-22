import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";
import { markNavigated } from "@/lib/initial-load";
import { router } from "./router";

vi.mock("next/navigation", () => ({ useRouter: () => router }));

beforeEach(() => {
  Object.values(router).forEach((fn) => fn.mockReset());
  markNavigated(); // screens are tested as client-side navigations: focus moves to the h1
});

afterEach(() => cleanup());

// Node's fetch needs absolute URLs; the app calls "/api/...". Resolve them against the page, as a browser does.
const nodeFetch = globalThis.fetch;
globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) =>
  nodeFetch(
    typeof input === "string" ? new URL(input, window.location.href) : input,
    init,
  )) as typeof fetch;
