"use client";

import * as React from "react";
import Link from "next/link";
import { Check, RefreshCw, Sparkles, X } from "lucide-react";
import {
  DocumentAIStatus,
  isAIWorking,
  useAIStatuses,
} from "./DocumentAIStatus";
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

type Item = {
  id: number;
  kind: string;
  field: string | null;
  suggested: { value?: unknown; currency?: string } | null;
  confidence: number | null;
  reason: string | null;
};
type Run = {
  id: number;
  at: string;
  task: string;
  provider: string;
  model: string;
  local: boolean;
  status: string;
};

function show(v: Item["suggested"]): string {
  if (!v || v.value === null || v.value === undefined) return "–";
  return Array.isArray(v.value)
    ? v.value.join(", ")
    : [String(v.value), v.currency].filter(Boolean).join(" ");
}

/** Slot: document detail, right column. Pending suggestions, AI history and "Re-run AI". */
export function DocumentAIPanel({
  documentId,
  canEdit = true,
  onComplete,
}: {
  documentId: string;
  canEdit?: boolean;
  onComplete?: () => void;
}) {
  const queue = useApi<{
    items: { document: { id: string; can_resolve: boolean }; items: Item[] }[];
  }>(`/api/review/queue?document_id=${encodeURIComponent(documentId)}`);
  const runs = useApi<{ items: Run[] }>(
    `/api/ai/runs?document_id=${encodeURIComponent(documentId)}&limit=20`,
  );
  const [error, setError] = React.useState<ApiError | null>(null);
  const [requesting, setRequesting] = React.useState(false);
  const progress = useAIStatuses([documentId]);
  const status = progress.items[documentId];
  const active = isAIWorking(status);
  const wasActive = React.useRef(false);
  const { reload: reloadQueue } = queue;
  const { reload: reloadRuns } = runs;
  React.useEffect(() => {
    if (wasActive.current && !active) {
      reloadQueue();
      reloadRuns();
      onComplete?.();
    }
    wasActive.current = active;
  }, [active, reloadQueue, reloadRuns, onComplete]);
  const group = queue.data?.items.find((g) => g.document.id === documentId);
  const items = group?.items.filter((i) => i.kind !== "new_term") ?? [];

  const resolve = (item: Item, action: "accept" | "reject") =>
    api(`/api/review/items/${item.id}/${action}`, {
      method: "POST",
      json: action === "accept" ? {} : undefined,
    })
      .then(() => {
        queue.reload();
        runs.reload();
        progress.reload();
        onComplete?.();
      })
      .catch(setError);

  return (
    <Card
      title="AI analysis"
      actions={
        <Sparkles aria-hidden="true" className="size-4 text-text-muted" />
      }
    >
      <div className="mb-4 space-y-2" aria-live="polite">
        <DocumentAIStatus status={status} unavailable={progress.error} />
        {status?.category_label && (
          <p className="text-sm">
            Categorized as{" "}
            <span className="font-medium">{status.category_label}</span>.
          </p>
        )}
        {status?.suggested_category && !status.category && (
          <p className="text-sm text-text-muted">
            Suggested category: {status.suggested_category}. Review and accept
            it below to apply it.
          </p>
        )}
        {status &&
          ["failed", "blocked", "disabled", "paused"].includes(
            status.status,
          ) && (
            <Link
              className="inline-block text-sm text-primary underline"
              href="/settings/ai"
            >
              Check AI settings
            </Link>
          )}
        {progress.error && (
          <Button size="sm" variant="secondary" onClick={progress.reload}>
            Retry status
          </Button>
        )}
      </div>
      {error && (
        <div className="mb-3">
          <ErrorBox error={error} />
        </div>
      )}
      {queue.loading && !queue.data ? (
        <Skeleton rows={2} />
      ) : (
        items.length > 0 && (
          <div className="mb-4">
            <h3 className="mb-2 font-semibold">Suggestions</h3>
            <ul className="space-y-2">
              {items.map((i) => (
                <li
                  key={i.id}
                  className="flex flex-wrap items-center justify-between gap-2 text-sm"
                >
                  {i.kind === "notice" ? (
                    <span className="flex items-center gap-2">
                      <Badge tone="warn">Notice</Badge>
                      {i.reason}
                    </span>
                  ) : (
                    <span className="min-w-0">
                      <span className="text-text-muted">
                        {fieldLabel(i.field ?? "")}:
                      </span>{" "}
                      <span className="font-medium">{i.field === "category" ? status?.suggested_category || show(i.suggested) : show(i.suggested)}</span>
                    </span>
                  )}
                  <span className="flex items-center gap-1">
                    {i.confidence !== null && (
                      <Meter value={i.confidence} label="Confidence" />
                    )}
                    {group?.document.can_resolve &&
                      (i.kind === "notice" ? (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => resolve(i, "reject")}
                        >
                          Dismiss
                        </Button>
                      ) : (
                        <>
                          <Button
                            size="sm"
                            variant="ghost"
                            aria-label={`Accept ${fieldLabel(i.field ?? "")}`}
                            disabled={i.suggested?.value == null}
                            onClick={() => resolve(i, "accept")}
                          >
                            <Check aria-hidden="true" />
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            aria-label={`Reject ${fieldLabel(i.field ?? "")}`}
                            onClick={() => resolve(i, "reject")}
                          >
                            <X aria-hidden="true" />
                          </Button>
                        </>
                      ))}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )
      )}
      <h3 className="mb-2 font-semibold">History</h3>
      {runs.error ? (
        <p className="text-sm text-text-muted">History is not available.</p>
      ) : !runs.data ? (
        <Skeleton rows={2} />
      ) : !runs.data.items.length ? (
        <p className="text-sm text-text-muted">
          AI has not processed this document yet.
        </p>
      ) : (
        <ul className="space-y-2 text-sm">
          {runs.data.items.map((r) => (
            <li
              key={r.id}
              className="flex flex-wrap items-center justify-between gap-2"
            >
              <Link
                href={`/settings/ai/runs/${r.id}`}
                className="hover:underline"
              >
                {fieldLabel(r.task)} · {formatDate(r.at)}
              </Link>
              <span className="flex items-center gap-1">
                <LocalBadge local={r.local} />
                <Badge
                  tone={
                    r.status === "ok"
                      ? "ok"
                      : r.status === "skipped"
                        ? "muted"
                        : "error"
                  }
                >
                  {r.status === "ok"
                    ? "Completed"
                    : r.status === "skipped"
                      ? "Skipped"
                      : "Failed"}
                </Badge>
              </span>
            </li>
          ))}
        </ul>
      )}
      {canEdit && (
        <Button
          className="mt-4"
          variant="secondary"
          disabled={requesting || active}
          onClick={async () => {
            setRequesting(true);
            setError(null);
            try {
              await api("/api/review/reclassify", {
                method: "POST",
                json: {
                  document_ids: [documentId],
                  tasks: ["classify", "extract"],
                },
              });
              progress.reload();
              queue.reload();
            } catch (err) {
              setError(err as ApiError);
            } finally {
              setRequesting(false);
            }
          }}
        >
          <RefreshCw aria-hidden="true" />{" "}
          {requesting
            ? "Queuing…"
            : active
              ? "AI analysis in progress"
              : "Re-run AI"}
        </Button>
      )}
    </Card>
  );
}
