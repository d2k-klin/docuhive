import { notFound, redirect } from "next/navigation";
import { LinkedFolders } from "@/components/core/linked-folders";
import { serverClient } from "@/lib/api/server";

export default async function FoldersPage() {
  const api = await serverClient();
  const { data: me } = await api.GET("/api/auth/me");
  if (!me) redirect("/login");
  if (me.role !== "admin") notFound();
  return <LinkedFolders />;
}
