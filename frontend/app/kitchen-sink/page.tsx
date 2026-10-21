import { notFound } from "next/navigation";
import { env } from "@/lib/env";
import { KitchenSink } from "./KitchenSink";

export const metadata = { title: "Component gallery" };

/** A developer gallery of every UI component. Off unless NEXT_PUBLIC_FEATURE_KITCHEN_SINK=true. */
export default function Page() {
  if (!env.featureKitchenSink) notFound();
  return <KitchenSink />;
}
