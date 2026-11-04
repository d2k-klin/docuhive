import { notFound } from "next/navigation";
import { ViewDocuments } from "@/components/core/view-documents";
import { serverClient } from "@/lib/api/server";

export default async function ViewPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const id = Number((await params).id);
  if (!Number.isInteger(id) || id < 1) notFound();
  const api = await serverClient();
  const path = { params: { path: { view_id: id } } };
  const [view, documents] = await Promise.all([
    api.GET("/api/views/{view_id}", path).catch(() => null),
    api.GET("/api/views/{view_id}/documents", path).catch(() => null),
  ]);
  if (view?.response.status === 404) notFound();
  if (!view?.data) throw new Error("The saved view could not be loaded.");
  return <ViewDocuments view={view.data} initial={documents?.data || null} />;
}
