import { vi } from "vitest";

/** One fake Next router for every screen test. */
export const router = {
  push: vi.fn(),
  replace: vi.fn(),
  back: vi.fn(),
  refresh: vi.fn(),
  prefetch: vi.fn(),
  forward: vi.fn(),
};
