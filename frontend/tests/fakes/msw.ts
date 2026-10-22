import { http, HttpResponse } from "msw";
import type { FakeBackend } from "./fake-backend";

/** Routes every `/api/*` request to the fake backend, for unit and component tests. */
export function fakeBackendHandlers(fake: FakeBackend) {
  return [
    http.all("*/api/*", async ({ request }) => {
      const url = new URL(request.url);
      const text = request.method === "GET" ? "" : await request.text();
      const res = fake.handle({
        method: request.method,
        path: url.pathname.replace(/^.*\/api/, ""),
        query: Object.fromEntries(url.searchParams),
        headers: Object.fromEntries(request.headers),
        body: text ? JSON.parse(text) : undefined,
      });
      return HttpResponse.json(res.body as never, { status: res.status, headers: res.headers });
    }),
  ];
}
