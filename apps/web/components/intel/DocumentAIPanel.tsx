"use client";

import * as React from "react";
import Link from "next/link";
import { Check, RefreshCw, Sparkles, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  api,
  ApiError,
  Badge,
  Card,
  ErrorBox,
  fieldLabel,
  formatDate,
  LocalBadge,
  Meter,
  Skeleton,
  useApi,
} from "@/components/intel/common";

type Item = { id: number; kind: string; field: string | null; suggested: { value?: unknown; currency?: string } | null; confidence: number | null; reason: string | null };
type Run = { id: number; at: string; task: string; provider: string; model: string; local: boolean; status: string };

function show(v: Item["suggested"]): string {
  if (!v || v.value === null || v.value === undefined) return "–";
  return Array.isArray(v.value) ? v.value.join(", ") : [String(v.value), v.currency].filter(Boolean).join(" ");
}

/** Slot: document detail, right column. Pending suggestions, AI history and "Re-run AI". */
export function DocumentAIPanel({ documentId }: { documentId: string }) {
  const queue = useApi<{ items: { document: { id: string; can_resolve: boolean }; items: Item[] }[] }>(
    `/api/review/queue?document_id=${encodeURIComponent(documentId)}`,
  );
  const runs = useApi<{ items: Run[] }>(`/api/ai/runs?document_id=${encodeURIComponent(documentId)}&limit=20`);
  const [error, setError] = React.useState<ApiError | null>(null);
  const [queued, setQueued] = React.useState(false);
  const group = queue.data?.items.find((g) => g.document.id === documentId);
  const items = group?.items.filter((i) => i.kind !== "new_term") ?? [];

  const resolve = (item: Item, action: "accept" | "reject") =>
    api(`/api/review/items/${item.id}/${action}`, { method: "POST", json: action === "accept" ? {} : undefined })
      .then(queue.reload).catch(setError);

  return (
    <Card title="AI" actions={<Sparkles aria-hidden="true" className="size-4 text-text-muted" />}>
      {error && <div className="mb-3"><ErrorBox error={error} /></div>}
      {queue.loading && !queue.data ? <Skeleton rows={2} /> : items.length > 0 && (
        <div className="mb-4">
          <h3 className="mb-2 font-semibold">Suggestions</h3>
          <ul className="space-y-2">
            {items.map((i) => (
              <li key={i.id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
                {i.kind === "notice" ? <span className="flex items-center gap-2"><Badge tone="warn">Notice</Badge>{i.reason}</span> : (
                  <span className="min-w-0"><span className="text-text-muted">{fieldLabel(i.field ?? "")}:</span> <span className="font-medium">{show(i.suggested)}</span></span>
                )}
                <span className="flex items-center gap-1">
                  {i.confidence !== null && <Meter value={i.confidence} label="Confidence" />}
                  {group?.document.can_resolve && (i.kind === "notice" ? (
                    <Button size="sm" variant="ghost" onClick={() => resolve(i, "reject")}>Dismiss</Button>
                  ) : (
                    <>
                      <Button size="sm" variant="ghost" aria-label={`Accept ${fieldLabel(i.field ?? "")}`} disabled={i.suggested?.value == null} onClick={() => resolve(i, "accept")}><Check aria-hidden="true" /></Button>
                      <Button size="sm" variant="ghost" aria-label={`Reject ${fieldLabel(i.field ?? "")}`} onClick={() => resolve(i, "reject")}><X aria-hidden="true" /></Button>
                    </>
                  ))}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <h3 className="mb-2 font-semibold">History</h3>
      {runs.error ? <p className="text-sm text-text-muted">History is not available.</p> : !runs.data ? <Skeleton rows={2} /> :
        !runs.data.items.length ? <p className="text-sm text-text-muted">AI has not processed this document yet.</p> : (
          <ul className="space-y-2 text-sm">
            {runs.data.items.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center justify-between gap-2">
                <Link href={`/settings/ai/runs/${r.id}`} className="hover:underline">{fieldLabel(r.task)} · {formatDate(r.at)}</Link>
                <span className="flex items-center gap-1"><LocalBadge local={r.local} /><Badge tone={r.status === "ok" ? "ok" : r.status === "skipped" ? "muted" : "error"}>{r.status}</Badge></span>
              </li>
            ))}
          </ul>
        )}
      <Button className="mt-4" variant="secondary" disabled={queued} onClick={() =>
        api("/api/review/reclassify", { method: "POST", json: { document_ids: [documentId], tasks: ["classify", "extract"] } })
          .then(() => setQueued(true)).catch(setError)}>
        <RefreshCw aria-hidden="true" /> {queued ? "Queued, results appear in Review" : "Re-run AI"}
      </Button>
    </Card>
  );
}
