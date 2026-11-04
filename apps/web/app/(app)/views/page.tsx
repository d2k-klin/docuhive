import { redirect } from "next/navigation";
import { SavedViews } from "@/components/core/saved-views";
import { serverClient } from "@/lib/api/server";

export default async function ViewsPage() {
  const api = await serverClient();
  const [{ data }, views, taxonomy] = await Promise.all([
    api.GET("/api/auth/me"),
    api.GET("/api/views").catch(() => null),
    api.GET("/api/kb/options").catch(() => null),
  ]);
  if (!data) redirect("/login");
  return (
    <SavedViews
      userId={data.id}
      initial={views?.data || null}
      taxonomy={taxonomy?.data || null}
    />
  );
}
