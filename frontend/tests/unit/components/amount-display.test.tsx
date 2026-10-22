import { vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AmountDisplay } from "@/components/ui/AmountDisplay";
import { InvalidAmountError } from "@/lib/format/money";

describe("AmountDisplay", () => {
  it("shows the digits to the eye but hides them from screen readers", () => {
    render(<AmountDisplay kobo={1_500_000} unit="naira" />);
    const digits = screen.getByText("₦15,000");
    expect(digits).toHaveAttribute("aria-hidden", "true");
  });

  it("gives screen readers the amount in WORDS", () => {
    render(<AmountDisplay kobo={1_500_000} unit="naira" />);
    expect(screen.getByText("fifteen thousand naira")).toHaveClass("sr-only");
  });

  it("does not let fifteen and fifty sound alike", () => {
    const { rerender } = render(<AmountDisplay kobo={1_500_000} unit="naira" />);
    expect(screen.getByText(/thousand naira/)).toHaveTextContent("fifteen thousand naira");
    rerender(<AmountDisplay kobo={5_000_000} unit="naira" />);
    expect(screen.getByText(/thousand naira/)).toHaveTextContent("fifty thousand naira");
  });

  it("prefers the BACKEND's words when given, so screen and spoken readback match", () => {
    render(<AmountDisplay kobo={1_500_000} words="fifteen thousand" unit="naira" />);
    expect(screen.getByText("fifteen thousand naira")).toBeInTheDocument();
  });

  it("with showWords, the words are visible and are the accessible text (nothing read twice)", () => {
    render(<AmountDisplay kobo={1_500_000} unit="naira" showWords />);
    const words = screen.getByText("fifteen thousand naira");
    expect(words).not.toHaveClass("sr-only");
    expect(screen.getAllByText("fifteen thousand naira")).toHaveLength(1);
    expect(screen.getByText("₦15,000")).toHaveAttribute("aria-hidden", "true");
  });

  it("uses the amount type style at hero size, with tabular figures", () => {
    render(<AmountDisplay kobo={1_500_000} unit="naira" />);
    expect(screen.getByText("₦15,000")).toHaveClass("type-hero");
  });

  it("shows kobo only when there are some", () => {
    render(<AmountDisplay kobo={1_500_050} unit="naira" />);
    expect(screen.getByText("₦15,000.50")).toBeInTheDocument();
    expect(screen.getByText("fifteen thousand naira and fifty kobo")).toBeInTheDocument();
  });

  it.each([
    ["a float", 1500000.5],
    ["negative", -1],
    ["NaN", Number.NaN],
    ["a string", "1500000"],
  ])("REFUSES to render %s: money that failed validation is never shown", (_label, bad) => {
    const quiet = () => {};
    const spy = vi.spyOn(console, "error").mockImplementation(quiet);
    expect(() => render(<AmountDisplay kobo={bad as number} unit="naira" />)).toThrow(
      InvalidAmountError,
    );
    spy.mockRestore();
  });
});
