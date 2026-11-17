import { redirect } from "next/navigation";
import { Plugins } from "@/components/core/plugins";
import { serverClient } from "@/lib/api/server";

export default async function PluginsPage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string }>;
}) {
  const api = await serverClient();
  const { data } = await api.GET("/api/auth/me");
  if (!data) redirect("/login");
  if (data.role !== "admin") redirect("/");
  const { tab } = await searchParams;
  return (
    <Plugins initialTab={tab === "marketplace" ? "marketplace" : "installed"} />
  );
}
