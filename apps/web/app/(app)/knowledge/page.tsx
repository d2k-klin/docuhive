import { redirect } from "next/navigation";
import { KnowledgeBases } from "@/components/core/knowledge-bases";
import { serverClient } from "@/lib/api/server";

export default async function KnowledgePage() {
  const api = await serverClient();
  const [{ data }, bases, taxonomy, suggestions] = await Promise.all([
    api.GET("/api/auth/me"),
    api.GET("/api/kb").catch(() => null),
    api.GET("/api/kb/options").catch(() => null),
    api.GET("/api/kb/suggestions").catch(() => null),
  ]);
  if (!data) redirect("/login");
  const statuses = await Promise.all(
    (bases?.data?.items || []).map(async (base) => {
      const response = await api
        .GET("/api/kb/{kb_id}/status", { params: { path: { kb_id: base.id } } })
        .catch(() => null);
      return [base.id, response?.data || null] as const;
    }),
  );
  return (
    <KnowledgeBases
      userId={data.id}
      initial={{
        bases: bases?.data || null,
        taxonomy: taxonomy?.data || null,
        suggestions: suggestions?.data || null,
        statuses: Object.fromEntries(statuses),
      }}
    />
  );
}
