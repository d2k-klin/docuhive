"use client";

import type * as React from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge, ErrorBox, Skeleton, useApi } from "@/components/intel/common";

type Check = {
  id: string;
  title: string;
  status: "ok" | "todo" | "warn" | "error" | "optional";
  message: string;
  action_label: string | null;
  action_href: string | null;
  help_doc: string | null;
  required: boolean;
};
const TONE = { ok: "ok", todo: "info", warn: "warn", error: "error", optional: "muted" } as const;
const TEXT = { ok: "Done", todo: "To do", warn: "Check", error: "Problem", optional: "Optional" };

function Checks({ path, onDone, intro }: { path: string; onDone(): void; intro: string }) {
  const { data, error, reload } = useApi<Check[]>(path);
  const blocking = data?.some((c) => c.required && c.status !== "ok");
  return (
    <div className="space-y-4">
      <p className="max-w-[65ch] text-text-muted">{intro}</p>
      {error ? <ErrorBox error={error} onRetry={reload} /> : !data ? <Skeleton rows={2} /> : (
        <ul className="space-y-3">
          {data.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center justify-between gap-3 rounded border border-border p-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2 font-medium">{c.title}<Badge tone={TONE[c.status]}>{TEXT[c.status]}</Badge></div>
                <p className="text-sm text-text-muted">{c.message}</p>
              </div>
              {c.action_href && c.status !== "ok" && (
                <Button asChild size="sm" variant="secondary"><Link href={c.action_href}>{c.action_label ?? "Open"}</Link></Button>
              )}
            </li>
          ))}
        </ul>
      )}
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={reload}>Check again</Button>
        <Button onClick={onDone}>{blocking ? "Skip for now" : "Continue"}</Button>
      </div>
    </div>
  );
}

/** Slot: the /setup wizard renders these between OA's storage and phone steps. */
export const intelSetupSteps: { id: string; title: string; Component: React.FC<{ onDone(): void }> }[] = [
  {
    id: "ai",
    title: "AI models and privacy",
    Component: ({ onDone }) => (
      <Checks path="/api/ai/setup-status" onDone={onDone}
        intro="DocuHive reads, sorts and answers questions about your documents with AI. A local model (Ollama) keeps everything on this server; private categories always stay local." />
    ),
  },
  {
    id: "mail",
    title: "Email accounts",
    Component: ({ onDone }) => (
      <Checks path="/api/sources/setup-status" onDone={onDone}
        intro="Connect a mailbox and DocuHive imports invoices, statements and contracts from attachments. Access is read-only." />
    ),
  },
  {
    id: "notifications",
    title: "Notifications",
    Component: ({ onDone }) => (
      <Checks path="/api/notifications/setup-status" onDone={onDone}
        intro="Get reminded before contracts end, invoices are due or IDs expire, on your phone or by email." />
    ),
  },
];
