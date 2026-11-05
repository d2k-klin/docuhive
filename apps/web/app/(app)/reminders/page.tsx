"use client";

import * as React from "react";
import Link from "next/link";
import { CalendarClock, Check, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  api,
  ApiError,
  Badge,
  daysLeft,
  Card,
  Empty,
  ErrorBox,
  formatDate,
  Page,
  PageHeader,
  Skeleton,
  useApi,
} from "@/components/intel/common";

type Reminder = { id: number; document_id: string; title: string | null; fact: string; label: string; due_on: string; days_left: number; status: string };

export default function RemindersPage() {
  const list = useApi<{ items: Reminder[] }>("/api/reminders");
  const [error, setError] = React.useState<ApiError | null>(null);
  const byMonth = new Map<string, Reminder[]>();
  for (const r of list.data?.items ?? []) {
    const key = new Date(`${r.due_on}T00:00:00`).toLocaleDateString(undefined, { year: "numeric", month: "long" });
    byMonth.set(key, [...(byMonth.get(key) ?? []), r]);
  }
  async function resolve(r: Reminder, action: "dismiss" | "done") {
    const before = list.data;
    list.setData((d) => d && { items: d.items.filter((x) => x.id !== r.id) });
    await api(`/api/reminders/${r.id}/${action}`, { method: "POST" }).catch((e) => {
      list.setData(before);
      setError(e);
    });
  }
  return (
    <Page narrow>
      <PageHeader title="Reminders" description="Deadlines found in your documents: due dates, contract ends, notice periods, renewals." />
      {error && <div className="mb-4"><ErrorBox error={error} /></div>}
      {list.loading && !list.data ? <Skeleton rows={5} /> : list.error ? <ErrorBox error={list.error} onRetry={list.reload} /> :
        byMonth.size === 0 ? (
          <Empty icon={CalendarClock} text="No upcoming deadlines. They appear here when documents with due dates or contract ends are added."
            action={<Button asChild variant="secondary"><Link href="/settings/notifications">Set up notifications</Link></Button>} />
        ) : (
          <div className="space-y-4">
            {[...byMonth].map(([month, items]) => (
              <Card key={month} title={month}>
                <ul className="divide-y divide-border">
                  {items.map((r) => (
                    <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
                      <div className="min-w-0">
                        <div className="font-medium">{r.label}</div>
                        <Link href={`/documents/${r.document_id}`} className="block truncate text-sm text-text-muted hover:underline">{r.title ?? "Document"}</Link>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="tabular text-sm">{formatDate(r.due_on)}</span>
                        <Badge tone={r.days_left <= 7 ? "warn" : "muted"}>{daysLeft(r.days_left)}</Badge>
                        <Button size="sm" variant="secondary" onClick={() => resolve(r, "done")}><Check aria-hidden="true" /> Done</Button>
                        <Button size="sm" variant="ghost" aria-label={`Dismiss ${r.label}`} onClick={() => resolve(r, "dismiss")}><X aria-hidden="true" /></Button>
                      </div>
                    </li>
                  ))}
                </ul>
              </Card>
            ))}
          </div>
        )}
      <Card title="In your calendar" className="mt-4">
        <p className="max-w-[65ch] text-sm text-text-muted">
          Subscribe to <code className="font-mono">/api/reminders.ics?token=…</code> with a personal API token that has only the
          calendar scope (API tokens). See docs/setup/notifications.md.
        </p>
      </Card>
    </Page>
  );
}
