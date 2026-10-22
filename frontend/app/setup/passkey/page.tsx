import { safeNext } from "@/lib/session-hint";
import { SetupPasskey } from "./SetupPasskey";

export const metadata = { title: "Set up your passkey" };

export default async function Page({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const { next } = await searchParams;
  return <SetupPasskey next={safeNext(next)} />;
}
