import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Home, whenWords } from "@/app/(app)/home/Home";
import { t } from "@/lib/i18n";
import { router } from "../router";
import { installFakeBackend } from "../fake-server";
import { heardRequest, renderScreen } from "./helpers";

const fake = installFakeBackend();

describe("Home", () => {
  it("has one h1, the Zolo wordmark with 'for Zenith Bank', and no Zenith logo", async () => {
    fake.actAs("customer");
    renderScreen(<Home />);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(screen.getByText(/for Zenith Bank/i)).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    await screen.findByText(t("home.recentEmpty"));
  });

  it("offers only what exists: Pay an agent (no Send money, no Card Guard)", async () => {
    fake.actAs("customer");
    renderScreen(<Home />);
    expect(screen.getByRole("link", { name: /Pay an agent/ })).toHaveAttribute("href", "/pay/code");
    expect(screen.queryByText(/send money|card/i)).not.toBeInTheDocument();
    await screen.findByText(t("home.recentEmpty"));
  });

  it("shows the last payments one per line, with the amount in words for screen readers", async () => {
    await heardRequest(fake);
    // finish one so it appears in the activity list
    fake.addPasskey();
    await fetch("/api/requests/" + [...fake.requests.keys()][0] + "/decline", { method: "POST" });
    renderScreen(<Home />);
    const item = await screen.findByText(/Declined fifteen thousand naira to Bisi Ventures, today/);
    expect(item.closest("li")).toHaveTextContent("Declined ₦15,000 to Bisi Ventures, today");
  });

  it("sends a signed-out visitor to the sign-in chooser and an agent to their page", async () => {
    renderScreen(<Home />);
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/signin"));
    router.replace.mockReset();
    fake.actAs("agent");
    renderScreen(<Home />);
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/agent"));
  });

  it("dates read 'today', 'yesterday', then '14 Oct'", () => {
    const now = new Date("2026-10-21T12:00:00");
    expect(whenWords("2026-10-21T08:00:00", now, t)).toBe("today");
    expect(whenWords("2026-10-20T23:00:00", now, t)).toBe("yesterday");
    expect(whenWords("2026-10-14T09:00:00", now, t)).toBe("14 Oct");
  });
});
