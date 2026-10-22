import { LiveRegionProvider } from "@/components/ui/LiveRegion";

/**
 * The app screens (everything except the landing page) sit in the phone-sized frame, with the one
 * shared live region for announcements. The landing page is a full-width page of its own with no
 * client components, so neither lives in the root layout: it ships as little JavaScript as possible.
 */
export default function AppLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <LiveRegionProvider>
      <div className="app-frame">{children}</div>
    </LiveRegionProvider>
  );
}
