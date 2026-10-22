import type { Metadata, Viewport } from "next";
import { connection } from "next/server";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Zolo", template: "%s · Zolo" },
  description: "Approve a payment only when you have heard it. Zolo, for Zenith Bank.",
  applicationName: "Zolo",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  colorScheme: "light dark",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#F5F5F7" },
    { media: "(prefers-color-scheme: dark)", color: "#111113" },
  ],
  // No maximumScale / userScalable: people must be able to pinch-zoom (WCAG 1.4.4).
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  // Render every page per request. The strict, nonce-based CSP (proxy.ts) needs a fresh nonce on
  // each response, and a statically prerendered page has no nonce on its scripts, so the browser
  // would block them all and the app would never become interactive.
  await connection();
  return (
    <html lang="en">
      <body>
        <a href="#main" className="skip-link">
          Skip to main content
        </a>
        {children}
      </body>
    </html>
  );
}
