import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Home from "@/app/page";

describe("scaffold home", () => {
  it("has one h1 and a main landmark", () => {
    render(<Home />);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("main")).toBeInTheDocument();
  });

  it("shows the Zolo wordmark with 'for Zenith Bank' and never the Zenith logo", () => {
    render(<Home />);
    expect(screen.getByText(/for Zenith Bank/i)).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});
