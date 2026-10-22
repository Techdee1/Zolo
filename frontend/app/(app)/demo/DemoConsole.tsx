"use client";

import { useEffect, useState } from "react";
import { PageHeading } from "@/components/PageHeading";
import { Screen } from "@/components/Screen";
import { Badge, type BadgeVariant } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useAnnounce } from "@/components/ui/LiveRegion";
import { ApiError, isApiError } from "@/lib/api/client";
import { demoExpire, demoReplay, demoReset, demoTamper, demoTimeline } from "@/lib/api/endpoints";
import type { TimelineOut } from "@/lib/api/types";
import { formatNaira } from "@/lib/format/money";
import { useT } from "@/lib/i18n";
import { getLastRequestId } from "@/lib/session-hint";

const STATE_BADGE: Record<string, BadgeVariant> = {
  SETTLED: "paid",
  SUBMITTED: "processing",
  APPROVED: "processing",
  DECLINED: "declined",
  EXPIRED: "expired",
  FAILED: "failed",
};

const isResetResult = (r: unknown): r is { customers: number; agents: number } =>
  typeof r === "object" && r !== null && "customers" in r && "agents" in r;

const FIELD =
  "min-h-(--target-min) w-full rounded-zolo-control border border-zolo-separator bg-zolo-elevated px-4 type-body text-zolo-text";

/**
 * The stage operator's controls: break a payment in four ways and watch the state change on a
 * projector. Only what the backend has today: reset, tamper, replay, expire and the timeline. The
 * demo token is typed in by the operator and lives in this tab's memory: it is never in the bundle.
 */
export function DemoConsole() {
  const t = useT();
  const announce = useAnnounce();
  const [token, setToken] = useState("");
  const [requestId, setRequestId] = useState("");
  const [timeline, setTimeline] = useState<TimelineOut | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const id = setTimeout(() => setRequestId(getLastRequestId() ?? ""), 0);
    return () => clearTimeout(id);
  }, []);

  // The timeline refreshes every two seconds while there is a token and a request to look at.
  useEffect(() => {
    if (!token || !requestId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      try {
        setTimeline(await demoTimeline(token, requestId, { signal: controller.signal }));
      } catch {
        if (controller.signal.aborted) return;
        setTimeline(null);
      }
      timer = setTimeout(() => void tick(), 2000);
    };
    void tick();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [token, requestId]);

  async function run(action: string, needsRequest: boolean, call: () => Promise<unknown>) {
    const missing = !token
      ? t("demo.needToken")
      : needsRequest && !requestId
        ? t("demo.needRequest")
        : null;
    if (missing) {
      setMessage(missing);
      announce(missing, { assertive: true });
      return;
    }
    setBusy(true);
    try {
      const result = await call();
      const text =
        action === t("demo.reset") && isResetResult(result)
          ? t("demo.resetDone", { customers: result.customers, agents: result.agents })
          : t("demo.ok", { action });
      setMessage(text);
      announce(text);
    } catch (e) {
      const code = isApiError(e) ? (e as ApiError).code : "NETWORK";
      const text = t("demo.refused", { action, code });
      setMessage(text);
      announce(text, { assertive: true });
    } finally {
      setBusy(false);
    }
  }

  const request = timeline?.request;
  return (
    <Screen
      back="/signin"
      hero={
        <div className="grid gap-3">
          <PageHeading title={t("demo.title")} className="type-display">
            {t("demo.title")}
          </PageHeading>
          <p className="type-body m-0 text-zolo-secondary">{t("demo.intro")}</p>
        </div>
      }
    >
      <div className="surface rise grid gap-5 p-5">
        <div className="grid gap-1">
          <label htmlFor="demo-token" className="type-headline">
            {t("demo.token")}
          </label>
          <input
            id="demo-token"
            className={FIELD}
            type="password"
            autoComplete="off"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            aria-describedby="demo-token-hint"
          />
          <p id="demo-token-hint" className="type-secondary">
            {t("demo.tokenHint")}
          </p>
        </div>
        <div className="grid gap-1">
          <label htmlFor="demo-request" className="type-headline">
            {t("demo.request")}
          </label>
          <input
            id="demo-request"
            className={FIELD}
            type="text"
            autoComplete="off"
            spellCheck={false}
            value={requestId}
            onChange={(e) => setRequestId(e.target.value.trim())}
          />
        </div>
      </div>

      <div className="rise grid grid-cols-2 gap-3 [--rise:1]">
        <Button
          variant="secondary"
          fullWidth
          loading={busy}
          onClick={() => void run(t("demo.reset"), false, () => demoReset(token))}
        >
          {t("demo.reset")}
        </Button>
        <Button
          variant="secondary"
          fullWidth
          loading={busy}
          onClick={() => void run(t("demo.tamper"), true, () => demoTamper(token, requestId))}
        >
          {t("demo.tamper")}
        </Button>
        <Button
          variant="secondary"
          fullWidth
          loading={busy}
          onClick={() => void run(t("demo.replay"), true, () => demoReplay(token, requestId))}
        >
          {t("demo.replay")}
        </Button>
        <Button
          variant="secondary"
          fullWidth
          loading={busy}
          onClick={() => void run(t("demo.expire"), true, () => demoExpire(token, requestId))}
        >
          {t("demo.expire")}
        </Button>
      </div>
      <p className="type-body m-0 min-h-6" data-testid="demo-message">
        {message}
      </p>

      <section aria-labelledby="timeline" className="surface grid gap-4 p-5">
        <h2 id="timeline" className="type-headline m-0">
          {t("demo.timeline")}
        </h2>
        {request ? (
          <p className="type-headline m-0 flex flex-wrap items-center gap-3">
            <span>{t("demo.state")}</span>
            <Badge variant={STATE_BADGE[request.state] ?? "waiting"}>{request.state}</Badge>
            <span className="tabular-nums">{formatNaira(request.amount_kobo)}</span>
          </p>
        ) : null}
        {timeline && timeline.events.length > 0 ? (
          <ol className="m-0 grid list-none gap-3 border-s-2 border-zolo-separator p-0 ps-4">
            {timeline.events.map((ev) => (
              <li key={ev.id} className="type-body tabular-nums">
                <span className="text-zolo-secondary">
                  {new Date(ev.at).toLocaleTimeString("en-GB")}
                </span>{" "}
                {ev.event} <span className="text-zolo-secondary">({ev.actor})</span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="type-body m-0 text-zolo-secondary">{t("demo.noEvents")}</p>
        )}
      </section>
    </Screen>
  );
}
