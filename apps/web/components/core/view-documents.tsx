"use client";

import { useState } from "react";
import { FileText, TriangleAlert } from "lucide-react";
import { browserClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { Button } from "@/components/ui/button";
import { ExportButton } from "./export-button";

type View = components["schemas"]["SavedViewView"];
type Page = components["schemas"]["DocumentPage"];
const api = browserClient();

export function ViewDocuments({
  view,
  initial,
}: {
  view: View;
  initial: Page | null;
}) {
  const [items, setItems] = useState(initial?.items || []);
  const [next, setNext] = useState(initial?.next_offset ?? null);
  const [error, setError] = useState(
    initial ? "" : "Documents could not be loaded. Try again.",
  );
  const [loading, setLoading] = useState(false);
  async function more(offset: number) {
    setLoading(true);
    setError("");
    const response = await api
      .GET("/api/views/{view_id}/documents", {
        params: { path: { view_id: view.id }, query: { offset } },
      })
      .catch(() => null);
    setLoading(false);
    if (!response?.data) {
      setError("Documents could not be loaded. Try again.");
      return;
    }
    const page = response.data;
    setItems((previous) =>
      offset ? [...previous, ...page.items] : page.items,
    );
    setNext(page.next_offset ?? null);
  }
  return (
    <main className="mx-auto max-w-screen-xl space-y-6 p-4 md:p-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div className="min-w-0">
          <h1 className="break-words text-xl font-semibold">{view.name}</h1>
          <p className="text-sm text-text-muted tabular">
            {initial ? `${initial.total} documents` : "Saved view"}
          </p>
        </div>
        {items.length > 0 && (
          <ExportButton
            source={{ view_id: view.id }}
            label={`Export ${view.name}`}
          />
        )}
      </header>
      {error && (
        <div
          role="alert"
          className="flex flex-wrap items-center gap-2 text-sm text-danger"
        >
          <TriangleAlert className="size-4" aria-hidden="true" />
          {error}
          <Button variant="secondary" onClick={() => void more(0)}>
            Retry loading
          </Button>
        </div>
      )}
      {!error && !items.length && (
        <div className="space-y-2 rounded-card border border-border bg-surface p-4">
          <FileText className="size-5" aria-hidden="true" />
          <h2 className="text-md font-semibold">No documents match yet</h2>
          <p className="text-sm text-text-muted">
            New documents that match this view appear here automatically.
          </p>
        </div>
      )}
      {items.length > 0 && (
        <div className="overflow-x-auto rounded-card border border-border bg-surface">
          <table className="w-full text-left text-base">
            <thead className="text-xs font-medium tracking-[0.02em] text-text-muted">
              <tr className="h-9 border-b border-border">
                {["Title", "Date", "Sender", "Category", "Tags"].map(
                  (label) => (
                    <th key={label} scope="col" className="px-3 font-medium">
                      {label}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {items.map((doc) => (
                <tr
                  key={doc.id}
                  className="h-11 border-b border-border last:border-0 hover:bg-surface-2"
                >
                  <td className="max-w-80 break-words px-3">
                    {doc.title || "Untitled document"}
                  </td>
                  <td className="whitespace-nowrap px-3 tabular">
                    {doc.document_date || "No date"}
                  </td>
                  <td className="break-words px-3">
                    {doc.correspondent || "—"}
                  </td>
                  <td className="break-words px-3">{doc.category || "—"}</td>
                  <td className="break-words px-3 text-sm text-text-muted">
                    {doc.tags.join(", ") || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {next !== null && (
        <Button
          variant="secondary"
          disabled={loading}
          onClick={() => void more(next)}
        >
          {loading ? "Loading…" : "Load more"}
        </Button>
      )}
    </main>
  );
}
