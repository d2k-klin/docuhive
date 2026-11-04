import { Duplicates } from "@/components/core/duplicates";
import { serverClient } from "@/lib/api/server";

export default async function DuplicatesPage() {
  const api = await serverClient();
  const pairs = await api.GET("/api/duplicates").catch(() => null);
  return <Duplicates initial={pairs?.data || null} />;
}
