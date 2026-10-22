import { notFound } from "next/navigation";
import { env } from "@/lib/env";
import { DemoConsole } from "./DemoConsole";

export const metadata = { title: "Demo console" };

/** For the stage demo only: off unless NEXT_PUBLIC_FEATURE_DEMO=true, and never linked from the app. */
export default function Page() {
  if (!env.featureDemo) notFound();
  return <DemoConsole />;
}
