import { CallScreen } from "./CallScreen";

export const metadata = { title: "Phone call" };

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <CallScreen id={id} />;
}
