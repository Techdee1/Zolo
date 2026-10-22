import { parseReason } from "@/lib/result-reason";
import { ResultScreen } from "./ResultScreen";

export const metadata = { title: "Result" };

export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ r?: string }>;
}) {
  const [{ id }, { r }] = await Promise.all([params, searchParams]);
  return <ResultScreen id={id} reason={parseReason(r)} />;
}
