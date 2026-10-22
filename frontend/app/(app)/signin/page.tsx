import { safeNext } from "@/lib/session-hint";
import { SignIn } from "./SignIn";

export const metadata = { title: "Choose who you are" };

export default async function Page({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const { next } = await searchParams;
  return <SignIn next={next ? safeNext(next) : undefined} />;
}
