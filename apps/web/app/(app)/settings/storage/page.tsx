import { redirect } from "next/navigation";
import { VaultHealth } from "@/components/core/vault-health";
import { serverClient } from "@/lib/api/server";

export default async function StoragePage() {
  const api = await serverClient();
  const { data } = await api.GET("/api/auth/me");
  if (!data) redirect("/login");
  if (data.role !== "admin") redirect("/");
  const report = await api.GET("/api/system/vault/health").catch(() => null);
  const backup = await api.GET("/api/system/backup").catch(() => null);
  const storage = await api.GET("/api/system/storage").catch(() => null);
  return (
    <VaultHealth
      initial={report?.data || null}
      backup={backup?.data || null}
      storage={storage?.data || null}
    />
  );
}
