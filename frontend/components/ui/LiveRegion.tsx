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
const HoldContext = createContext<(() => () => void) | null>(null);

export function LiveRegionProvider({ children }: { children: React.ReactNode }) {
  const [polite, setPolite] = useState("");
  const [assertive, setAssertive] = useState("");
  const timers = useRef<number[]>([]);

  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach((t) => window.clearTimeout(t));
  }, []);

  // While Zolo's own voice is speaking, nothing is announced: the screen reader would talk over
  // it. Messages wait here and are spoken, in order, when the last hold is released.
  const holds = useRef(0);
  const queue = useRef<Array<[string, boolean]>>([]);

  const speak = useCallback((message: string, assertiveRegion: boolean) => {
    const set = assertiveRegion ? setAssertive : setPolite;
    set(""); // clear first, so an identical message is announced again
    timers.current.push(window.setTimeout(() => set(message), 50));
  }, []);

  const announce = useCallback<Announce>(
    (message, options) => {
      const assertiveRegion = Boolean(options?.assertive);
      if (holds.current > 0) queue.current.push([message, assertiveRegion]);
      else speak(message, assertiveRegion);
    },
    [speak],
  );

  const hold = useCallback(() => {
    holds.current += 1;
    let released = false;
    return () => {
      if (released) return;
      released = true;
      holds.current -= 1;
      if (holds.current > 0) return;
      // Only the latest message per region matters: older ones are stale by now.
      const latest = new Map<boolean, string>();
      for (const [message, assertiveRegion] of queue.current) latest.set(assertiveRegion, message);
      queue.current = [];
      for (const [assertiveRegion, message] of latest) speak(message, assertiveRegion);
    };
  }, [speak]);

  const value = useMemo(() => announce, [announce]);

  return (
    <LiveRegionContext.Provider value={value}>
      <HoldContext.Provider value={hold}>
        {children}
        <div className="sr-only">
          <div role="status" aria-live="polite" aria-atomic="true" data-live-region="polite">
            {polite}
          </div>
          <div role="alert" aria-live="assertive" aria-atomic="true" data-live-region="assertive">
            {assertive}
          </div>
        </div>
      </HoldContext.Provider>
    </LiveRegionContext.Provider>
  );
}

/** `announce("Paid. You sent ₦15,000 to Bisi Ventures.")`, or `{ assertive: true }` for errors. */
export function useAnnounce(): Announce {
  const announce = useContext(LiveRegionContext);
  if (!announce) throw new Error("useAnnounce must be used inside <LiveRegionProvider>");
  return announce;
}

/**
 * Pause every announcement while Zolo's voice plays. `const release = hold()` when audio starts,
 * `release()` when it ends (or fails). Safe to call release twice.
 */
export function useHoldAnnouncements(): () => () => void {
  const hold = useContext(HoldContext);
  if (!hold) throw new Error("useHoldAnnouncements must be used inside <LiveRegionProvider>");
  return hold;
}
