import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TimeLeft, formatClock, type TimeLeftMessages } from "@/components/ui/TimeLeft";

const announce = vi.fn();
vi.mock("@/components/ui/LiveRegion", () => ({ useAnnounce: () => announce }));

const messages: TimeLeftMessages = {
  label: "Time left",
  oneMinute: "One minute left.",
  fifteenSeconds: "Fifteen seconds left.",
  expired: "Time is up.",
};
const T0 = Date.parse("2026-10-21T10:00:00Z");

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(T0);
  announce.mockClear();
});
afterEach(() => vi.useRealTimers());

const tick = (seconds: number) => act(() => vi.advanceTimersByTime(seconds * 1000));
const said = () => announce.mock.calls.map((c) => c[0]);

describe("formatClock", () => {
  it.each([
    [105, "1:45"],
    [60, "1:00"],
    [59, "0:59"],
    [9, "0:09"],
    [0, "0:00"],
    [120, "2:00"],
  ])("%i s is %s", (s, text) => expect(formatClock(s)).toBe(text));
});

describe("TimeLeft", () => {
  it("shows the time left, and counts down", () => {
    render(<TimeLeft expiresAt={T0 + 105_000} messages={messages} />);
    expect(screen.getByText("1:45")).toBeInTheDocument();
    tick(1);
    expect(screen.getByText("1:44")).toBeInTheDocument();
  });

  it("is a <time> with a machine-readable duration", () => {
    render(<TimeLeft expiresAt={T0 + 105_000} messages={messages} />);
    expect(screen.getByText("1:45")).toHaveAttribute("datetime", "PT105S");
  });

  it("accepts the API's ISO timestamp", () => {
    render(<TimeLeft expiresAt="2026-10-21T10:02:00Z" messages={messages} />);
    expect(screen.getByText("2:00")).toBeInTheDocument();
  });

  it("is NOT a live region: the ticking digits are not announced every second", () => {
    const { container } = render(<TimeLeft expiresAt={T0 + 105_000} messages={messages} />);
    expect(
      container.querySelector("[aria-live], [role=status], [role=alert], [role=timer]"),
    ).toBeNull();
  });

  it("speaks exactly three times over a whole countdown: 60 s, 15 s, and time up", () => {
    const onExpire = vi.fn();
    render(<TimeLeft expiresAt={T0 + 105_000} messages={messages} onExpire={onExpire} />);
    expect(said()).toEqual([]);
    tick(44); // 61 left
    expect(said()).toEqual([]);
    tick(1); // 60 left
    expect(said()).toEqual(["One minute left."]);
    tick(44); // 16 left
    expect(said()).toEqual(["One minute left."]);
    tick(1); // 15 left
    expect(said()).toEqual(["One minute left.", "Fifteen seconds left."]);
    tick(14);
    expect(said()).toHaveLength(2);
    tick(1); // 0
    expect(said()).toEqual(["One minute left.", "Fifteen seconds left.", "Time is up."]);
    expect(onExpire).toHaveBeenCalledTimes(1);
    tick(30); // and nothing more, ever
    expect(said()).toHaveLength(3);
    expect(onExpire).toHaveBeenCalledTimes(1);
  });

  it("does not say 'one minute left' just because the screen opened with 45 seconds left", () => {
    render(<TimeLeft expiresAt={T0 + 45_000} messages={messages} />);
    tick(29); // 16 left
    expect(said()).toEqual([]);
    tick(1); // 15 left
    expect(said()).toEqual(["Fifteen seconds left."]);
  });

  it("opening with 10 seconds left says nothing until time is up", () => {
    render(<TimeLeft expiresAt={T0 + 10_000} messages={messages} />);
    tick(9);
    expect(said()).toEqual([]);
    tick(1);
    expect(said()).toEqual(["Time is up."]);
  });

  it("an already-expired request shows 0:00 and still tells the owner (onExpire) once", () => {
    const onExpire = vi.fn();
    render(<TimeLeft expiresAt={T0 - 5_000} messages={messages} onExpire={onExpire} />);
    expect(screen.getByText("0:00")).toBeInTheDocument();
    tick(5);
    expect(onExpire).toHaveBeenCalledTimes(1);
  });

  it("a renewal (new expiry) starts again, with no false 'time is up'", () => {
    const { rerender } = render(<TimeLeft expiresAt={T0 + 20_000} messages={messages} />);
    tick(20);
    expect(said()).toEqual(["Time is up."]);
    announce.mockClear();
    rerender(<TimeLeft expiresAt={T0 + 20_000 + 120_000} messages={messages} />);
    tick(1);
    expect(said()).toEqual([]); // not expired any more, and nothing stale was announced
    expect(screen.getByText("1:59")).toBeInTheDocument();
    tick(59); // 60 left
    expect(said()).toEqual(["One minute left."]);
  });

  it("uses the injected clock (so a phone with the wrong time can be corrected)", () => {
    render(<TimeLeft expiresAt={T0 + 105_000} messages={messages} now={() => T0 + 45_000} />);
    expect(screen.getByText("1:00")).toBeInTheDocument();
  });
});
