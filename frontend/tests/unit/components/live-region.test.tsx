import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LiveRegionProvider, useAnnounce } from "@/components/ui/LiveRegion";

function Speak({ text, assertive }: { text: string; assertive?: boolean }) {
  const announce = useAnnounce();
  return <button onClick={() => announce(text, { assertive })}>say</button>;
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

const polite = () => document.querySelector('[data-live-region="polite"]')!;
const assertive = () => document.querySelector('[data-live-region="assertive"]')!;
const flush = () => act(() => vi.advanceTimersByTime(100));
const click = () => act(() => screen.getByRole("button").click());

describe("LiveRegion", () => {
  it("has exactly ONE polite region and ONE assertive region, always in the page", () => {
    render(
      <LiveRegionProvider>
        <p>content</p>
      </LiveRegionProvider>,
    );
    expect(document.querySelectorAll('[aria-live="polite"]')).toHaveLength(1);
    expect(document.querySelectorAll('[aria-live="assertive"]')).toHaveLength(1);
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("announces politely by default", () => {
    render(
      <LiveRegionProvider>
        <Speak text="Paid. You sent ₦15,000 to Bisi Ventures." />
      </LiveRegionProvider>,
    );
    click();
    flush();
    expect(polite()).toHaveTextContent("Paid. You sent ₦15,000 to Bisi Ventures.");
    expect(assertive()).toBeEmptyDOMElement();
  });

  it("announces errors assertively, in the other region", () => {
    render(
      <LiveRegionProvider>
        <Speak text="Something went wrong." assertive />
      </LiveRegionProvider>,
    );
    click();
    flush();
    expect(assertive()).toHaveTextContent("Something went wrong.");
    expect(polite()).toBeEmptyDOMElement();
  });

  it("clears first, so saying the same thing twice is heard twice", () => {
    render(
      <LiveRegionProvider>
        <Speak text="Waiting for the agent." />
      </LiveRegionProvider>,
    );
    click();
    flush();
    expect(polite()).toHaveTextContent("Waiting for the agent.");
    click();
    expect(polite()).toBeEmptyDOMElement(); // emptied: the next set is a change a screen reader notices
    flush();
    expect(polite()).toHaveTextContent("Waiting for the agent.");
  });

  it("is atomic and hidden from the eye (but not from screen readers)", () => {
    render(
      <LiveRegionProvider>
        <p>x</p>
      </LiveRegionProvider>,
    );
    expect(polite()).toHaveAttribute("aria-atomic", "true");
    expect(polite().parentElement).toHaveClass("sr-only");
  });

  it("fails loudly, not silently, when used outside the provider", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Speak text="x" />)).toThrow(/LiveRegionProvider/);
  });
});
