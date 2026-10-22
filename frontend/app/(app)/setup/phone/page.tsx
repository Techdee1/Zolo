import { safeNext } from "@/lib/session-hint";
import { SetupPhone } from "./SetupPhone";

export const metadata = { title: "Set up phone approval" };

export default async function Page({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const { next } = await searchParams;
  return <SetupPhone next={safeNext(next)} />;
}
