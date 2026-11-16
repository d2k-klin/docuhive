import { redirect } from "next/navigation";
import { Identities } from "@/components/core/identities";
import { serverClient } from "@/lib/api/server";

export default async function IdentitiesPage() {
  const api = await serverClient();
  const [{ data }, profiles] = await Promise.all([
    api.GET("/api/auth/me"),
    api.GET("/api/profiles").catch(() => null),
  ]);
  if (!data) redirect("/login");
  return <Identities initial={profiles?.data || null} viewerId={data.id} />;
}
