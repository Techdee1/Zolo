// A tiny stand-in for the Zolo API, used only by the proxy tests. It behaves like the real one
// where the proxy cares: an HttpOnly session cookie that must come back, RFC 9457 errors,
// a slow stream, and an echo of what it received.
import { createServer } from "node:http";
import { randomBytes } from "node:crypto";

const PORT = Number(process.env.E2E_API_PORT ?? 3101);
const sessions = new Set();

const problem = (res, status, code) => {
  res.writeHead(status, {
    "content-type": "application/problem+json",
    "cache-control": "no-store",
  });
  res.end(JSON.stringify({ type: "about:blank", title: code, status, code, detail: "" }));
};
const readBody = (req) =>
  new Promise((resolve) => {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => resolve(Buffer.concat(chunks)));
  });
const cookieOf = (req, name) =>
  (req.headers.cookie ?? "")
    .split(/;\s*/)
    .map((p) => p.split("="))
    .find(([k]) => k === name)?.[1];

createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://localhost:${PORT}`);

  if (url.pathname === "/healthz") {
    res.writeHead(200, { "content-type": "application/json" });
    return res.end('{"status":"ok"}');
  }

  if (req.method === "POST" && url.pathname === "/auth/mock-login") {
    const body = JSON.parse((await readBody(req)).toString() || "{}");
    if (body.otp !== "123456") return problem(res, 401, "UNAUTHENTICATED");
    const token = randomBytes(12).toString("hex");
    sessions.add(token);
    res.writeHead(200, {
      "content-type": "application/json",
      "set-cookie": `zolo_session=${token}; Max-Age=43200; Path=/; HttpOnly; SameSite=Lax`,
      "cache-control": "no-store",
    });
    return res.end(JSON.stringify({ role: "customer", display_name: "Amaka Obi" }));
  }

  if (req.method === "GET" && url.pathname === "/me/activity") {
    if (!sessions.has(cookieOf(req, "zolo_session"))) return problem(res, 401, "UNAUTHENTICATED");
    res.writeHead(200, { "content-type": "application/json", "cache-control": "no-store" });
    return res.end(JSON.stringify({ items: [] }));
  }

  if (url.pathname === "/echo") {
    const body = (await readBody(req)).toString();
    res.writeHead(200, { "content-type": "application/json", "cache-control": "no-store" });
    return res.end(
      JSON.stringify({
        method: req.method,
        url: req.url, // proves the /api prefix was removed
        host: req.headers.host,
        forwardedFor: req.headers["x-forwarded-for"] ?? null,
        forwardedHost: req.headers["x-forwarded-host"] ?? null,
        requestId: req.headers["x-request-id"] ?? null,
        hasCookie: Boolean(req.headers.cookie),
        bodyLength: body.length,
        bodyEcho: body.length < 200 ? body : undefined,
      }),
    );
  }

  if (url.pathname === "/stream") {
    // Five events, 250 ms apart: a client that sees the first one quickly is not being buffered.
    res.writeHead(200, {
      "content-type": "text/event-stream",
      "cache-control": "no-store",
      connection: "keep-alive",
    });
    res.flushHeaders();
    let n = 0;
    const timer = setInterval(() => {
      res.write(`data: ${n}\n\n`);
      if (++n === 5) {
        clearInterval(timer);
        res.end();
      }
    }, 250);
    req.on("close", () => clearInterval(timer));
    return;
  }

  const status = url.pathname.match(/^\/status\/(\d{3})$/);
  if (status) return problem(res, Number(status[1]), "SAMPLE_ERROR");

  problem(res, 404, "NOT_FOUND");
}).listen(PORT, () => console.log(`fake API on ${PORT}`));
