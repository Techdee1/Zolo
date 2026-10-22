import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";
import { Button } from "@/components/ui/Button";

describe("Button", () => {
  it("is a real button with its text as the accessible name", () => {
    render(<Button>Approve ₦15,000</Button>);
    expect(screen.getByRole("button", { name: "Approve ₦15,000" })).toBeInTheDocument();
  });

  it("is type=button by default, so it never submits a form by accident", () => {
    render(<Button>Go</Button>);
    expect(screen.getByRole("button")).toHaveAttribute("type", "button");
  });

  it("calls onClick for a click, Enter and Space: one tap or one key is enough", async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(<Button onClick={onClick}>Go</Button>);
    const button = screen.getByRole("button");
    await user.click(button);
    button.focus();
    await user.keyboard("{Enter}");
    await user.keyboard(" ");
    expect(onClick).toHaveBeenCalledTimes(3);
  });

  describe("when it cannot be used yet", () => {
    it("is aria-disabled but STILL focusable, so a screen reader user finds it", async () => {
      const user = userEvent.setup();
      render(
        <Button disabled disabledReason="Listen to the request first">
          Approve
        </Button>,
      );
      const button = screen.getByRole("button", { name: "Approve" });
      expect(button).toHaveAttribute("aria-disabled", "true");
      expect(button).not.toBeDisabled(); // not natively disabled: it stays in the tab order
      await user.tab();
      expect(button).toHaveFocus();
    });

    it("explains why, in its description", () => {
      render(
        <Button disabled disabledReason="Listen to the request first">
          Approve
        </Button>,
      );
      expect(screen.getByRole("button", { name: "Approve" })).toHaveAccessibleDescription(
        "Listen to the request first",
      );
    });

    it("ignores clicks and the keyboard", async () => {
      const onClick = vi.fn();
      const user = userEvent.setup();
      render(
        <Button disabled disabledReason="why" onClick={onClick}>
          Approve
        </Button>,
      );
      const button = screen.getByRole("button");
      await user.click(button);
      button.focus();
      await user.keyboard("{Enter}");
      await user.keyboard(" ");
      expect(onClick).not.toHaveBeenCalled();
    });

    it("works again as soon as it is enabled, and the reason is gone", () => {
      const { rerender } = render(
        <Button disabled disabledReason="why">
          Approve
        </Button>,
      );
      rerender(<Button>Approve</Button>);
      const button = screen.getByRole("button", { name: "Approve" });
      expect(button).not.toHaveAttribute("aria-disabled");
      expect(button).not.toHaveAccessibleDescription();
    });
  });

  it("while loading: busy, and clicks are ignored", async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(
      <Button loading onClick={onClick}>
        Request
      </Button>,
    );
    const button = screen.getByRole("button");
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(button).toHaveAttribute("aria-disabled", "true");
    await user.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("keeps a caller's aria-describedby together with its own reason", () => {
    render(
      <>
        <p id="hint">Hint text</p>
        <Button aria-describedby="hint" disabled disabledReason="Not yet">
          Approve
        </Button>
      </>,
    );
    expect(screen.getByRole("button")).toHaveAccessibleDescription("Hint text Not yet");
  });

  it("hides a decorative icon from screen readers", () => {
    render(<Button icon={<svg data-testid="icon" />}>Go</Button>);
    expect(screen.getByTestId("icon").parentElement).toHaveAttribute("aria-hidden", "true");
  });

  it("marks its variant and forwards a ref", () => {
    const ref = createRef<HTMLButtonElement>();
    render(
      <Button variant="primary" ref={ref}>
        Go
      </Button>,
    );
    expect(screen.getByRole("button")).toHaveAttribute("data-variant", "primary");
    expect(ref.current).toBe(screen.getByRole("button"));
  });
});
