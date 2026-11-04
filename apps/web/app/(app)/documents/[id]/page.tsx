import { notFound } from "next/navigation";
import { DocumentDetailView } from "@/components/core/document-detail";

const ULID = /^[0-9A-HJKMNP-TV-Z]{26}$/;

export default async function DocumentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!ULID.test(id)) notFound();
  return <DocumentDetailView id={id} />;
}
