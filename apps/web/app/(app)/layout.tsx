import Link from "next/link";
import { redirect } from "next/navigation";
import { serverClient } from "@/lib/api/server";
import { visibleNav } from "@/lib/nav";
import { UserActions } from "@/components/core/user-actions";

export default async function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const client = await serverClient();
  const response = await client.GET("/api/auth/me").catch(() => null);
  if (!response?.data) redirect("/login");
  const user = response.data;
  const implemented = new Set(["/"]);
  const items = visibleNav(user.role).filter(
    (item) => item.section === "intel" || implemented.has(item.href),
  );
  return (
    <div className="min-h-screen md:flex">
      <aside className="border-b border-border bg-surface p-4 md:w-56 md:border-b-0 md:border-r">
        <Link href="/" className="mb-6 block text-md font-semibold">
          DocuHive
        </Link>
        <nav
          aria-label="Main navigation"
          className="flex flex-wrap gap-2 md:flex-col"
        >
          {items.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="flex h-control items-center gap-2 rounded px-3 text-sm hover:bg-surface-2"
            >
              <item.icon className="size-4" aria-hidden="true" />
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>
      <div className="min-w-0 flex-1">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-border bg-surface px-4 py-3 md:px-6">
          <span className="text-sm text-text-muted">{user.username}</span>
          <UserActions />
        </header>
        {children}
      </div>
    </div>
  );
}
