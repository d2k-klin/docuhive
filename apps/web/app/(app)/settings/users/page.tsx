import type { ComponentProps } from "react";
import { notFound, redirect } from "next/navigation";
import { Users } from "@/components/core/users";
import { serverClient } from "@/lib/api/server";

export default async function UsersPage() {
  const api = await serverClient();
  const { data: me } = await api.GET("/api/auth/me");
  if (!me) redirect("/login");
  if (me.role !== "admin") notFound();
  const [users, taxonomy, bookkeeper] = await Promise.all([
    api.GET("/api/users", { params: { query: { limit: 200 } } }),
    api.GET("/api/taxonomy"),
    api.GET("/api/users/roles/bookkeeper"),
  ]);
  type Listed = ComponentProps<typeof Users>["initial"];
  const people = (users.data as { items?: Listed } | undefined)?.items ?? [];
  const tax = taxonomy.data as { categories?: { id: string; label: string }[] } | undefined;
  return (
    <Users
      initial={people}
      categories={(tax?.categories ?? []).map((c) => ({ id: c.id, label: c.label }))}
      bookkeeper={bookkeeper.data?.categories ?? []}
      viewerId={me.id}
    />
  );
}
