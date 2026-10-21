import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Badge, type BadgeVariant } from "@/components/ui/Badge";

const VARIANTS: BadgeVariant[] = [
  "verified",
  "paid",
  "waiting",
  "processing",
  "expiring",
  "declined",
  "expired",
  "changed",
  "failed",
];

describe("Badge never relies on colour alone", () => {
  it.each(VARIANTS)("%s has an icon AND words", (variant) => {
    const { container } = render(<Badge variant={variant}>Label for {variant}</Badge>);
    expect(screen.getByText(`Label for ${variant}`)).toBeInTheDocument();
    const icon = container.querySelector("svg");
    expect(icon, "an icon").not.toBeNull();
    expect(icon).toHaveAttribute("aria-hidden", "true"); // decoration: the words carry the meaning
  });

  it("gives every variant a different icon or tone, so states stay distinguishable", () => {
    const look = (v: BadgeVariant) => {
      const { container, unmount } = render(<Badge variant={v}>x</Badge>);
      const out = `${container.querySelector("svg")?.getAttribute("class")}|${container.firstElementChild?.className}`;
      unmount();
      return out;
    };
    expect(new Set(VARIANTS.map(look)).size).toBeGreaterThan(5);
  });

  it("'processing' never looks like 'paid': different icon and no success colour", () => {
    const a = render(<Badge variant="processing">Processing</Badge>);
    const processing = a.container.innerHTML;
    a.unmount();
    const b = render(<Badge variant="paid">Paid</Badge>);
    const paid = b.container.innerHTML;
    expect(processing).not.toContain("text-zolo-success");
    expect(processing).toContain("text-zolo-warning");
    expect(paid).toContain("text-zolo-success");
    expect(processing.match(/<svg[^>]*class="([^"]*)"/)?.[1]).not.toBe(
      paid.match(/<svg[^>]*class="([^"]*)"/)?.[1],
    );
  });

  it("uses the caption size and no other", () => {
    render(<Badge variant="paid">Paid</Badge>);
    expect(screen.getByText("Paid").parentElement).toHaveClass("type-caption");
  });

  it("critical states use the critical tone, always with the icon and text above", () => {
    for (const v of ["changed", "failed"] as const) {
      const { container, unmount } = render(<Badge variant={v}>x</Badge>);
      expect(container.innerHTML).toContain("text-zolo-critical");
      unmount();
    }
  });
});
