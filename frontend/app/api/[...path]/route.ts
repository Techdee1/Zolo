import type { NextRequest } from "next/server";

/**
 * The /api proxy: the browser only ever talks to this origin, and this handler forwards to the Zolo
 * API (BACKEND_URL, server-side, read at runtime). Why a handler and not a Next rewrite: a rewrite
 * cannot guarantee two things we need.
 *
 *  1. Responses are streamed, never buffered, so server-sent events work later. Next gzips
 *     responses, and compression buffers a stream; marking API responses `no-transform` stops that,
 *     and a rewrite cannot override the backend's own Cache-Control to add it.
 *  2. A client that disconnects aborts the upstream request too.
 *
 * Cookies pass through both ways untouched (Set-Cookie is forwarded one by one), so the session is
 * a first-party cookie on this origin.
 */
export const dynamic = "force-dynamic";

const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  "host",
  "content-length", // recomputed by fetch from the body we pass
]);

function backendBase(): string {
  return (process.env.BACKEND_URL ?? "http://localhost:8000").replace(/\/+$/, "");
}

type Ctx = { params: Promise<{ path: string[] }> };

async function proxy(req: NextRequest, ctx: Ctx): Promise<Response> {
  const { path } = await ctx.params;
  // Refuse path tricks: "." / ".." segments, or anything that is not a plain path piece.
  if (path.some((seg) => seg === "." || seg === ".." || seg === "" || /[\\/]/.test(seg))) {
    return Response.json({ code: "NOT_FOUND", status: 404, title: "Not found" }, { status: 404 });
  }
  const target = `${backendBase()}/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;

  const headers = new Headers();
  req.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) headers.set(key, value);
  });
  headers.set("accept-encoding", "identity"); // bytes pass through unchanged
  headers.set("x-forwarded-host", req.headers.get("host") ?? req.nextUrl.host);
  headers.set("x-forwarded-proto", req.nextUrl.protocol.replace(":", ""));

  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: req.method,
      headers,
      body: hasBody ? req.body : undefined,
      // @ts-expect-error `duplex` is required to stream a request body but is missing from the DOM types
      duplex: hasBody ? "half" : undefined,
      redirect: "manual", // the API never redirects; pass anything odd straight back
      cache: "no-store",
      signal: req.signal,
    });
  } catch (error) {
    if (req.signal.aborted) return new Response(null, { status: 499 });
    // The API is unreachable. Say so plainly, and never echo the address or the error text.
    console.error("api proxy: upstream unreachable", error instanceof Error ? error.name : "error");
    return Response.json(
      {
        type: "https://zolo.app/problems/internal-error",
        title: "The Zolo service is not reachable",
        status: 502,
        code: "INTERNAL_ERROR",
        detail: "",
      },
      { status: 502, headers: { "content-type": "application/problem+json" } },
    );
  }

  const out = new Headers();
  upstream.headers.forEach((value, key) => {
    const k = key.toLowerCase();
    if (!HOP_BY_HOP.has(k) && k !== "set-cookie" && k !== "content-encoding") out.set(key, value);
  });
  for (const cookie of upstream.headers.getSetCookie()) out.append("set-cookie", cookie);
  // Keep Next's compression away from API responses (it would buffer a stream).
  const cc = out.get("cache-control") ?? "no-store";
  if (!/no-transform/i.test(cc)) out.set("cache-control", `${cc}, no-transform`);

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: out,
  });
}

export {
  proxy as GET,
  proxy as POST,
  proxy as PUT,
  proxy as PATCH,
  proxy as DELETE,
  proxy as OPTIONS,
};
