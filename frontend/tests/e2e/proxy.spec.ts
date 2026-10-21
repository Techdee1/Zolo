import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "@playwright/test";

// These go through the real production server and its /api proxy to a fake backend
// (tests/e2e/fake-api.ts). They protect decision 2: one origin for the browser.

const LOGIN = { phone: "+2348011111111", otp: "123456" };

test("the session cookie round-trips through the proxy, first-party and HttpOnly", async ({
  page,
  context,
  baseURL,
}) => {
  await page.goto("/");

  const login = await page.evaluate(async (body) => {
    const r = await fetch("/api/auth/mock-login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    return { status: r.status, json: await r.json() };
  }, LOGIN);
  expect(login.status).toBe(200);
  expect(login.json.display_name).toBe("Amaka Obi");

  // The cookie is stored for OUR host (first-party), HttpOnly, SameSite=Lax, and scripts cannot read it.
  const cookies = await context.cookies();
  const session = cookies.find((c) => c.name === "zolo_session");
  expect(session, "the backend's Set-Cookie must pass through the proxy").toBeTruthy();
  expect(session?.httpOnly).toBe(true);
  expect(session?.sameSite).toBe("Lax");
  expect(session?.domain).toBe(new URL(baseURL ?? "").hostname);
  expect(await page.evaluate(() => document.cookie)).not.toContain("zolo_session");

  // ...and the browser sends it back, through the proxy, on the next call.
  const next = await page.evaluate(async () => (await fetch("/api/me/activity")).status);
  expect(next).toBe(200);
});

test("without the cookie the backend says 401, and the error comes through intact", async ({
  page,
}) => {
  await page.goto("/");
  const res = await page.evaluate(async () => {
    const r = await fetch("/api/me/activity");
    return { status: r.status, type: r.headers.get("content-type"), body: await r.json() };
  });
  expect(res.status).toBe(401);
  expect(res.type).toContain("application/problem+json");
  expect(res.body).toMatchObject({ status: 401, code: "UNAUTHENTICATED" });
});

test("one person's cookie does not appear in another browser context", async ({ browser }) => {
  const a = await browser.newContext();
  const b = await browser.newContext();
  const pa = await a.newPage();
  const pb = await b.newPage();
  await pa.goto("/");
  await pb.goto("/");
  await pa.evaluate(
    async (body) =>
      fetch("/api/auth/mock-login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      }),
    LOGIN,
  );
  expect(await pa.evaluate(async () => (await fetch("/api/me/activity")).status)).toBe(200);
  expect(await pb.evaluate(async () => (await fetch("/api/me/activity")).status)).toBe(401);
  await a.close();
  await b.close();
});

test("a wrong code is refused and sets no cookie", async ({ request }) => {
  const res = await request.post("/api/auth/mock-login", { data: { ...LOGIN, otp: "000000" } });
  expect(res.status()).toBe(401);
  expect(res.headers()["set-cookie"]).toBeUndefined();
});

test("Set-Cookie attributes survive the proxy unchanged", async ({ request }) => {
  const res = await request.post("/api/auth/mock-login", { data: LOGIN });
  const header = res.headers()["set-cookie"] ?? "";
  expect(header).toMatch(/^zolo_session=[0-9a-f]+;/);
  for (const attr of ["HttpOnly", "SameSite=Lax", "Path=/", "Max-Age=43200"]) {
    expect(header).toContain(attr);
  }
  expect(header).not.toMatch(/Domain=/i); // host-only: it belongs to this origin and nothing else
});

test("the backend sees the path WITHOUT /api, the real client address and the body", async ({
  request,
}) => {
  const get = await (
    await request.get("/api/echo", { headers: { "x-request-id": "trace-12345" } })
  ).json();
  expect(get.url).toBe("/echo"); // the proxy strips /api
  expect(get.requestId).toBe("trace-12345");
  expect(get.forwardedFor, "rate limits need the client address, not the proxy's").toBeTruthy();

  const big = "x".repeat(150_000);
  const post = await (await request.post("/api/echo", { data: big })).json();
  expect(post.method).toBe("POST");
  expect(post.bodyLength).toBe(big.length);
});

test("responses are streamed, not buffered (so SSE can work later)", async ({ baseURL }) => {
  // Ask for compression too: a compressing proxy is the usual thing that buffers a stream.
  const started = Date.now();
  const res = await fetch(`${baseURL}/api/stream`, { headers: { "accept-encoding": "gzip, br" } });
  expect(res.headers.get("content-type")).toContain("text/event-stream");
  const reader = res.body!.getReader();
  const arrivals: number[] = [];
  for (;;) {
    const { done } = await reader.read();
    if (done) break;
    arrivals.push(Date.now() - started);
  }
  expect(arrivals.length).toBeGreaterThanOrEqual(3); // arrived in pieces
  expect(arrivals[0]!).toBeLessThan(600); // the first event did not wait for the last (~1250 ms)
  expect(arrivals.at(-1)! - arrivals[0]!).toBeGreaterThan(600); // and they were spread out in time
});

test("the CSP lets the page call the API through the proxy and nothing else", async ({ page }) => {
  const violations: string[] = [];
  page.on("console", (m) => {
    if (/content security policy/i.test(m.text())) violations.push(m.text());
  });
  await page.goto("/");
  const ok = await page.evaluate(async () => (await fetch("/api/status/404")).status);
  expect(ok).toBe(404);
  const blocked = await page.evaluate(async () => {
    try {
      await fetch("http://localhost:3101/status/404", { mode: "no-cors" });
      return "allowed";
    } catch {
      return "blocked";
    }
  });
  expect(blocked, "a direct call to the backend must be refused by connect-src 'self'").toBe(
    "blocked",
  );
  expect(violations.some((v) => v.includes("connect-src"))).toBe(true);
});

test("the backend address never reaches the browser bundle", async () => {
  const walk = (dir: string): string[] =>
    readdirSync(dir).flatMap((f) => {
      const p = join(dir, f);
      return statSync(p).isDirectory() ? walk(p) : [p];
    });
  const files = walk(join(process.cwd(), ".next", "static")).filter((f) =>
    /\.(js|css|html|json)$/.test(f),
  );
  expect(files.length).toBeGreaterThan(0);
  for (const file of files) {
    const text = readFileSync(file, "utf8");
    expect(text, file).not.toContain("localhost:3101");
    expect(text, file).not.toContain("BACKEND_URL");
  }
});

test("path tricks cannot escape the proxy", async ({ request }) => {
  // Dot-dot and encoded slashes are refused outright.
  for (const path of ["/api/%2e%2e/healthz", "/api/a/%2e%2e/b", "/api/a%2fb", "/api/a%5cb"]) {
    const res = await request.get(path);
    expect([404, 400], path).toContain(res.status());
    expect(await res.text(), path).not.toContain('"status":"ok"'); // never reached the backend's /healthz
  }
  // A lone encoded dot is normalised away by the server before it gets here, so it is simply
  // /api/echo. The invariant that matters: the backend only ever sees a path it would serve anyway.
  const lone = await request.get("/api/%2e/echo");
  if (lone.status() === 200) expect((await lone.json()).url).toBe("/echo");
});
