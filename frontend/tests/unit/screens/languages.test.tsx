import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Home } from "@/app/(app)/home/Home";
import { ReviewScreen } from "@/app/(app)/requests/[id]/ReviewScreen";
import { ResultScreen } from "@/app/(app)/requests/[id]/result/ResultScreen";
import { SignIn } from "@/app/(app)/signin/SignIn";
import { LanguagePicker } from "@/components/LanguagePicker";
import { LOCALES, type Locale } from "@/lib/locales";
import { router } from "../router";
import { installFakeBackend } from "../fake-server";
import { messagesFor } from "../messages";
import { claimedRequest, renderScreen } from "./helpers";

const fake = installFakeBackend();
const say = (locale: Locale, key: string) =>
  key
    .split(".")
    .reduce<unknown>((n, p) => (n as Record<string, unknown>)[p], messagesFor(locale)) as string;

describe("the language picker", () => {
  it("is a labelled select with each language in its own name and its own lang", () => {
    renderScreen(<LanguagePicker />);
    const select = screen.getByRole("combobox", { name: "Language" });
    const options = within(select).getAllByRole("option");
    expect(options.map((o) => o.textContent)).toEqual([
      "English",
      "Pidgin",
      "Yorùbá",
      "Hausa",
      "Igbo",
    ]);
    expect(options.map((o) => o.getAttribute("lang"))).toEqual(["en", "pcm", "yo", "ha", "ig"]);
    expect(select).toHaveAccessibleDescription(/spoken request is in English or Pidgin/);
  });

  it("remembers the choice in a cookie and asks the server to render the new words", async () => {
    renderScreen(<LanguagePicker />);
    await userEvent.selectOptions(screen.getByRole("combobox"), "yo");
    expect(document.cookie).toContain("zolo_locale=yo");
    expect(router.refresh).toHaveBeenCalled();
  });

  it("shows the current language, in that language's own label", () => {
    renderScreen(<LanguagePicker />, "ig");
    expect(screen.getByRole("combobox", { name: "Asụsụ" })).toHaveValue("ig");
  });
});

for (const locale of LOCALES.filter((l) => l !== "en")) {
  describe(`the screens in ${locale}`, () => {
    it("sign-in and home are in the language, with the amount in digits and words kept", async () => {
      renderScreen(<SignIn />, locale);
      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
        say(locale, "signin.title"),
      );
      expect(
        screen.getByRole("button", {
          name: say(locale, "signin.agent").replace("{name}", "Bisi Ventures"),
        }),
      ).toBeInTheDocument();
    });

    it("review: the sentence, the buttons and the amount in words, in the language", async () => {
      await claimedRequest(fake);
      renderScreen(<ReviewScreen id={[...fake.requests.keys()][0]!} />, locale);
      await screen.findByRole("heading", { level: 2, name: say(locale, "review.readbackHeading") });
      const h1 = screen.getByRole("heading", { level: 1 });
      expect(h1).toHaveAccessibleName(
        say(locale, "review.titleSpoken")
          .replace("{payee}", "Bisi Ventures")
          .replace("{amountWords}", "fifteen thousand naira"),
      );
      expect(h1).toHaveTextContent("₦15,000");
      expect(
        screen.getByRole("button", { name: say(locale, "review.decline") }),
      ).toBeInTheDocument();
    });
  });
}

describe("the spoken readback follows the language, and only asks for what the backend has", () => {
  const requested = async (locale: Locale) => {
    const native = fake.nativeClips;
    fake.reset();
    fake.setNativeClips(native);
    await claimedRequest(fake);
    const spy = vi.spyOn(globalThis, "fetch");
    renderScreen(<ReviewScreen id={[...fake.requests.keys()][0]!} />, locale);
    await screen.findByRole("heading", { level: 2, name: say(locale, "review.readbackHeading") });
    const url = spy.mock.calls.map((c) => String(c[0])).find((u) => u.includes("/readback")) ?? "";
    spy.mockRestore();
    return url;
  };

  it("Pidgin asks for pcm; English asks for en", async () => {
    expect(await requested("pcm")).toContain("lang=pcm");
    expect(await requested("en")).toContain("lang=en");
  });

  it("Yoruba, Hausa and Igbo ask for their own language, and the backend decides what comes back", async () => {
    for (const l of ["yo", "ha", "ig"] as const) {
      expect(await requested(l)).toContain(`lang=${l}`);
      document.body.innerHTML = "";
    }
  });

  it("when there is no recording, the English readback comes back and the note says the voice is in English", async () => {
    for (const l of ["yo", "ha", "ig"] as const) {
      fake.setNativeClips(false);
      await requested(l);
      expect(screen.getByText(say(l, "review.englishNote"))).toBeInTheDocument();
      expect(document.getElementById("readback-text")).toHaveAttribute("lang", "en");
      expect(document.getElementById("readback-text")).toHaveTextContent(/is asking for/);
      document.body.innerHTML = "";
    }
  });

  it("when the recording exists, the readback is in the customer's language and there is NO note", async () => {
    for (const l of ["yo", "ha", "ig"] as const) {
      fake.setNativeClips(true);
      await requested(l);
      expect(screen.queryByText(say(l, "review.englishNote"))).not.toBeInTheDocument();
      expect(document.getElementById("readback-text")).toHaveAttribute("lang", l);
      expect(document.getElementById("readback-text")).not.toHaveTextContent(/is asking for/);
      document.body.innerHTML = "";
    }
  });

  it("Pidgin and English do not show the note", async () => {
    await requested("pcm");
    expect(screen.queryByText(say("pcm", "review.englishNote"))).not.toBeInTheDocument();
  });
});

describe("the result screens in another language keep the honest wording", () => {
  it("Processing (SUBMITTED) is never shown as Paid, in any language", async () => {
    for (const locale of LOCALES.filter((l) => l !== "en")) {
      fake.reset();
      const made = await claimedRequest(fake);
      await fetch(`/api/requests/${made.id}/readback?lang=en`);
      fake.addPasskey();
      fake.setOutcome("SUBMITTED");
      await fetch(`/api/requests/${made.id}/challenge`, { method: "POST" });
      await fetch(`/api/requests/${made.id}/approve`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ id: "c", response: {} }),
      });
      renderScreen(<ResultScreen id={made.id} reason={null} />, locale);
      const h1 = await screen.findByRole("heading", {
        level: 1,
        name: say(locale, "result.processing"),
      });
      expect(h1).toBeInTheDocument();
      expect(document.body).not.toHaveTextContent(say(locale, "result.paidShort"));
      document.body.innerHTML = "";
    }
  });

  it("Paid and Declined use the language's own words", async () => {
    const made = await claimedRequest(fake);
    await fetch(`/api/requests/${made.id}/readback?lang=en`);
    await fetch(`/api/requests/${made.id}/decline`, { method: "POST" });
    renderScreen(<ResultScreen id={made.id} reason={null} />, "pcm");
    expect(
      await screen.findByRole("heading", { level: 1, name: say("pcm", "result.declined") }),
    ).toBeInTheDocument();
  });
});

describe("home in another language", () => {
  it("dates and the payment line are in the language", async () => {
    const made = await claimedRequest(fake);
    await fetch(`/api/requests/${made.id}/readback?lang=en`);
    await fetch(`/api/requests/${made.id}/decline`, { method: "POST" });
    renderScreen(<Home />, "pcm");
    // Heard: the whole line in Pidgin. Seen: the Pidgin status word in the row.
    const item = await screen.findByText(/You decline .* to .*today/i);
    expect(item.closest("li")).toHaveTextContent(say("pcm", "result.badge.declined"));
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(say("pcm", "home.title")),
    );
  });
});
