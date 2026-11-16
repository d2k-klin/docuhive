import { redirect } from "next/navigation";
import { Plugins } from "@/components/core/plugins";
import { serverClient } from "@/lib/api/server";

export default async function PluginsPage() {
  const api = await serverClient();
  const { data } = await api.GET("/api/auth/me");
  if (!data) redirect("/login");
  if (data.role !== "admin") redirect("/");
  return <Plugins />;
}
