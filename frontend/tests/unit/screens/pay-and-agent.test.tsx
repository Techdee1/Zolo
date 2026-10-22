import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { AgentNewRequest } from "@/app/(app)/agent/AgentNewRequest";
import { AgentWaiting } from "@/app/(app)/agent/requests/[id]/AgentWaiting";
import { PayCode } from "@/app/(app)/pay/code/PayCode";
import { createAgentRequest, claimByCode } from "@/lib/api/endpoints";
import { setAgentRequest } from "@/lib/session-hint";
import { router } from "../router";
import { installFakeBackend } from "../fake-server";
import { assertive, polite, renderScreen } from "./helpers";

const fake = installFakeBackend();

describe("Pay an agent", () => {
  it("is a labelled numeric field (system keyboard), not a PIN pad, and submits on the 4th digit", async () => {
    fake.actAs("agent");
    const made = await createAgentRequest(1_500_000, "k");
    fake.actAs("customer");
    renderScreen(<PayCode />);
    const field = screen.getByRole("textbox", { name: /4-digit code/ });
    expect(field).toHaveAttribute("inputmode", "numeric");
    expect(field).toHaveAttribute("type", "text"); // not masked: it is not a secret
    await userEvent.type(field, made.claim_code!.slice(0, 3));
    expect(router.push).not.toHaveBeenCalled();
    await userEvent.type(field, made.claim_code!.slice(3));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith(`/requests/${made.id}`));
  });

  it("says specifically that no request has that code, and speaks it assertively", async () => {
    fake.actAs("customer");
    renderScreen(<PayCode />);
    await userEvent.type(screen.getByRole("textbox"), "9999");
    expect(await screen.findByText(/No request has that code/)).toBeInTheDocument();
    await waitFor(() => expect(assertive()).toMatch(/No request has that code/));
    expect(screen.getByRole("textbox")).toHaveAttribute("aria-invalid", "true");
  });

  it("says specifically that the code expired", async () => {
    fake.actAs("agent");
    const made = await createAgentRequest(1_500_000, "k");
    fake.handle({
      method: "POST",
      path: `/demo/requests/${made.id}/expire`,
      headers: { "x-demo-token": "demo-token-1234" },
    });
    fake.actAs("customer");
    renderScreen(<PayCode />);
    await userEvent.type(screen.getByRole("textbox"), made.claim_code!);
    expect(await screen.findByText(/That code has expired/)).toBeInTheDocument();
  });

  it("from the agent's QR (/claim?code=…): starts filled in and claims once, with no typing", async () => {
    fake.actAs("agent");
    const made = await createAgentRequest(1_500_000, "k");
    fake.actAs("customer");
    renderScreen(<PayCode initialCode={made.claim_code!} />);
    expect(screen.getByRole("textbox")).toHaveValue(made.claim_code);
    await waitFor(() => expect(router.push).toHaveBeenCalledWith(`/requests/${made.id}`));
    expect(router.push).toHaveBeenCalledTimes(1);
  });

  it("from the QR while signed out: sends you to sign in, and back to this code after", async () => {
    fake.actAs(null);
    renderScreen(<PayCode initialCode="1234" />);
    await waitFor(() =>
      expect(router.replace).toHaveBeenCalledWith(
        `/signin?next=${encodeURIComponent("/claim?code=1234")}`,
      ),
    );
  });

  it("ignores anything that is not a digit and never takes more than 4", async () => {
    fake.actAs("customer");
    renderScreen(<PayCode />);
    const field = screen.getByRole("textbox");
    await userEvent.type(field, "1a2");
    expect(field).toHaveValue("12");
  });
});

describe("Agent: new request", () => {
  it("types an amount on the keypad, shows it with words, and the request button names it", async () => {
    fake.actAs("agent");
    renderScreen(<AgentNewRequest />);
    const request = () => screen.getByRole("button", { name: /^Request/ });
    expect(request()).toHaveAttribute("aria-disabled", "true");
    const keypad = screen.getByRole("group", { name: "Amount keypad" });
    for (const d of ["1", "5", "0", "0", "0"])
      await userEvent.click(within(keypad).getByRole("button", { name: d }));
    expect(screen.getByText("fifteen thousand naira")).toBeInTheDocument();
    expect(request()).toHaveAccessibleName("Request fifteen thousand naira");
    expect(request()).toHaveTextContent("Request ₦15,000");
    expect(request()).not.toHaveAttribute("aria-disabled");
  });

  it("quick chips set the amount", async () => {
    fake.actAs("agent");
    renderScreen(<AgentNewRequest />);
    await userEvent.click(
      screen.getByRole("button", { name: "Set the amount to ten thousand naira" }),
    );
    expect(screen.getByText("ten thousand naira")).toBeInTheDocument();
  });

  it("creates the request in integer kobo, remembers the code, and goes to the waiting page", async () => {
    fake.actAs("agent");
    renderScreen(<AgentNewRequest />);
    await userEvent.click(
      screen.getByRole("button", { name: "Set the amount to five thousand naira" }),
    );
    await userEvent.click(screen.getByRole("button", { name: /^Request/ }));
    await waitFor(() => expect(router.push).toHaveBeenCalled());
    const id = [...fake.requests.keys()][0]!;
    expect(fake.requests.get(id)?.amount).toBe(500_000);
    expect(router.push).toHaveBeenCalledWith(`/agent/requests/${id}`);
    expect(JSON.parse(sessionStorage.getItem(`zolo.agent-request.${id}`)!).claim_code).toMatch(
      /^\d{4}$/,
    );
  });

  it("announces the whole amount once typing stops, so a blind agent can check it", async () => {
    fake.actAs("agent");
    renderScreen(<AgentNewRequest />);
    await userEvent.click(
      screen.getByRole("button", { name: "Set the amount to twenty thousand naira" }),
    );
    await waitFor(() => expect(polite()).toBe("Amount: twenty thousand naira"));
  });

  it("sends a signed-out agent to the sign-in chooser", async () => {
    renderScreen(<AgentNewRequest />);
    await userEvent.click(
      screen.getByRole("button", { name: "Set the amount to five thousand naira" }),
    );
    await userEvent.click(screen.getByRole("button", { name: /^Request/ }));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/signin"));
  });
});

describe("Agent: waiting", () => {
  async function waitingFor(naira = 15_000) {
    fake.actAs("agent");
    const made = await createAgentRequest(naira * 100, `w-${naira}`);
    setAgentRequest(made);
    return made;
  }

  it("shows the code digit by digit, hides the QR from screen readers, and says to wait for Paid", async () => {
    const made = await waitingFor();
    renderScreen(<AgentWaiting id={made.id} />);
    const code = await screen.findByRole("img", { name: /^Code: / });
    expect(code).toHaveAccessibleName(`Code: ${[...made.claim_code!].join(", ")}`);
    expect(screen.getByText("Give cash only after you see Paid.")).toBeInTheDocument();
    expect(document.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });

  it("while the bank has not confirmed (SUBMITTED) says Processing, never Paid, and keeps polling until it settles", async () => {
    const made = await waitingFor();
    fake.actAs("customer");
    await claimByCode(made.claim_code!);
    fake.setOutcome("SUBMITTED");
    await heardApprove(made.id);
    fake.actAs("agent");
    renderScreen(<AgentWaiting id={made.id} />);
    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Processing. Don't hand over goods yet.",
      }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/^Paid$/)).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(/give the cash/i);
    await waitFor(() => expect(polite()).toBe("Processing. Don't hand over goods yet."));
    fake.settle(made.id);
    expect(
      await screen.findByRole("heading", { level: 1, name: "Paid" }, { timeout: 4000 }),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(polite()).toMatch(/^Paid\. fifteen thousand naira from the customer/),
    );
  });

  it("shows Declined and Expired plainly, with a way to start again", async () => {
    const made = await waitingFor();
    fake.handle({
      method: "POST",
      path: `/demo/requests/${made.id}/expire`,
      headers: { "x-demo-token": "demo-token-1234" },
    });
    renderScreen(<AgentWaiting id={made.id} />);
    expect(await screen.findByRole("heading", { level: 1, name: /expired/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "New request" })).toHaveAttribute("href", "/agent");
  });

  it("after a reload the code is gone: it says so instead of showing a stale one", async () => {
    const made = await waitingFor();
    sessionStorage.clear();
    renderScreen(<AgentWaiting id={made.id} />);
    expect(await screen.findByText(/no longer on this screen/)).toBeInTheDocument();
  });
});

async function heardApprove(id: string) {
  fake.addPasskey();
  await fetch(`/api/requests/${id}/readback?lang=en`);
  await fetch(`/api/requests/${id}/challenge`, { method: "POST" });
  await fetch(`/api/requests/${id}/approve`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ id: "c", response: {} }),
  });
}
