import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ReviewScreen } from "@/app/(app)/requests/[id]/ReviewScreen";
import { signWithPasskey } from "@/lib/passkeys";
import { router } from "../router";
import { installFakeBackend } from "../fake-server";
import { assertive, claimedRequest, polite, renderScreen } from "./helpers";

vi.mock("@/lib/passkeys", async (orig) => ({
  ...(await orig<typeof import("@/lib/passkeys")>()),
  signWithPasskey: vi.fn(),
}));

const fake = installFakeBackend();
const sign = vi.mocked(signWithPasskey);
/** The readback has arrived (until then the screen shows a loading heading). */
const ready = async () => {
  await screen.findByRole("heading", { level: 2, name: "What Zolo says" });
  return screen.getByRole("heading", { level: 1 });
};
const approveButton = () => screen.getByRole("button", { name: /^Approve/ });

/** A stand-in for the browser's Audio, so a test can start, finish and refuse playback. */
class FakeAudio {
  static last: FakeAudio | null = null;
  static refuse = false;
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  currentTime = 0;
  constructor(public src: string) {
    FakeAudio.last = this;
  }
  play = vi.fn(() =>
    FakeAudio.refuse
      ? Promise.reject(new DOMException("blocked", "NotAllowedError"))
      : Promise.resolve(),
  );
  pause = vi.fn();
}

beforeEach(() => {
  FakeAudio.last = null;
  FakeAudio.refuse = false;
  localStorage.clear();
  fake.addPasskey();
  sign.mockResolvedValue({ id: "c", response: { signature: "s" } });
});

describe("Review and approve: with no pre-rendered audio (screen reader reads it)", () => {
  it("shows who is asking, the amount first, in words, the bank, and the verified badge — all from the API", async () => {
    await claimedRequest(fake);
    renderScreen(<ReviewScreen id={[...fake.requests.keys()][0]!} />);
    const h1 = await ready();
    expect(h1).toHaveAccessibleName("Bisi Ventures is asking for fifteen thousand naira");
    expect(h1).toHaveTextContent("Bisi Ventures is asking for ₦15,000");
    expect(screen.getByText("Verified by bank")).toBeInTheDocument();
    expect(screen.getByText("fifteen thousand naira")).toBeInTheDocument();
    expect(
      screen.getByText(
        /Bisi Ventures is asking for fifteen thousand naira\. One five, zero zero zero\./,
      ),
    ).toBeInTheDocument();
    expect(approveButton()).toHaveAccessibleName("Approve fifteen thousand naira to Bisi Ventures");
  });

  it("asks the backend for the readback in English or Pidgin only", async () => {
    await claimedRequest(fake);
    const spy = vi.spyOn(globalThis, "fetch");
    renderScreen(<ReviewScreen id={[...fake.requests.keys()][0]!} />);
    await ready();
    const urls = spy.mock.calls.map((c) => String(c[0]));
    expect(urls.some((u) => u.includes("/readback?lang=en"))).toBe(true);
    expect(urls.some((u) => /lang=(yo|ha|ig)/.test(u))).toBe(false);
  });

  it("keeps Approve inactive, with the reason, until the readback has been heard; focus goes to the readback", async () => {
    await claimedRequest(fake);
    renderScreen(<ReviewScreen id={[...fake.requests.keys()][0]!} />);
    await ready();
    expect(approveButton()).toHaveAttribute("aria-disabled", "true");
    expect(approveButton()).toHaveAccessibleDescription("Listen to the request first.");
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 2, name: "What Zolo says" })).toHaveFocus(),
    );
    await userEvent.click(approveButton());
    expect(sign).not.toHaveBeenCalled();
    await waitFor(() => expect(approveButton()).not.toHaveAttribute("aria-disabled"), {
      timeout: 4000,
    });
  });

  it("does not take focus to the h1: the readback gets it, so nothing talks over anything", async () => {
    await claimedRequest(fake);
    renderScreen(<ReviewScreen id={[...fake.requests.keys()][0]!} />);
    const h1 = await ready();
    expect(h1).not.toHaveFocus();
  });

  it("approves with the passkey: challenge, assertion, then the result page", async () => {
    await claimedRequest(fake);
    const id = [...fake.requests.keys()][0]!;
    renderScreen(<ReviewScreen id={id} />);
    await ready();
    await waitFor(() => expect(approveButton()).not.toHaveAttribute("aria-disabled"), {
      timeout: 4000,
    });
    await userEvent.click(approveButton());
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith(`/requests/${id}/result`));
    expect(sign).toHaveBeenCalledWith(expect.objectContaining({ rpId: "localhost" }));
    expect(fake.requests.get(id)?.state).toBe("SETTLED");
  });

  it("when the bank has not confirmed, the result page is where it shows (SUBMITTED, not Paid)", async () => {
    fake.setOutcome("SUBMITTED");
    await claimedRequest(fake);
    const id = [...fake.requests.keys()][0]!;
    renderScreen(<ReviewScreen id={id} />);
    await ready();
    await waitFor(() => expect(approveButton()).not.toHaveAttribute("aria-disabled"), {
      timeout: 4000,
    });
    await userEvent.click(approveButton());
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith(`/requests/${id}/result`));
    expect(fake.requests.get(id)?.state).toBe("SUBMITTED");
  });

  it("cancelling the passkey prompt sends nothing and says so", async () => {
    sign.mockRejectedValue(Object.assign(new Error("cancelled"), { name: "NotAllowedError" }));
    await claimedRequest(fake);
    const id = [...fake.requests.keys()][0]!;
    renderScreen(<ReviewScreen id={id} />);
    await ready();
    await waitFor(() => expect(approveButton()).not.toHaveAttribute("aria-disabled"), {
      timeout: 4000,
    });
    await userEvent.click(approveButton());
    expect(
      await screen.findByText("Cancelled. Nothing was sent. You can try again."),
    ).toBeInTheDocument();
    await waitFor(() => expect(assertive()).toMatch(/Cancelled/));
    expect(fake.requests.get(id)?.state).toBe("READ_BACK");
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("an amount changed after the readback ends on the 'changed' result and nothing is sent", async () => {
    await claimedRequest(fake);
    const id = [...fake.requests.keys()][0]!;
    renderScreen(<ReviewScreen id={id} />);
    await ready();
    await waitFor(() => expect(approveButton()).not.toHaveAttribute("aria-disabled"), {
      timeout: 4000,
    });
    fake.handle({
      method: "POST",
      path: `/demo/requests/${id}/tamper`,
      headers: { "x-demo-token": "demo-token-1234" },
      body: {},
    });
    await userEvent.click(approveButton());
    await waitFor(() =>
      expect(router.replace).toHaveBeenCalledWith(`/requests/${id}/result?r=changed`),
    );
    expect(fake.requests.get(id)?.state).toBe("READ_BACK");
  });

  it("a customer with no passkey is taken to set one up, then back", async () => {
    fake.reset();
    await claimedRequest(fake);
    const id = [...fake.requests.keys()][0]!;
    renderScreen(<ReviewScreen id={id} />);
    await ready();
    await waitFor(() => expect(approveButton()).not.toHaveAttribute("aria-disabled"), {
      timeout: 4000,
    });
    await userEvent.click(approveButton());
    await waitFor(() =>
      expect(router.push).toHaveBeenCalledWith(
        `/setup/passkey?next=${encodeURIComponent(`/requests/${id}`)}`,
      ),
    );
  });

  it("declines in one tap with no confirmation, and says nothing was sent", async () => {
    await claimedRequest(fake);
    const id = [...fake.requests.keys()][0]!;
    renderScreen(<ReviewScreen id={id} />);
    await ready();
    await userEvent.click(screen.getByRole("button", { name: "Decline" }));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith(`/requests/${id}/result`));
    expect(fake.requests.get(id)?.state).toBe("DECLINED");
    await waitFor(() => expect(polite()).toBe("Declined. Nothing was sent."));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("a request tampered with before it is read goes straight to 'changed'", async () => {
    await claimedRequest(fake);
    const id = [...fake.requests.keys()][0]!;
    await fetch(`/api/requests/${id}/readback?lang=en`);
    fake.handle({
      method: "POST",
      path: `/demo/requests/${id}/tamper`,
      headers: { "x-demo-token": "demo-token-1234" },
      body: {},
    });
    renderScreen(<ReviewScreen id={id} />);
    await waitFor(() =>
      expect(router.replace).toHaveBeenCalledWith(`/requests/${id}/result?r=changed`),
    );
  });

  it("remembers 'screen reader only' for next time", async () => {
    await claimedRequest(fake);
    renderScreen(<ReviewScreen id={[...fake.requests.keys()][0]!} />);
    await ready();
    await userEvent.click(screen.getByRole("button", { name: "Use my screen reader only" }));
    expect(localStorage.getItem("zolo.readback-mode")).toBe("reader");
    expect(screen.getByRole("button", { name: "Use Zolo's voice" })).toBeInTheDocument();
  });
});

describe("Review and approve: with Zolo's voice", () => {
  beforeEach(() => {
    vi.stubGlobal("Audio", FakeAudio);
    fake.setAudio("/voice/audio/abc.mp3");
  });

  it("plays the clip from our own origin, and Approve waits until it has ended; then focus moves to the readback", async () => {
    await claimedRequest(fake);
    renderScreen(<ReviewScreen id={[...fake.requests.keys()][0]!} />);
    await ready();
    await waitFor(() => expect(FakeAudio.last?.play).toHaveBeenCalled());
    expect(FakeAudio.last?.src).toBe("/api/voice/audio/abc.mp3");
    expect(approveButton()).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("heading", { level: 2, name: "What Zolo says" })).not.toHaveFocus();
    act(() => FakeAudio.last?.onended?.());
    expect(approveButton()).not.toHaveAttribute("aria-disabled");
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 2, name: "What Zolo says" })).toHaveFocus(),
    );
  });

  it("says nothing through the live region while Zolo speaks, then catches up", async () => {
    await claimedRequest(fake);
    renderScreen(<ReviewScreen id={[...fake.requests.keys()][0]!} />);
    await ready();
    await waitFor(() => expect(FakeAudio.last?.play).toHaveBeenCalled());
    await userEvent.click(screen.getByRole("button", { name: "Decline" })); // announces "Declined..." while audio plays? it is held
    await waitFor(() => expect(router.replace).toHaveBeenCalled());
    expect(polite()).toBe("");
  });

  it("if the browser blocks sound, offers a tap to hear it; Approve still waits", async () => {
    FakeAudio.refuse = true;
    await claimedRequest(fake);
    renderScreen(<ReviewScreen id={[...fake.requests.keys()][0]!} />);
    const hear = await screen.findByRole("button", { name: "Hear the request" });
    expect(screen.getByText("Tap to hear the request.")).toBeInTheDocument();
    expect(approveButton()).toHaveAttribute("aria-disabled", "true");
    FakeAudio.refuse = false;
    await userEvent.click(hear);
    act(() => FakeAudio.last?.onended?.());
    expect(approveButton()).not.toHaveAttribute("aria-disabled");
  });

  it("if the clip fails to load, falls back to reading it (never leaves Approve stuck)", async () => {
    await claimedRequest(fake);
    renderScreen(<ReviewScreen id={[...fake.requests.keys()][0]!} />);
    await ready();
    await waitFor(() => expect(FakeAudio.last).not.toBeNull());
    act(() => FakeAudio.last?.onerror?.());
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 2, name: "What Zolo says" })).toHaveFocus(),
    );
    await waitFor(() => expect(approveButton()).not.toHaveAttribute("aria-disabled"), {
      timeout: 4000,
    });
  });

  it("only plays clips the backend rendered, never another address", async () => {
    fake.setAudio("https://evil.example/x.mp3");
    await claimedRequest(fake);
    renderScreen(<ReviewScreen id={[...fake.requests.keys()][0]!} />);
    await ready();
    expect(FakeAudio.last).toBeNull();
  });
});
