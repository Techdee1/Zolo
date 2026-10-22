import type { Metadata, Viewport } from "next";
import { connection } from "next/server";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages, getTranslations } from "next-intl/server";
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
  const locale = await getLocale();
  const t = await getTranslations();
  // The landing page is English only and renders on the server, so its strings are not sent to the
  // browser with every screen.
  const messages = { ...((await getMessages()) as Record<string, unknown>) };
  delete messages.landing;
  return (
    <html lang={locale}>
      <body>
        <a href="#main" className="skip-link">
          {t("app.skip")}
        </a>
        <NextIntlClientProvider locale={locale} messages={messages as never}>
          {children}
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
