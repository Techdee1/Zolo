import type { NextConfig } from "next";

/**
 * Deliberately NOT enabled: `cacheComponents` and `partialPrefetching`.
 *
 * With Cache Components, Next keeps previously visited routes alive in a hidden state and restores
 * their component state on back-navigation. For a payment app that is the wrong default: a back
 * button must never bring back an old review screen with an old amount. Money screens always
 * refetch and revalidate. (Also, nonce-based CSP needs dynamic rendering anyway.)
 */
const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Photos are served as AVIF or WebP when the browser can read them, from our own origin.
  images: { formats: ["image/avif", "image/webp"] },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
          {
            // Camera (scan a QR) and microphone (voice) only for this origin, and only on request.
            // WebAuthn is allowed for this origin so passkeys work; everything else is off.
            key: "Permissions-Policy",
            value:
              "camera=(self), microphone=(self), geolocation=(), payment=(), " +
              "publickey-credentials-get=(self), publickey-credentials-create=(self)",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
