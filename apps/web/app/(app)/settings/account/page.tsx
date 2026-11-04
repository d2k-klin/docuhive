import { redirect } from "next/navigation";
import { AccountPage } from "@/components/core/account";
import { serverClient } from "@/lib/api/server";

export default async function Account() {
  const me = await (await serverClient()).GET("/api/auth/me").catch(() => null);
  if (!me?.data) redirect("/login");
  return <AccountPage username={me.data.username} role={me.data.role} />;
}
