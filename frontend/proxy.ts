import { NextResponse, type NextRequest } from "next/server";

/**
 * Strict, nonce-based Content Security Policy, set on every page request.
 *
 * - Scripts: only this origin plus a fresh per-request nonce ('strict-dynamic' lets those scripts
 *   load their own chunks). No 'unsafe-inline' and no 'unsafe-eval' in production.
 * - connect-src / media-src: this origin and the Zolo API origin only (readback audio is served by
 *   the API).
 * - style-src-attr 'unsafe-inline': style ATTRIBUTES only (React and animation libraries set
 *   them); style elements still need the nonce. Scripts stay strict. This is a deliberate trade.
 *
 * The API origin comes from NEXT_PUBLIC_API_BASE_URL. Set CSP_UPGRADE_INSECURE=1 in real (https)
 * deployments so any stray http sub-resource is upgraded; leave it off for http://localhost runs.
 */
const apiOrigin = (() => {
  try {
    return new URL(process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").origin;
  } catch {
    return "";
  }
})();

export function buildCsp(nonce: string, opts: { dev: boolean; upgrade: boolean }): string {
  const directives = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${opts.dev ? " 'unsafe-eval'" : ""}`,
    `style-src 'self' 'nonce-${nonce}'`,
    "style-src-attr 'unsafe-inline'",
    "img-src 'self' blob: data:",
    "font-src 'self'",
    `connect-src 'self' ${apiOrigin}${opts.dev ? " ws:" : ""}`.trim(),
    `media-src 'self' blob: ${apiOrigin}`.trim(),
    "worker-src 'self'",
    "manifest-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ];
  if (opts.upgrade) directives.push("upgrade-insecure-requests");
  return directives.join("; ");
}

export function proxy(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const csp = buildCsp(nonce, {
    dev: process.env.NODE_ENV === "development",
    upgrade: process.env.CSP_UPGRADE_INSECURE === "1",
  });

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export const config = {
  matcher: [
    {
      // Pages only: skip static files, the favicon and prefetches, which need no CSP.
      source: "/((?!_next/static|_next/image|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
