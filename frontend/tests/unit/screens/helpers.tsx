import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { LiveRegionProvider } from "@/components/ui/LiveRegion";
import { createAgentRequest, claimByCode, getReadback } from "@/lib/api/endpoints";
import type { FakeBackend } from "../../fakes/fake-backend";

export const renderScreen = (ui: ReactElement) =>
  render(<LiveRegionProvider>{ui}</LiveRegionProvider>);

export const polite = () => document.querySelector("[data-live-region=polite]")?.textContent ?? "";
export const assertive = () =>
  document.querySelector("[data-live-region=assertive]")?.textContent ?? "";

let keys = 0;
/** An agent makes a request for `naira`; the customer claims it. Leaves the customer signed in. */
export async function claimedRequest(fake: FakeBackend, naira = 15_000) {
  fake.actAs("agent");
  const made = await createAgentRequest(naira * 100, `test-${(keys += 1)}`);
  fake.actAs("customer");
  await claimByCode(made.claim_code!);
  return made;
}

/** ...and has also heard it, so it can be approved. */
export async function heardRequest(fake: FakeBackend, naira = 15_000) {
  const made = await claimedRequest(fake, naira);
  await getReadback(made.id, "en");
  return made;
}
