// The Zolo API stand-in for end-to-end tests: the shared fake backend behind a real HTTP server
// (the production build proxies /api/* to it), plus a few controls under /__fake that the real
// API does not have (make the next approval end in SUBMITTED, let the bank confirm, and so on).
import { createServer } from "node:http";
import { createFakeBackend, type ApprovalOutcome } from "../fakes/fake-backend";

const PORT = Number(process.env.E2E_API_PORT ?? 3101);
const fake = createFakeBackend({ audioUrl: null });

const readBody = (req: import("node:http").IncomingMessage) =>
  new Promise<string>((resolve) => {
    const chunks: Buffer[] = [];
    req.on("data", (c: Buffer) => chunks.push(c));
    req.on("end", () => resolve(Buffer.concat(chunks).toString()));
  });

createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://localhost:${PORT}`);
  const raw = req.method === "GET" || req.method === "HEAD" ? "" : await readBody(req);

  // ── Endpoints for the proxy tests: not part of the real API ──
  if (url.pathname === "/echo") {
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
        bodyLength: raw.length,
        bodyEcho: raw.length < 200 ? raw : undefined,
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
  const status = /^\/status\/(\d{3})$/.exec(url.pathname);
  if (status) {
    res.writeHead(Number(status[1]), {
      "content-type": "application/problem+json",
      "cache-control": "no-store",
    });
    return res.end(
      JSON.stringify({
        type: "about:blank",
        title: "SAMPLE_ERROR",
        status: Number(status[1]),
        code: "SAMPLE_ERROR",
        detail: "",
      }),
    );
  }

  // ── Controls that only exist in tests ──
  if (url.pathname.startsWith("/__fake/")) {
    const [, , action, arg] = url.pathname.split("/");
    if (action === "reset") fake.reset();
    if (action === "outcome") fake.setOutcome(arg as ApprovalOutcome);
    if (action === "settle") fake.settle(arg ?? "");
    if (action === "passkey") fake.addPasskey();
    if (action === "phone") fake.setPhone(arg !== "off");
    if (action === "native") fake.setNativeClips(arg === "on");
    if (action === "audio") fake.setAudio(arg === "none" ? null : "/voice/audio/test.mp3");
    res.writeHead(204);
    return res.end();
  }

  // ── The audio file for readbacks: a short silent WAV served as the pre-rendered clip ──
  if (url.pathname === "/voice/audio/test.mp3") {
    const rate = 8000;
    const samples = rate / 2; // half a second of silence
    const buf = Buffer.alloc(44 + samples);
    buf.write("RIFF", 0);
    buf.writeUInt32LE(36 + samples, 4);
    buf.write("WAVEfmt ", 8);
    buf.writeUInt32LE(16, 16);
    buf.writeUInt16LE(1, 20);
    buf.writeUInt16LE(1, 22);
    buf.writeUInt32LE(rate, 24);
    buf.writeUInt32LE(rate, 28);
    buf.writeUInt16LE(1, 32);
    buf.writeUInt16LE(8, 34);
    buf.write("data", 36);
    buf.writeUInt32LE(samples, 40);
    buf.fill(128, 44);
    res.writeHead(200, { "content-type": "audio/wav", "content-length": buf.length });
    return res.end(buf);
  }

  let body: unknown;
  try {
    body = raw ? JSON.parse(raw) : undefined;
  } catch {
    body = undefined;
  }
  const out = fake.handle({
    method: req.method ?? "GET",
    path: url.pathname,
    query: Object.fromEntries(url.searchParams),
    headers: Object.fromEntries(
      Object.entries(req.headers).map(([k, v]) => [k, Array.isArray(v) ? v.join(", ") : v]),
    ),
    body,
  });
  res.writeHead(out.status, out.headers);
  res.end(JSON.stringify(out.body));
}).listen(PORT, () => console.log(`fake zolo api on ${PORT}`));
