import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { CallScreen } from "@/app/(app)/requests/[id]/call/CallScreen";
import { ReviewScreen } from "@/app/(app)/requests/[id]/ReviewScreen";
import { SetupPhone } from "@/app/(app)/setup/phone/SetupPhone";
import { router } from "../router";
import { installFakeBackend } from "../fake-server";
import { claimedRequest, renderScreen } from "./helpers";

const fake = installFakeBackend();

describe("Phone-call approval", () => {
  it("is invisible while the feature is off: no offer on the review screen", async () => {
    const made = await claimedRequest(fake);
    renderScreen(<ReviewScreen id={made.id} />);
    await screen.findByRole("heading", { level: 2, name: "What Zolo says" });
    expect(screen.queryByText(/phone call instead/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/set up phone approval/i)).not.toBeInTheDocument();
  });

  it("offers to set it up when on but not enrolled, and to call when enrolled", async () => {
    const made = await claimedRequest(fake);
    fake.setPhone(true, false);
    const first = renderScreen(<ReviewScreen id={made.id} />);
    const setup = await screen.findByRole("link", { name: "Set up phone approval" });
    expect(setup).toHaveAttribute("href", expect.stringContaining("/setup/phone?next="));
    first.unmount();

    fake.setPhone(true, true);
    renderScreen(<ReviewScreen id={made.id} />);
    const call = await screen.findByRole("link", { name: "Approve by phone call instead" });
    expect(call).toHaveAttribute("href", `/requests/${made.id}/call`);
    expect(screen.getByText(/up to ₦20,000/)).toBeInTheDocument();
  });

  it("sets up a number and a PIN, and refuses an easy PIN", async () => {
    fake.actAs("customer");
    fake.setPhone(true);
    renderScreen(<SetupPhone next="/home" />);
    await userEvent.type(screen.getByLabelText(/number Zolo should ring/i), "+2348055550142");
    await userEvent.type(screen.getByLabelText(/four digit Zolo PIN/i), "1234");
    await userEvent.click(screen.getByRole("button", { name: "Save phone approval" }));
    expect(await screen.findByText("Choose a PIN that is harder to guess.")).toBeInTheDocument();

    await userEvent.clear(screen.getByLabelText(/four digit Zolo PIN/i));
    await userEvent.type(screen.getByLabelText(/four digit Zolo PIN/i), "7391");
    await userEvent.click(screen.getByRole("button", { name: "Save phone approval" }));
    expect(await screen.findByText("Phone approval is ready.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Done" })).toHaveAttribute("href", "/home");
  });

  it("says plainly that the PIN is not a bank PIN", () => {
    fake.setPhone(true);
    renderScreen(<SetupPhone next="/home" />);
    expect(screen.getByText(/never your bank PIN or your card PIN/i)).toBeInTheDocument();
  });

  it("rings first and only starts the call when it is answered", async () => {
    const made = await claimedRequest(fake);
    fake.setPhone(true, true);
    renderScreen(<CallScreen id={made.id} />);
    expect(screen.getByRole("heading", { level: 1, name: "Zolo is calling you" })).toBeVisible();
    expect(screen.queryByText(/someone has asked/i)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Answer" }));
    expect(await screen.findByText(/Someone has asked for a payment/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Approve/ })).toBeInTheDocument();
  });

  it("approves only after 1 and the typed PIN, then goes to the result", async () => {
    const made = await claimedRequest(fake);
    fake.setPhone(true, true);
    renderScreen(<CallScreen id={made.id} />);
    await userEvent.click(screen.getByRole("button", { name: "Answer" }));
    await userEvent.click(await screen.findByRole("button", { name: /Approve/ }));
    const pin = await screen.findByLabelText("Type your four digit Zolo PIN");
    expect(screen.getByRole("button", { name: "Send PIN" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(router.replace).not.toHaveBeenCalled();
    await userEvent.type(pin, "7391");
    await userEvent.click(screen.getByRole("button", { name: "Send PIN" }));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith(`/requests/${made.id}/result`));
    expect(fake.requests.get(made.id)?.state).toBe("SETTLED");
  });

  it("a wrong PIN ends the call and sends nothing", async () => {
    const made = await claimedRequest(fake);
    fake.setPhone(true, true);
    renderScreen(<CallScreen id={made.id} />);
    await userEvent.click(screen.getByRole("button", { name: "Answer" }));
    await userEvent.click(await screen.findByRole("button", { name: /Approve/ }));
    await userEvent.type(await screen.findByLabelText(/four digit Zolo PIN/), "1111");
    await userEvent.click(screen.getByRole("button", { name: "Send PIN" }));
    expect(await screen.findByText("That PIN was wrong.")).toBeInTheDocument();
    expect(fake.requests.get(made.id)?.state).not.toBe("SETTLED");
  });

  it("Decline on the keypad declines", async () => {
    const made = await claimedRequest(fake);
    fake.setPhone(true, true);
    renderScreen(<CallScreen id={made.id} />);
    await userEvent.click(screen.getByRole("button", { name: "Answer" }));
    await userEvent.click(await screen.findByRole("button", { name: /Decline/ }));
    await waitFor(() => expect(fake.requests.get(made.id)?.state).toBe("DECLINED"));
  });

  it("not enrolled: says so and offers the passkey, never a call", async () => {
    const made = await claimedRequest(fake);
    fake.setPhone(true, false);
    renderScreen(<CallScreen id={made.id} />);
    await userEvent.click(screen.getByRole("button", { name: "Answer" }));
    expect(await screen.findByText("Set up phone approval first.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Use my passkey instead" })).toBeInTheDocument();
  });
});
