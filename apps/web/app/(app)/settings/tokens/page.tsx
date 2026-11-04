import { redirect } from "next/navigation";
import { ApiTokens } from "@/components/core/api-tokens";
import { serverClient } from "@/lib/api/server";

export default async function TokensPage() {
  const api = await serverClient();
  const [{ data }, tokens] = await Promise.all([
    api.GET("/api/auth/me"),
    api.GET("/api/tokens").catch(() => null),
  ]);
  if (!data) redirect("/login");
  return (
    <ApiTokens
      admin={data.role === "admin"}
      initialTokens={tokens?.data?.items || null}
    />
  );
}
