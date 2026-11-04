import { notFound, redirect } from "next/navigation";
import { DocumentDetailView } from "@/components/core/document-detail";
import { serverClient } from "@/lib/api/server";

const ULID = /^[0-9A-HJKMNP-TV-Z]{26}$/;

export default async function DocumentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!ULID.test(id)) notFound();
  const me = await (await serverClient()).GET("/api/auth/me").catch(() => null);
  if (!me?.data) redirect("/login");
  return <DocumentDetailView id={id} viewerId={me.data.id} />;
}
