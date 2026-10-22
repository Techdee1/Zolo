import { AgentWaiting } from "./AgentWaiting";

export const metadata = { title: "Waiting for the customer" };

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <AgentWaiting id={id} />;
}
