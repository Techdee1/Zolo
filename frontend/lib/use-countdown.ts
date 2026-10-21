"use client";

import { useEffect, useState } from "react";

/** Whole seconds until `expiresAtMs`, rounded UP so "0" means it is really over. */
export function secondsLeft(expiresAtMs: number, nowMs: number): number {
  return Math.max(0, Math.ceil((expiresAtMs - nowMs) / 1000));
}

/**
 * Seconds remaining, re-read four times a second so the display flips right on the boundary.
 * `now` is injectable (tests, and later a server-clock offset so a phone with the wrong time
 * does not show a wrong countdown). Re-renders happen only when the second changes.
 */
export function useCountdown(expiresAtMs: number, now: () => number = Date.now): number {
  const [remaining, setRemaining] = useState(() => secondsLeft(expiresAtMs, now()));
  useEffect(() => {
    const tick = () => setRemaining(secondsLeft(expiresAtMs, now()));
    tick();
    const id = window.setInterval(tick, 250);
    return () => window.clearInterval(id);
  }, [expiresAtMs, now]);
  return remaining;
}
