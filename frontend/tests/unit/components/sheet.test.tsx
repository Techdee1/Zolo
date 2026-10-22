import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Sheet } from "@/components/ui/Sheet";

const animate = vi.fn();
const reduced = vi.fn(() => false);
vi.mock("motion", () => ({
  animate: (...args: unknown[]) => {
    animate(...args);
    return { finished: Promise.resolve(), stop: vi.fn() };
  },
}));
vi.mock("motion/react", () => ({ useReducedMotion: () => reduced() }));

// jsdom does not implement <dialog> modality, so give it the minimum a browser does.
beforeEach(() => {
  animate.mockClear();
  reduced.mockReturnValue(false);
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.removeAttribute("open");
  };
});
afterEach(() => vi.restoreAllMocks());

const dialog = () => document.querySelector("dialog")!;
const sheet = (props: Partial<React.ComponentProps<typeof Sheet>> = {}) => (
  <Sheet open title="More time?" closeLabel="Close" onClose={vi.fn()} {...props}>
    <p>Body text</p>
  </Sheet>
);

describe("Sheet", () => {
  it("is a dialog named by its heading", () => {
    render(sheet());
    expect(screen.getByRole("dialog", { name: "More time?" })).toBeInTheDocument();
    expect(dialog()).toHaveAttribute(
      "aria-labelledby",
      screen.getByRole("heading", { name: "More time?" }).id,
    );
  });

  it("is closed until opened", () => {
    render(sheet({ open: false }));
    expect(dialog()).not.toHaveAttribute("open");
  });

  it("opens as a modal and puts focus on its heading, so a screen reader starts at the top", () => {
    render(sheet());
    expect(dialog()).toHaveAttribute("open");
    expect(screen.getByRole("heading", { name: "More time?" })).toHaveFocus();
  });

  it("every way out is one tap: the Close button...", async () => {
    const onClose = vi.fn();
    render(sheet({ onClose }));
    await userEvent.setup().click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("...Escape (and the browser's own close is held back: the owner decides)...", () => {
    const onClose = vi.fn();
    render(sheet({ onClose }));
    const cancel = new Event("cancel", { cancelable: true });
    act(() => void dialog().dispatchEvent(cancel));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(cancel.defaultPrevented).toBe(true);
  });

  it("...or a tap on the scrim, but not a tap inside the sheet", () => {
    const onClose = vi.fn();
    render(sheet({ onClose }));
    fireEvent.click(screen.getByText("Body text"));
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.click(dialog()); // the dialog itself is the backdrop area
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("slides up on the sheet spring (damping 0.8, response 0.3), and the other way to leave", async () => {
    const { rerender } = render(sheet({ open: true }));
    const [, enter, enterSpring] = animate.mock.calls[0]!;
    expect(enter).toMatchObject({ y: ["100%", "0%"] });
    expect(enterSpring).toMatchObject({ type: "spring", mass: 1 });
    expect(enterSpring.damping ** 2).toBeLessThan(4 * enterSpring.stiffness); // bouncy: under-damped

    animate.mockClear();
    rerender(sheet({ open: false }));
    expect(animate.mock.calls[0]![1]).toEqual({ y: "100%" }); // back the way it came
    await act(async () => void (await Promise.resolve()));
    expect(dialog()).not.toHaveAttribute("open"); // closed once the animation ended
  });

  it("under reduced motion it only fades: no slide, no spring", () => {
    reduced.mockReturnValue(true);
    const { rerender } = render(sheet({ open: true }));
    expect(animate.mock.calls[0]![1]).toEqual({ opacity: [0, 1] });
    expect(animate.mock.calls[0]![2]).toEqual({ duration: 0.15 }); // a short fade, not a spring
    animate.mockClear();
    rerender(sheet({ open: false }));
    expect(animate.mock.calls[0]![1]).toEqual({ opacity: 0 });
  });

  it("animates only transform and opacity (nothing that forces layout)", () => {
    const { rerender } = render(sheet({ open: true }));
    rerender(sheet({ open: false }));
    const animated = new Set(animate.mock.calls.flatMap((c) => Object.keys(c[1] as object)));
    expect([...animated].every((k) => ["y", "opacity"].includes(k))).toBe(true);
  });
});
