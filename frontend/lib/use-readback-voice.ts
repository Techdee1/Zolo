"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useHoldAnnouncements } from "@/components/ui/LiveRegion";

/**
 * Zolo's voice and the screen reader must never talk at the same time.
 *
 * - "zolo" (default): play the readback audio, say nothing else meanwhile (announcements wait), and
 *   when the audio ends move focus to the readback, so the screen reader takes over after Zolo.
 * - "reader": no audio. Focus goes straight to the readback and the screen reader reads it.
 *
 * `heard` turns true when the audio has played to its end, or, with no audio (the reader mode, or no
 * clip was pre-rendered, or it failed), a short while after focus reaches the readback. Approve
 * waits for it. We cannot know what a screen reader has actually read; 2 s is the floor, and the
 * PRD's blind-tester check decides the real default.
 */
export type VoiceMode = "zolo" | "reader";
const STORAGE_KEY = "zolo.readback-mode";
const READER_DWELL_MS = 2000;

export function useVoiceMode(): [VoiceMode, (mode: VoiceMode) => void] {
  const [mode, setMode] = useState<VoiceMode>("zolo");
  useEffect(() => {
    const id = setTimeout(() => {
      try {
        if (window.localStorage.getItem(STORAGE_KEY) === "reader") setMode("reader");
      } catch {
        // storage blocked: default stays
      }
    }, 0);
    return () => clearTimeout(id);
  }, []);
  const choose = useCallback((next: VoiceMode) => {
    setMode(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // not remembered, still works
    }
  }, []);
  return [mode, choose];
}

export function useReadbackVoice({
  audioUrl,
  mode,
  ready,
  focusReadback,
}: {
  audioUrl: string | null | undefined;
  mode: VoiceMode;
  /** The readback has arrived and is on screen. */
  ready: boolean;
  focusReadback: () => void;
}) {
  const hold = useHoldAnnouncements();
  const audio = useRef<HTMLAudioElement | null>(null);
  const release = useRef<(() => void) | null>(null);
  const focus = useRef(focusReadback);
  const [heard, setHeard] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [blocked, setBlocked] = useState(false);

  useEffect(() => {
    focus.current = focusReadback;
  });

  const stopHold = useCallback(() => {
    release.current?.();
    release.current = null;
  }, []);

  const play = useCallback(() => {
    const el = audio.current;
    if (!el) return;
    el.currentTime = 0;
    if (!release.current) release.current = hold();
    setBlocked(false);
    el.play().then(
      () => setPlaying(true),
      () => {
        // The browser wants a tap before it will play sound. Nothing is lost: the button asks.
        stopHold();
        setPlaying(false);
        setBlocked(true);
      },
    );
  }, [hold, stopHold]);

  useEffect(() => {
    if (!ready) return;
    let dwell: ReturnType<typeof setTimeout> | undefined;
    const readerFlow = () => {
      focus.current();
      dwell = setTimeout(() => setHeard(true), READER_DWELL_MS);
    };

    if (mode === "zolo" && audioUrl) {
      const el = new Audio(audioUrl);
      audio.current = el;
      el.onended = () => {
        stopHold();
        setPlaying(false);
        setHeard(true);
        focus.current(); // Zolo has finished; now the screen reader may speak
      };
      el.onerror = () => {
        stopHold();
        setPlaying(false);
        readerFlow(); // the clip failed: fall back to reading it
      };
      play();
    } else {
      readerFlow();
    }

    return () => {
      clearTimeout(dwell);
      audio.current?.pause();
      audio.current = null;
      stopHold();
      setPlaying(false);
    };
  }, [ready, mode, audioUrl, play, stopHold]);

  return { heard, playing, blocked, hasAudio: mode === "zolo" && Boolean(audioUrl), play };
}
