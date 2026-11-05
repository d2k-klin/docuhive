"use client";

import { useCallback, useEffect, useState } from "react";
import { LoaderCircle } from "lucide-react";
import { api, Badge } from "./common";

export type AIStatus = {
  document_id: string;
  status: string;
  stage: string | null;
  category: string | null;
  category_label: string | null;
  suggested_category: string | null;
  ai_run_id: number | null;
};

export function isAIWorking(status?: AIStatus) {
  return (
    !!status &&
    ["queued", "running", "processing", "retrying", "paused"].includes(
      status.status,
    )
  );
}

export function useAIStatuses(ids: string[]) {
  const key = [...new Set(ids)].sort().join(",");
  const [items, setItems] = useState<Record<string, AIStatus>>({});
  const [error, setError] = useState(false);
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((n) => n + 1), []);
  useEffect(() => {
    if (!key) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      let delay = 15000;
      try {
        const documentIds = key.split(",");
        const responses = await Promise.all(
          Array.from({ length: Math.ceil(documentIds.length / 500) }, (_, i) =>
            api<{ items: AIStatus[] }>("/api/ai/documents/status", {
              method: "POST",
              json: { document_ids: documentIds.slice(i * 500, (i + 1) * 500) },
            }),
          ),
        );
        const result = { items: responses.flatMap((r) => r.items) };
        if (cancelled) return;
        setItems(
          Object.fromEntries(
            result.items.map((item) => [item.document_id, item]),
          ),
        );
        setError(false);
        if (result.items.some((s) => isAIWorking(s) && s.status !== "paused"))
          delay = 2500;
      } catch {
        if (!cancelled) setError(true);
      }
      if (!cancelled) timer = setTimeout(() => void load(), delay);
    }
    void load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [key, tick]);
  return { items, error, reload };
}

const labels: Record<string, string> = {
  queued: "AI queued",
  running: "AI in progress",
  processing: "Reading document…",
  categorized: "Categorized",
  completed: "AI completed",
  needs_review: "Completed · needs review",
  failed: "AI needs attention",
  retrying: "AI waiting to retry",
  paused: "AI paused · budget used",
  blocked: "AI needs setup",
  disabled: "AI is off",
  not_started: "Not analysed yet",
};
const stages: Record<string, string> = {
  "document.stored": "AI queued",
  "ai.classify": "Categorising…",
  "ai.extract": "Extracting details…",
  "index.embed": "Making searchable…",
};

export function DocumentAIStatus({
  status,
  unavailable = false,
}: {
  status?: AIStatus;
  unavailable?: boolean;
}) {
  if (unavailable) return <Badge tone="warn">AI status unavailable</Badge>;
  if (!status)
    return <span className="text-xs text-text-muted">Checking AI status…</span>;
  const working = isAIWorking(status);
  const tone = ["failed", "blocked"].includes(status.status)
    ? "error"
    : ["needs_review", "paused", "retrying"].includes(status.status)
      ? "warn"
      : working
        ? "info"
        : ["categorized", "completed"].includes(status.status)
          ? "ok"
          : "muted";
  return (
    <Badge
      tone={tone}
      icon={status.status === "running" ? LoaderCircle : undefined}
    >
      {status.status === "running"
        ? stages[status.stage || ""] || labels.running
        : labels[status.status] || "AI status unavailable"}
    </Badge>
  );
}
