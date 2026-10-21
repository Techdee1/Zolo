import { afterAll, afterEach, beforeAll } from "vitest";
import { setupServer } from "msw/node";
import { createFakeBackend, type FakeOptions } from "../fakes/fake-backend";
import { fakeBackendHandlers } from "../fakes/msw";

/**
 * Starts the shared fake backend behind MSW for one test file. `fake.actAs("customer")` signs in
 * without a cookie (jsdom has no cookie jar for Node's fetch); `fake.reset()` runs after each test.
 */
export function installFakeBackend(options?: FakeOptions) {
  const fake = createFakeBackend(options);
  const server = setupServer(...fakeBackendHandlers(fake));
  beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
  afterEach(() => {
    server.resetHandlers();
    fake.reset();
  });
  afterAll(() => server.close());
  return fake;
}
