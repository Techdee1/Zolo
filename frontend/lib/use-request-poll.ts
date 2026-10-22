"use client";

import { useEffect, useState } from "react";
import { getRequest } from "@/lib/api/endpoints";
import { isApiError } from "@/lib/api/client";
import type { RequestOut } from "@/lib/api/types";

export const TERMINAL = ["SETTLED", "DECLINED", "EXPIRED", "FAILED"] as const;
export const isTerminal = (s: RequestOut["state"]) => (TERMINAL as readonly string[]).includes(s);

export type PollResult = {
  request: RequestOut | null;
  /** The last try failed to reach the server; the screen keeps showing what it knew. */
  offline: boolean;
  /** The server said this is not ours to see (401, 403, 404). */
  denied: "unauthenticated" | "not-found" | null;
};

/**
 * Polls GET /requests/{id} once a second until the request reaches a final state. SUBMITTED is NOT
 * final: the bank has not confirmed, so we keep asking. A dropped connection never changes what is
 * on screen (a screen must not flip to "failed" because the network blinked); it backs off to 3 s.
 * `once` asks a single time (for screens whose message does not depend on what happens next).
 */
export function useRequestPoll(id: string, { once = false }: { once?: boolean } = {}): PollResult {
  const [state, setState] = useState<PollResult>({ request: null, offline: false, denied: null });

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;

    const tick = async () => {
      let delay = 1000;
      try {
        const request = await getRequest(id, { signal: controller.signal });
        setState({ request, offline: false, denied: null });
        if (once || isTerminal(request.state)) return;
      } catch (e) {
        if (controller.signal.aborted) return;
        if (isApiError(e) && (e.status === 401 || e.status === 403)) {
          setState((s) => ({ ...s, denied: "unauthenticated" }));
          return;
        }
        if (isApiError(e) && e.status === 404) {
          setState((s) => ({ ...s, denied: "not-found" }));
          return;
        }
        setState((s) => ({ ...s, offline: true }));
        delay = 3000;
      }
      timer = setTimeout(() => void tick(), delay);
    };
    void tick();

    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [id, once]);

  return state;
}
