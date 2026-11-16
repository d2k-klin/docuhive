import { GuestDocuments } from "@/components/core/guest-documents";

export const metadata = {
  referrer: "no-referrer",
  robots: "noindex, nofollow",
};

export default async function GuestPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  return <GuestDocuments token={token} />;
}
