import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PageHeading } from "@/components/PageHeading";
import { markNavigated } from "@/lib/initial-load";

describe("PageHeading", () => {
  it("moves focus to the h1 and sets the tab title on a route change", () => {
    markNavigated();
    render(<PageHeading title="Pay an agent">Pay an agent</PageHeading>);
    expect(screen.getByRole("heading", { level: 1 })).toHaveFocus();
    expect(document.title).toBe("Pay an agent · Zolo");
  });

  it("leaves focus alone on a fresh page load, so the first Tab still reaches the skip link", async () => {
    vi.resetModules();
    const { PageHeading: Fresh } = await import("@/components/PageHeading"); // a new module = a new page load
    render(<Fresh title="Home">Home</Fresh>);
    expect(screen.getByRole("heading", { level: 1 })).not.toHaveFocus();
  });

  it("does not take focus when told the screen manages it (the review screen)", () => {
    markNavigated();
    render(
      <PageHeading title="Review" manualFocus>
        Review
      </PageHeading>,
    );
    expect(screen.getByRole("heading", { level: 1 })).not.toHaveFocus();
  });
});
