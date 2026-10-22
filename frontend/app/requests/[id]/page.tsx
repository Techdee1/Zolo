import { ReviewScreen } from "./ReviewScreen";

export const metadata = { title: "Review the request" };

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ReviewScreen id={id} />;
}
