"use client";

import { useEffect, useRef } from "react";
import { cn } from "@/lib/cn";
import { secondsLeft, useCountdown } from "@/lib/use-countdown";
import { useAnnounce } from "./LiveRegion";

/**
 * Time left on a request. The visible digits tick every second but are NOT a live region, so a
 * screen reader is not chattering. It speaks (politely, through the shared region) only twice as
 * the time runs down, at 60 and at 15 seconds, and once when time is up.
 *
 * It announces when the time CROSSES those marks while you are looking. Opening a screen with 45
 * seconds left does not say "one minute left". Giving it a new `expiresAt` (a renewal) starts again.
 */
export type TimeLeftMessages = {
  label: string; // "Time left"
  oneMinute: string; // "One minute left."
  fifteenSeconds: string; // "Fifteen seconds left."
  expired: string; // "Time is up."
};

export type TimeLeftProps = {
  /** ISO timestamp from the API (`expires_at`) or epoch milliseconds. */
  expiresAt: string | number;
  messages: TimeLeftMessages;
  onExpire?: () => void;
  now?: () => number;
  className?: string;
};

const toMs = (v: string | number) => (typeof v === "number" ? v : Date.parse(v));

export function formatClock(totalSeconds: number): string {
  const minutes = (totalSeconds - (totalSeconds % 60)) / 60;
  return `${minutes}:${String(totalSeconds % 60).padStart(2, "0")}`;
}

export function TimeLeft({ expiresAt, messages, onExpire, now, className }: TimeLeftProps) {
  const announce = useAnnounce();
  const expiresMs = toMs(expiresAt);
  const remaining = useCountdown(expiresMs, now);
  const clock = now ?? Date.now;

  // What has already been said, or was already past when we started, for THIS expiry time.
  const said = useRef({ for: Number.NaN, minute: true, quarter: true, over: true });
  useEffect(() => {
    const start = secondsLeft(expiresMs, clock());
    said.current = { for: expiresMs, minute: start <= 60, quarter: start <= 15, over: false };
  }, [expiresMs, clock]);

  useEffect(() => {
    const s = said.current;
    if (s.for !== expiresMs) return; // the new expiry has not been registered yet
    const left = secondsLeft(expiresMs, clock()); // not the (possibly stale) state value
    if (left <= 0 && !s.over) {
      s.over = true;
      announce(messages.expired);
      onExpire?.();
    } else if (left > 0 && left <= 15 && !s.quarter) {
      s.quarter = s.minute = true;
      announce(messages.fifteenSeconds);
    } else if (left > 15 && left <= 60 && !s.minute) {
      s.minute = true;
      announce(messages.oneMinute);
    }
  }, [remaining, expiresMs, clock, announce, messages, onExpire]);

  return (
    <span
      className={cn(
        "type-secondary tabular-nums",
        remaining <= 60 && "font-semibold text-zolo-warning",
        className,
      )}
    >
      {messages.label} <time dateTime={`PT${remaining}S`}>{formatClock(remaining)}</time>
    </span>
  );
}
