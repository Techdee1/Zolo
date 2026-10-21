import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => cleanup());

// Node's fetch needs absolute URLs; the app calls "/api/...". Resolve them against the page, as a browser does.
const nodeFetch = globalThis.fetch;
globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) =>
  nodeFetch(
    typeof input === "string" ? new URL(input, window.location.href) : input,
    init,
  )) as typeof fetch;
