import { PayCode } from "../pay/code/PayCode";

export const metadata = { title: "Pay an agent" };

/**
 * Where the agent's QR points (`/claim?code=1234`, built by the backend). It is the pay-by-code
 * screen with the code already in it. Anything that is not exactly 4 digits is ignored, and the
 * customer types the code instead.
 */
export default async function Page({ searchParams }: { searchParams: Promise<{ code?: string }> }) {
  const { code } = await searchParams;
  return <PayCode initialCode={code && /^\d{4}$/.test(code) ? code : undefined} />;
}
