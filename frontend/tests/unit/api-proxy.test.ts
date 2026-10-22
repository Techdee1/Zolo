import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GET, POST } from "@/app/api/[...path]/route";

const ctx = (...path: string[]) => ({ params: Promise.resolve({ path }) });
const req = (path: string, init?: ConstructorParameters<typeof NextRequest>[1]) =>
  new NextRequest(`http://app.test${path}`, init);

let upstream: ReturnType<typeof vi.fn>;
beforeEach(() => {
  process.env.BACKEND_URL = "http://backend.test:8000/";
  upstream = vi.fn(async () => new Response("{}", { status: 200 }));
  vi.stubGlobal("fetch", upstream);
});
afterEach(() => {
  vi.unstubAllGlobals();
  delete process.env.BACKEND_URL;
});

const sent = () => upstream.mock.calls[0] as [string, RequestInit & { headers: Headers }];

describe("the /api proxy", () => {
  it("strips /api and forwards to BACKEND_URL, keeping the query string", async () => {
    await GET(req("/api/requests/abc/readback?lang=pcm"), ctx("requests", "abc", "readback"));
    expect(sent()[0]).toBe("http://backend.test:8000/requests/abc/readback?lang=pcm");
  });

  it.each([["."], [".."], [""], ["a/b"], ["a\\b"]])("refuses the path segment %j", async (seg) => {
    const res = await GET(req("/api/x"), ctx("requests", seg));
    expect(res.status).toBe(404);
    expect(upstream).not.toHaveBeenCalled();
  });

  it("forwards cookies and the method, and asks the backend for uncompressed bytes", async () => {
    await POST(
      req("/api/auth/mock-login", {
        method: "POST",
        headers: {
          cookie: "zolo_session=abc",
          "content-type": "application/json",
          "accept-encoding": "gzip, br",
        },
        body: "{}",
      }),
      ctx("auth", "mock-login"),
    );
    const [, init] = sent();
    expect(init.method).toBe("POST");
    expect(init.headers.get("cookie")).toBe("zolo_session=abc");
    expect(init.headers.get("accept-encoding")).toBe("identity");
    expect(init.headers.get("x-forwarded-host")).toBe("app.test");
    expect(init.headers.get("x-forwarded-proto")).toBe("http");
  });

  it("does not forward hop-by-hop headers", async () => {
    await GET(
      req("/api/x", {
        headers: {
          connection: "keep-alive",
          "keep-alive": "5",
          te: "trailers",
          upgrade: "websocket",
        },
      }),
      ctx("x"),
    );
    const h = sent()[1].headers;
    for (const name of ["connection", "keep-alive", "te", "upgrade"])
      expect(h.has(name)).toBe(false);
  });

  it("passes EVERY Set-Cookie back, not just the first", async () => {
    upstream.mockResolvedValueOnce(
      new Response("{}", {
        headers: [
          ["set-cookie", "zolo_session=a; HttpOnly; SameSite=Lax; Path=/"],
          ["set-cookie", "other=b; Path=/"],
        ],
      }),
    );
    const res = await GET(req("/api/x"), ctx("x"));
    expect(res.headers.getSetCookie()).toEqual([
      "zolo_session=a; HttpOnly; SameSite=Lax; Path=/",
      "other=b; Path=/",
    ]);
  });

  it("marks every API response no-transform so compression cannot buffer a stream", async () => {
    upstream.mockResolvedValueOnce(
      new Response("{}", { headers: { "cache-control": "no-store" } }),
    );
    expect((await GET(req("/api/x"), ctx("x"))).headers.get("cache-control")).toBe(
      "no-store, no-transform",
    );
    upstream.mockResolvedValueOnce(new Response("{}"));
    expect((await GET(req("/api/x"), ctx("x"))).headers.get("cache-control")).toBe(
      "no-store, no-transform",
    );
    upstream.mockResolvedValueOnce(
      new Response("{}", { headers: { "cache-control": "no-cache, no-transform" } }),
    );
    expect((await GET(req("/api/x"), ctx("x"))).headers.get("cache-control")).toBe(
      "no-cache, no-transform",
    );
  });

  it("passes the status and the problem+json body of an error straight through", async () => {
    upstream.mockResolvedValueOnce(
      new Response('{"code":"STATE_CONFLICT"}', {
        status: 409,
        headers: { "content-type": "application/problem+json" },
      }),
    );
    const res = await POST(
      req("/api/requests/1/approve", { method: "POST", body: "{}" }),
      ctx("requests", "1", "approve"),
    );
    expect(res.status).toBe(409);
    expect(res.headers.get("content-type")).toBe("application/problem+json");
    expect(await res.json()).toEqual({ code: "STATE_CONFLICT" });
  });

  it("does not follow redirects and never caches", async () => {
    await GET(req("/api/x"), ctx("x"));
    expect(sent()[1]).toMatchObject({ redirect: "manual", cache: "no-store" });
  });

  it("answers 502 in the API's own problem format when the backend is unreachable, leaking nothing", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    upstream.mockRejectedValueOnce(
      new TypeError("fetch failed: connect ECONNREFUSED 10.0.0.7:8000"),
    );
    const res = await GET(req("/api/me/activity"), ctx("me", "activity"));
    const text = await res.text();
    expect(res.status).toBe(502);
    expect(res.headers.get("content-type")).toBe("application/problem+json");
    expect(JSON.parse(text)).toMatchObject({ status: 502, code: "INTERNAL_ERROR" });
    expect(text).not.toMatch(/10\.0\.0\.7|ECONNREFUSED|backend\.test/);
  });

  it("logs only the error TYPE when the backend is unreachable, never its message", async () => {
    const log = vi.spyOn(console, "error").mockImplementation(() => {});
    upstream.mockRejectedValueOnce(new TypeError("secret detail 10.0.0.7"));
    await GET(req("/api/x"), ctx("x"));
    expect(JSON.stringify(log.mock.calls)).not.toContain("10.0.0.7");
  });
});
