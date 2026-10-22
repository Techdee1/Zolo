"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { takeInitialLoad } from "@/lib/initial-load";

/**
 * The screen's one h1. When a screen opens, focus moves to it and the tab title changes, so a
 * screen-reader user hears where they are and a keyboard user starts at the top.
 *
 * `manualFocus` is for the review screen only: there, Zolo's voice speaks first and focus moves
 * (later) to the readback, so the screen reader and the voice never talk at once.
 */
export function PageHeading({
  children,
  title,
  manualFocus = false,
  className,
}: {
  children: ReactNode;
  /** Plain text for the tab title; defaults to the heading's own text. */
  title: string;
  manualFocus?: boolean;
  className?: string;
}) {
  const ref = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    document.title = `${title} · Zolo`;
  }, [title]);

  useEffect(() => {
    const firstLoad = takeInitialLoad();
    if (!manualFocus && !firstLoad) ref.current?.focus({ preventScroll: true });
    // Once per screen, not on every change of the heading's words.
  }, [manualFocus]);

  return (
    <h1 ref={ref} tabIndex={-1} className={cn("type-title outline-none", className)}>
      {children}
    </h1>
  );
}
