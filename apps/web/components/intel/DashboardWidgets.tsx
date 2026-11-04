"use client";

import Link from "next/link";
import { CalendarClock, Inbox, Mail } from "lucide-react";
import { Badge, Card, daysLeft, formatDate, Skeleton, useApi } from "@/components/intel/common";

type Reminder = { id: number; document_id: string; title: string | null; label: string; due_on: string; days_left: number };
type Account = { id: number; address: string; status: string };

/** Slot: dashboard grid, after OA's core widgets. */
export function IntelDashboardWidgets() {
  const review = useApi<{ pending: number }>("/api/review/count");
  const reminders = useApi<{ items: Reminder[] }>("/api/reminders");
  const accounts = useApi<{ items: Account[] }>("/api/sources/accounts");
  const attention = accounts.data?.items.filter((a) => a.status !== "active" && a.status !== "paused") ?? [];
  return (
    <>
      <Card title="Needs review" actions={<Inbox aria-hidden="true" className="size-5 text-text-muted" />}>
        {!review.data ? <Skeleton rows={1} /> : (
          <Link href="/review" className="block">
            <span className="tabular text-lg font-semibold">{review.data.pending}</span>{" "}
            <span className="text-text-muted">{review.data.pending === 1 ? "suggestion waiting" : "suggestions waiting"}</span>
          </Link>
        )}
      </Card>
      <Card title="Next deadlines" actions={<CalendarClock aria-hidden="true" className="size-5 text-text-muted" />}>
        {!reminders.data ? <Skeleton rows={3} /> : !reminders.data.items.length ? (
          <p className="text-sm text-text-muted">No upcoming deadlines.</p>
        ) : (
          <ul className="space-y-2">
            {reminders.data.items.slice(0, 5).map((r) => (
              <li key={r.id} className="flex items-center justify-between gap-2 text-sm">
                <Link href={`/documents/${r.document_id}`} className="min-w-0 truncate hover:underline">{r.label}: {r.title ?? "Document"}</Link>
                <span className="flex shrink-0 items-center gap-2">
                  <span className="tabular text-xs text-text-muted">{formatDate(r.due_on)}</span>
                  <Badge tone={r.days_left <= 7 ? "warn" : "muted"}>{daysLeft(r.days_left)}</Badge>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="Email" actions={<Mail aria-hidden="true" className="size-5 text-text-muted" />}>
        {!accounts.data ? <Skeleton rows={1} /> : !accounts.data.items.length ? (
          <Link href="/sources?connect=choose" className="text-sm text-primary hover:underline">Connect a mailbox to import attachments</Link>
        ) : attention.length ? (
          <Link href="/sources" className="flex items-center gap-2 text-sm"><Badge tone="error">Needs attention</Badge>{attention.map((a) => a.address).join(", ")}</Link>
        ) : (
          <Link href="/sources" className="flex items-center gap-2 text-sm"><Badge tone="ok">All mailboxes OK</Badge>{accounts.data.items.length} connected</Link>
        )}
      </Card>
    </>
  );
}
