"use client";

import { useState } from "react";
import { CircleCheck, Copy, TriangleAlert } from "lucide-react";
import { browserClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { errorMessage } from "@/lib/i18n/errors";
import { Button } from "@/components/ui/button";

type Pair = components["schemas"]["DuplicateView"];
type Side = components["schemas"]["DuplicateSide"];
const api = browserClient();
const reasons: Record<Pair["reasons"][number], string> = {
  same_sender: "Same sender",
  same_amount: "Same amount",
  close_date: "Dates within a week",
  similar_content: "Very similar text",
};

function Document({ side }: { side: Side }) {
  return (
    <div className="min-w-0 space-y-1 rounded border border-border p-3">
      <p className="break-words font-medium">
        {side.title || "Untitled document"}
      </p>
      <p className="break-words text-xs text-text-muted tabular">
        {side.document_date || "No date"} · {side.correspondent || "No sender"}
      </p>
    </div>
  );
}

export function Duplicates({ initial }: { initial: Pair[] | null }) {
  const [items, setItems] = useState<Pair[]>(initial || []);
  const [error, setError] = useState(
    initial ? "" : "Possible duplicates could not be loaded. Try again.",
  );
  const [busy, setBusy] = useState<number | null>(null);

  async function load() {
    setError("");
    const response = await api.GET("/api/duplicates").catch(() => null);
    if (!response?.data) {
      setError("Possible duplicates could not be loaded. Try again.");
      return;
    }
    setItems(response.data);
  }
  async function decide(pair: Pair, status: "dismissed" | "confirmed") {
    setBusy(pair.id);
    setError("");
    try {
      const response = await api.POST("/api/duplicates/{pair_id}", {
        params: { path: { pair_id: pair.id } },
        body: { status },
      });
      if (!response.response.ok) {
        setError(
          errorMessage(
            (response.error as { error?: { code?: string } })?.error?.code,
          ),
        );
        return;
      }
      setItems((previous) => previous.filter((p) => p.id !== pair.id));
    } catch {
      setError("The decision could not be saved. Try again.");
    } finally {
      setBusy(null);
    }
  }
  return (
    <main className="mx-auto max-w-screen-xl space-y-6 p-4 md:p-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Possible duplicates</h1>
          <p className="text-sm text-text-muted">
            The same document that arrived twice, for example by email and as a
            scan.
          </p>
        </div>
        <Button variant="secondary" onClick={() => void load()}>
          Refresh
        </Button>
      </header>
      <p className="max-w-prose text-sm text-text-muted">
        Nothing is deleted here. Your answer only stops the pair from being
        suggested again.
      </p>
      {error && (
        <div
          role="alert"
          className="flex flex-wrap items-center gap-2 text-sm text-danger"
        >
          <TriangleAlert className="size-4" aria-hidden="true" />
          {error}
          <Button variant="secondary" onClick={() => void load()}>
            Retry loading
          </Button>
        </div>
      )}
      {!error && !items.length && (
        <div className="space-y-2 rounded-card border border-border bg-surface p-4">
          <CircleCheck className="size-5" aria-hidden="true" />
          <h2 className="text-md font-semibold">No possible duplicates</h2>
          <p className="text-sm text-text-muted">
            New documents are compared with your archive automatically.
          </p>
        </div>
      )}
      <ul className="space-y-4">
        {items.map((pair) => (
          <li
            key={pair.id}
            className="space-y-3 rounded-card border border-border bg-surface p-4"
          >
            <div className="flex flex-wrap items-center gap-2">
              <Copy className="size-4" aria-hidden="true" />
              {pair.reasons.map((reason) => (
                <span
                  key={reason}
                  className="inline-flex h-5 items-center rounded-[6px] bg-surface-2 px-2 text-xs font-medium"
                >
                  {reasons[reason]}
                </span>
              ))}
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <Document side={pair.document} />
              <Document side={pair.other} />
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="secondary"
                disabled={busy === pair.id}
                onClick={() => void decide(pair, "dismissed")}
              >
                Not a duplicate
              </Button>
              <Button
                disabled={busy === pair.id}
                onClick={() => void decide(pair, "confirmed")}
              >
                Yes, it’s a duplicate
              </Button>
            </div>
          </li>
        ))}
      </ul>
      <details className="max-w-prose text-sm">
        <summary className="cursor-pointer font-medium">
          How was this made?
        </summary>
        <p className="mt-2 text-text-muted">
          After a document is indexed, it is compared with your other documents
          on sender, amounts, dates and meaning. A pair is shown only when the
          dates are within a week and at least two of the other signals agree,
          or when the text is nearly identical.
        </p>
        <a
          className="mt-2 inline-block text-primary underline"
          href="https://github.com/d2k-klin/docuhive/blob/main/docs/learn/13-near-duplicates.md"
          target="_blank"
          rel="noreferrer"
        >
          Learn about near-duplicate detection
        </a>
      </details>
    </main>
  );
}
