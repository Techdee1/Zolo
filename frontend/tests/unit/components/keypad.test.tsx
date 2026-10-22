import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { Keypad, type KeypadLabels } from "@/components/ui/Keypad";
import { appendDigit, deleteDigit } from "@/lib/format/amount-entry";

const labels: KeypadLabels = {
  group: "Amount keypad",
  clear: "Clear",
  backspace: "Delete last digit",
};

function Harness() {
  const [naira, setNaira] = useState(0);
  return (
    <>
      <output aria-label="entered">{naira}</output>
      <Keypad
        labels={labels}
        onDigit={(d) => setNaira((n) => appendDigit(n, d))}
        onBackspace={() => setNaira(deleteDigit)}
        onClear={() => setNaira(0)}
      />
    </>
  );
}

describe("Keypad", () => {
  it("is a labelled group of twelve real buttons", () => {
    render(<Keypad labels={labels} onDigit={vi.fn()} onBackspace={vi.fn()} onClear={vi.fn()} />);
    const group = screen.getByRole("group", { name: "Amount keypad" });
    expect(within(group).getAllByRole("button")).toHaveLength(12);
  });

  it("names every key: digits by their digit, the others in words", () => {
    render(<Keypad labels={labels} onDigit={vi.fn()} onBackspace={vi.fn()} onClear={vi.fn()} />);
    for (const d of "0123456789")
      expect(screen.getByRole("button", { name: d })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clear" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete last digit" })).toBeInTheDocument();
  });

  it("lays the digits out like a phone: 1-2-3 / 4-5-6 / 7-8-9 / clear 0 delete", () => {
    render(<Keypad labels={labels} onDigit={vi.fn()} onBackspace={vi.fn()} onClear={vi.fn()} />);
    const order = screen
      .getAllByRole("button")
      .map((b) => b.getAttribute("aria-label") ?? b.textContent);
    expect(order).toEqual([
      "1",
      "2",
      "3",
      "4",
      "5",
      "6",
      "7",
      "8",
      "9",
      "Clear",
      "0",
      "Delete last digit",
    ]);
  });

  it("types an amount with single taps", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    for (const key of ["1", "5", "0", "0", "0"])
      await user.click(screen.getByRole("button", { name: key }));
    expect(screen.getByLabelText("entered")).toHaveTextContent("15000");
    await user.click(screen.getByRole("button", { name: "Delete last digit" }));
    expect(screen.getByLabelText("entered")).toHaveTextContent("1500");
    await user.click(screen.getByRole("button", { name: "Clear" }));
    expect(screen.getByLabelText("entered")).toHaveTextContent("0");
  });

  it("stops at the cap instead of showing an amount that cannot be sent", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    for (const key of ["1", "0", "0", "0", "0", "0", "0", "0"])
      await user.click(screen.getByRole("button", { name: key }));
    expect(screen.getByLabelText("entered")).toHaveTextContent("100000");
  });

  it("is only for amounts: no text field, no masking, nothing PIN-like", () => {
    const { container } = render(
      <Keypad labels={labels} onDigit={vi.fn()} onBackspace={vi.fn()} onClear={vi.fn()} />,
    );
    expect(container.querySelector("input")).toBeNull();
    expect(container.innerHTML).not.toMatch(/password|pin|secure|autocomplete/i);
  });

  it("never lets the digit buttons submit a form", () => {
    render(<Keypad labels={labels} onDigit={vi.fn()} onBackspace={vi.fn()} onClear={vi.fn()} />);
    for (const b of screen.getAllByRole("button")) expect(b).toHaveAttribute("type", "button");
  });
});
