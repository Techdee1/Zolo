"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

/**
 * ONE shared polite live region for status changes (Paid, Declined, Expired, waiting), and one
 * assertive region for errors. Everything announces through these two, so announcements are
 * ordered and never compete. The regions are always in the DOM (a region added at the moment of
 * the message is often not announced) and visually hidden.
 *
 * Announcing the same sentence twice in a row still speaks it twice: the region is cleared first.
 */
type Announce = (message: string, options?: { assertive?: boolean }) => void;

const LiveRegionContext = createContext<Announce | null>(null);

export function LiveRegionProvider({ children }: { children: React.ReactNode }) {
  const [polite, setPolite] = useState("");
  const [assertive, setAssertive] = useState("");
  const timers = useRef<number[]>([]);

  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach((t) => window.clearTimeout(t));
  }, []);

  const announce = useCallback<Announce>((message, options) => {
    const set = options?.assertive ? setAssertive : setPolite;
    set(""); // clear first, so an identical message is announced again
    timers.current.push(window.setTimeout(() => set(message), 50));
  }, []);

  const value = useMemo(() => announce, [announce]);

  return (
    <LiveRegionContext.Provider value={value}>
      {children}
      <div className="sr-only">
        <div role="status" aria-live="polite" aria-atomic="true" data-live-region="polite">
          {polite}
        </div>
        <div role="alert" aria-live="assertive" aria-atomic="true" data-live-region="assertive">
          {assertive}
        </div>
      </div>
    </LiveRegionContext.Provider>
  );
}

/** `announce("Paid. You sent ₦15,000 to Bisi Ventures.")`, or `{ assertive: true }` for errors. */
export function useAnnounce(): Announce {
  const announce = useContext(LiveRegionContext);
  if (!announce) throw new Error("useAnnounce must be used inside <LiveRegionProvider>");
  return announce;
}
