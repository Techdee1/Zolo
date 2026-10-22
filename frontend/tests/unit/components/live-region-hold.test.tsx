import { act, render, screen, waitFor } from "@testing-library/react";
import { useEffect } from "react";
import { describe, expect, it } from "vitest";
import { LiveRegionProvider, useAnnounce, useHoldAnnouncements } from "@/components/ui/LiveRegion";

let controls: {
  announce: ReturnType<typeof useAnnounce>;
  hold: ReturnType<typeof useHoldAnnouncements>;
};
function Probe() {
  const announce = useAnnounce();
  const hold = useHoldAnnouncements();
  useEffect(() => {
    controls = { announce, hold };
  });
  return null;
}
const polite = () => document.querySelector("[data-live-region=polite]")?.textContent;

describe("holding announcements while Zolo speaks", () => {
  it("says nothing while held, then only the latest message when released", async () => {
    render(
      <LiveRegionProvider>
        <Probe />
      </LiveRegionProvider>,
    );
    let release!: () => void;
    act(() => {
      release = controls.hold();
    });
    act(() => {
      controls.announce("one");
      controls.announce("two");
    });
    await new Promise((r) => setTimeout(r, 120));
    expect(polite()).toBe("");
    act(() => release());
    await waitFor(() => expect(polite()).toBe("two"));
  });

  it("waits for every hold, and releasing twice is harmless", async () => {
    render(
      <LiveRegionProvider>
        <Probe />
      </LiveRegionProvider>,
    );
    let a!: () => void, b!: () => void;
    act(() => {
      a = controls.hold();
      b = controls.hold();
    });
    act(() => controls.announce("later"));
    act(() => {
      a();
      a();
    });
    await new Promise((r) => setTimeout(r, 120));
    expect(polite()).toBe("");
    act(() => b());
    await waitFor(() => expect(polite()).toBe("later"));
    expect(screen.getByRole("status")).toBeInTheDocument();
  });
});
