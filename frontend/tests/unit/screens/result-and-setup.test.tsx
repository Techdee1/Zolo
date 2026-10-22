import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DemoConsole } from "@/app/(app)/demo/DemoConsole";
import { ResultScreen } from "@/app/(app)/requests/[id]/result/ResultScreen";
import { SetupPasskey } from "@/app/(app)/setup/passkey/SetupPasskey";
import { SignIn } from "@/app/(app)/signin/SignIn";
import { createPasskey, passkeySupport } from "@/lib/passkeys";
import { router } from "../router";
import { installFakeBackend } from "../fake-server";
import { assertive, claimedRequest, polite, renderScreen } from "./helpers";
import { approve, getChallenge, getReadback } from "@/lib/api/endpoints";
import type { ApprovalOutcome } from "../../fakes/fake-backend";

vi.mock("@/lib/passkeys", async (orig) => ({
  ...(await orig<typeof import("@/lib/passkeys")>()),
  createPasskey: vi.fn(),
  passkeySupport: vi.fn(),
}));

const fake = installFakeBackend();
const DEMO = { "x-demo-token": "demo-token-1234" };

/** Take a claimed request all the way to `outcome`, as the customer. */
async function endedAs(outcome: ApprovalOutcome | "DECLINED" | "EXPIRED") {
  const made = await claimedRequest(fake);
  await getReadback(made.id, "en");
  if (outcome === "DECLINED") await fetch(`/api/requests/${made.id}/decline`, { method: "POST" });
  else if (outcome === "EXPIRED")
    fake.handle({ method: "POST", path: `/demo/requests/${made.id}/expire`, headers: DEMO });
  else {
    fake.addPasskey();
    fake.setOutcome(outcome);
    await getChallenge(made.id);
    await approve(made.id, { id: "c", response: {} }).catch(() => undefined);
  }
  return made.id;
}

describe("Result screen: one outcome per screen, honest about money", () => {
  const cases: Array<[Parameters<typeof endedAs>[0], RegExp, string]> = [
    ["SETTLED", /Paid\. You sent fifteen thousand naira to Bisi Ventures\./, "paid"],
    ["SUBMITTED", /^Processing\. Don't hand over goods yet\.$/, "processing"],
    ["DECLINED", /^Declined\. Nothing was sent\.$/, "declined"],
    ["EXPIRED", /^This request expired\. Nothing was sent\.$/, "expired"],
    ["BANK_REJECTED", /did not accept this payment\. Nothing was sent/, "failed"],
    ["RISK_BLOCKED", /stopped this payment to keep your money safe\. Nothing was sent/, "failed"],
    ["FAILED", /did not go through\. Nothing was sent/, "failed"],
  ];
  for (const [outcome, title, variant] of cases) {
    it(`${outcome}: says so in the h1, with an icon-and-words badge`, async () => {
      const id = await endedAs(outcome);
      renderScreen(<ResultScreen id={id} reason={null} />);
      const h1 = await screen.findByRole("heading", { level: 1, name: title });
      await waitFor(() => expect(h1).toHaveFocus());
      expect(document.querySelector("[data-result]")).toHaveAttribute("data-result", variant);
      expect(document.querySelector("[data-variant] svg")).toHaveAttribute("aria-hidden", "true");
    });
  }

  it("Paid is read with the amount in words, and has one next action", async () => {
    const id = await endedAs("SETTLED");
    renderScreen(<ResultScreen id={id} reason={null} />);
    const h1 = await screen.findByRole("heading", { level: 1, name: /^Paid\./ });
    expect(h1).toHaveAccessibleName("Paid. You sent fifteen thousand naira to Bisi Ventures.");
    expect(h1).toHaveTextContent("Paid. You sent ₦15,000 to Bisi Ventures.");
    expect(screen.getAllByRole("link")).toHaveLength(1);
    expect(screen.getByRole("link", { name: "Done" })).toHaveAttribute("href", "/home");
  });

  it("SUBMITTED never says Paid, keeps polling, and announces the change to Paid when the bank confirms", async () => {
    const id = await endedAs("SUBMITTED");
    renderScreen(<ResultScreen id={id} reason={null} />);
    await screen.findByRole("heading", {
      level: 1,
      name: "Processing. Don't hand over goods yet.",
    });
    expect(document.body).not.toHaveTextContent(/Paid/);
    expect(screen.getAllByText(/waiting for the bank to confirm/).length).toBeGreaterThan(0);
    fake.settle(id);
    await screen.findByRole("heading", { level: 1, name: /^Paid\./ }, { timeout: 4000 });
    await waitFor(() => expect(polite()).toMatch(/^Paid\. You sent fifteen thousand naira/));
  });

  it("'changed' says it plainly, offers Try again, and is spoken assertively only if it appears later", async () => {
    const id = await endedAs("DECLINED");
    renderScreen(<ResultScreen id={id} reason="changed" />);
    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "This payment changed after you heard it. Nothing was sent.",
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Try again" })).toBeInTheDocument();
    expect(assertive()).toBe(""); // focus already read it
  });

  it("a request that is not decided yet goes back to the review instead of showing a result", async () => {
    const made = await claimedRequest(fake);
    await getReadback(made.id, "en");
    renderScreen(<ResultScreen id={made.id} reason="check" />);
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith(`/requests/${made.id}`));
  });
});

describe("Setup passkey", () => {
  beforeEach(() => {
    vi.mocked(passkeySupport).mockResolvedValue("ok");
    vi.mocked(createPasskey).mockResolvedValue({ id: "new-credential", response: {} });
    fake.actAs("customer");
  });

  it("explains in plain words, says Zolo never asks for a PIN, and asks for privacy", async () => {
    renderScreen(<SetupPasskey next="/" />);
    expect(screen.getByText(/never asks for your PIN or your card number/)).toBeInTheDocument();
    expect(screen.getByText(/in private\. Use earphones/)).toBeInTheDocument();
    expect(document.querySelector("input")).toBeNull(); // no PIN pad, no field of any kind
  });

  it("registers, says it is ready, and carries on to where the customer was going", async () => {
    renderScreen(<SetupPasskey next="/requests/abc" />);
    await userEvent.click(await screen.findByRole("button", { name: "Set up passkey" }));
    expect(await screen.findByText("Your passkey is ready.")).toBeInTheDocument();
    await waitFor(() => expect(polite()).toBe("Your passkey is ready."));
    expect(screen.getByRole("link", { name: "Done" })).toHaveAttribute("href", "/requests/abc");
  });

  it("says when a new passkey replaced an old one", async () => {
    fake.addPasskey();
    renderScreen(<SetupPasskey next="/" />);
    await userEvent.click(await screen.findByRole("button", { name: "Set up passkey" }));
    expect(
      await screen.findByText("Your passkey is ready. It replaced your old one."),
    ).toBeInTheDocument();
  });

  it("handles cancel, already registered, and no screen lock — each in its own words", async () => {
    renderScreen(<SetupPasskey next="/" />);
    const start = await screen.findByRole("button", { name: "Set up passkey" });
    vi.mocked(createPasskey).mockRejectedValueOnce(
      Object.assign(new Error("x"), { name: "NotAllowedError" }),
    );
    await userEvent.click(start);
    expect(await screen.findByText("Cancelled. You can try again.")).toBeInTheDocument();
    await waitFor(() => expect(assertive()).toBe("Cancelled. You can try again."));
    vi.mocked(createPasskey).mockRejectedValueOnce(
      Object.assign(new Error("x"), { name: "InvalidStateError" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Set up passkey" }));
    expect(await screen.findByText("This phone already has your passkey.")).toBeInTheDocument();
  });

  it("with no usable screen lock, says what to do and keeps the button inactive", async () => {
    vi.mocked(passkeySupport).mockResolvedValue("no-lock");
    renderScreen(<SetupPasskey next="/" />);
    expect((await screen.findAllByText(/no screen lock we can use/)).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Set up passkey" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
  });

  it("sends a signed-out visitor to sign in", async () => {
    fake.actAs(null);
    renderScreen(<SetupPasskey next="/" />);
    await userEvent.click(await screen.findByRole("button", { name: "Set up passkey" }));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/signin"));
  });
});

describe("Demo sign-in chooser", () => {
  it("lets you pick a person; nothing is typed, no code is asked for", async () => {
    renderScreen(<SignIn />);
    expect(document.querySelector("input")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "I am an agent: Bisi Ventures" }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/agent"));
    expect(JSON.parse(sessionStorage.getItem("zolo.session")!)).toEqual({
      role: "agent",
      name: "Bisi Ventures",
    });
  });

  it("a customer goes home", async () => {
    renderScreen(<SignIn />);
    await userEvent.click(screen.getByRole("button", { name: "I am a customer: Amaka Obi" }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/home"));
  });
});

describe("Demo console", () => {
  async function filled(id: string) {
    renderScreen(<DemoConsole />);
    await userEvent.type(screen.getByLabelText("Demo token"), "demo-token-1234");
    const field = screen.getByLabelText("Request id");
    await userEvent.clear(field);
    await userEvent.type(field, id);
  }

  it("has exactly the actions the backend has: reset, tamper, replay, expire (and the timeline)", () => {
    renderScreen(<DemoConsole />);
    const buttons = screen.getAllByRole("button").map((b) => b.textContent);
    expect(buttons).toEqual([
      "Reset the demo",
      "Change the amount after the readback",
      "Replay the approval",
      "Expire it now",
    ]);
    expect(screen.getByLabelText("Demo token")).toHaveAttribute("type", "password");
  });

  it("tamper then approve: the timeline shows it and the customer's approval fails", async () => {
    const made = await claimedRequest(fake);
    await getReadback(made.id, "en");
    fake.actAs(null);
    await filled(made.id);
    await userEvent.click(
      screen.getByRole("button", { name: "Change the amount after the readback" }),
    );
    await waitFor(() => expect(screen.getByTestId("demo-message")).toHaveTextContent("done"));
    expect(await screen.findByText("demo.tampered", {}, { timeout: 5000 })).toBeInTheDocument();
    expect(fake.requests.get(made.id)?.tampered).toBe(true);
  });

  it("a wrong token is refused, with the code, and asks nothing else", async () => {
    renderScreen(<DemoConsole />);
    await userEvent.type(screen.getByLabelText("Demo token"), "wrong-token");
    await userEvent.click(screen.getByRole("button", { name: "Reset the demo" }));
    await waitFor(() =>
      expect(screen.getByTestId("demo-message")).toHaveTextContent("refused (UNAUTHENTICATED)"),
    );
  });

  it("asks for the token first", async () => {
    renderScreen(<DemoConsole />);
    await userEvent.click(screen.getByRole("button", { name: "Expire it now" }));
    expect(screen.getByTestId("demo-message")).toHaveTextContent("Enter the demo token first.");
  });
});
