import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Home } from "@/app/(app)/home/Home";
import { AgentNewRequest } from "@/app/(app)/agent/AgentNewRequest";
import { ReviewScreen } from "@/app/(app)/requests/[id]/ReviewScreen";
import { SetupPasskey } from "@/app/(app)/setup/passkey/SetupPasskey";
import { createPasskey, passkeySupport } from "@/lib/passkeys";
import { setPasskeyKnown } from "@/lib/passkey-status";
import { installFakeBackend } from "../fake-server";
import { claimedRequest, renderScreen } from "./helpers";

// The demo flag is a build-time constant; tests flip it here.
const flags = vi.hoisted(() => ({ featureDemo: false }));
vi.mock("@/lib/env", async (orig) => ({
  ...(await orig<typeof import("@/lib/env")>()),
  env: flags,
}));
vi.mock("@/lib/passkeys", async (orig) => ({
  ...(await orig<typeof import("@/lib/passkeys")>()),
  createPasskey: vi.fn(),
  passkeySupport: vi.fn(),
}));

const fake = installFakeBackend();

beforeEach(() => {
  flags.featureDemo = false;
  localStorage.clear();
  setPasskeyKnown(false);
});

describe("the role label: customer and agent are told apart at a glance", () => {
  it("customer screens say Customer, agent screens say Agent, and each marks itself for the tint", async () => {
    fake.actAs("customer");
    const { unmount } = renderScreen(<Home />);
    expect(screen.getByText("Customer")).toBeInTheDocument();
    expect(document.querySelector("main")).toHaveAttribute("data-role", "customer");
    await screen.findByText("No payments yet.");
    unmount();
    fake.actAs("agent");
    renderScreen(<AgentNewRequest />);
    expect(screen.getByText("Agent")).toBeInTheDocument();
    expect(document.querySelector("main")).toHaveAttribute("data-role", "agent");
  });

  it("is a small pill in the page header, not a banner", () => {
    fake.actAs("agent");
    renderScreen(<AgentNewRequest />);
    const header = document.querySelector("header")!;
    expect(within(header).getByText("Agent")).toBeInTheDocument();
    expect(within(header).getByText("Agent")).toHaveClass("type-caption", "rounded-full");
    expect(header.closest("main")).not.toBeNull(); // inside the page, not a site-wide banner
  });
});

describe("demo tools live in a menu, and only in demo builds", () => {
  it("a customer build has no demo menu and no 'Switch demo user' anywhere on home", async () => {
    fake.actAs("customer");
    renderScreen(<Home />);
    await screen.findByText("No payments yet.");
    expect(screen.queryByRole("button", { name: "Demo tools" })).not.toBeInTheDocument();
    expect(screen.queryByText(/switch demo user/i)).not.toBeInTheDocument();
  });

  it("a demo build has a small Demo tools button that opens a sheet with switch-user and the console", async () => {
    flags.featureDemo = true;
    fake.actAs("customer");
    renderScreen(<Home />);
    await screen.findByText("No payments yet.");
    await userEvent.click(screen.getByRole("button", { name: "Demo tools" }));
    const sheet = await screen.findByRole("dialog", { name: "Demo tools" });
    expect(within(sheet).getByRole("link", { name: "Switch demo user" })).toHaveAttribute(
      "href",
      "/signin",
    );
    expect(within(sheet).getByRole("link", { name: "Demo console" })).toHaveAttribute(
      "href",
      "/demo",
    );
  });
});

describe("the passkey row on home", () => {
  it("says Not set up, with Set up as its action, until a passkey is made on this phone", async () => {
    fake.actAs("customer");
    renderScreen(<Home />);
    const row = await screen.findByRole("link", { name: /Passkey/ });
    expect(row).toHaveAttribute("href", "/setup/passkey");
    expect(row).toHaveTextContent("Not set up");
    expect(row).toHaveTextContent("Set up");
  });

  it("says Set up on this phone, with Replace as its action, once it is", async () => {
    setPasskeyKnown(true);
    fake.actAs("customer");
    renderScreen(<Home />);
    const row = await screen.findByRole("link", { name: /Passkey/ });
    expect(row).toHaveTextContent("Set up on this phone");
    expect(row).toHaveTextContent("Replace");
  });

  it("is remembered after setup succeeds", async () => {
    vi.mocked(passkeySupport).mockResolvedValue("ok");
    vi.mocked(createPasskey).mockResolvedValue({ id: "c", response: {} });
    fake.actAs("customer");
    renderScreen(<SetupPasskey next="/" />);
    await userEvent.click(await screen.findByRole("button", { name: "Set up passkey" }));
    await screen.findByText("Your passkey is ready.");
    expect(localStorage.getItem("zolo.passkey")).toBe("1");
  });
});

describe("the review screen explains a missing passkey instead of failing", () => {
  it("shows a card with what a passkey is and a way to set one up, then back to this request", async () => {
    await claimedRequest(fake);
    const id = [...fake.requests.keys()][0]!;
    renderScreen(<ReviewScreen id={id} />);
    const card = await screen.findByRole("region", { name: "Set up your passkey first" });
    expect(card).toHaveTextContent(/fingerprint, face or screen lock/);
    expect(within(card).getByRole("link", { name: "Set up passkey" })).toHaveAttribute(
      "href",
      `/setup/passkey?next=${encodeURIComponent(`/requests/${id}`)}`,
    );
  });

  it("is not shown once this phone has a passkey", async () => {
    setPasskeyKnown(true);
    await claimedRequest(fake);
    renderScreen(<ReviewScreen id={[...fake.requests.keys()][0]!} />);
    await screen.findByRole("heading", { level: 2, name: "What Zolo says" });
    await waitFor(() =>
      expect(screen.queryByText("Set up your passkey first")).not.toBeInTheDocument(),
    );
  });
});

describe("the review hero", () => {
  it("shows the payee, the amount and the words as one card, and says them once to a screen reader", async () => {
    await claimedRequest(fake);
    renderScreen(<ReviewScreen id={[...fake.requests.keys()][0]!} />);
    await screen.findByRole("heading", { level: 2, name: "What Zolo says" });
    const hero = document.querySelector(".type-hero")!;
    expect(hero).toHaveTextContent("₦15,000");
    expect(hero.closest("[aria-hidden=true]")).not.toBeNull(); // the h1 carries it for assistive tech
    expect(screen.getByRole("heading", { level: 1 })).toHaveAccessibleName(
      "Bisi Ventures is asking for fifteen thousand naira",
    );
  });

  it("pins Approve and Decline in a bottom action area", async () => {
    await claimedRequest(fake);
    renderScreen(<ReviewScreen id={[...fake.requests.keys()][0]!} />);
    await screen.findByRole("heading", { level: 2, name: "What Zolo says" });
    const bar = document.querySelector(".action-bar")!;
    expect(
      within(bar as HTMLElement).getByRole("button", { name: /^Approve/ }),
    ).toBeInTheDocument();
    expect(within(bar as HTMLElement).getByRole("button", { name: "Decline" })).toBeInTheDocument();
  });
});
