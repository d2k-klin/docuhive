"use client";

import { useCallback, useState } from "react";
import {
  BookOpen,
  CircleCheck,
  CircleDashed,
  LockKeyhole,
  TriangleAlert,
} from "lucide-react";
import { browserClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { errorMessage } from "@/lib/i18n/errors";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DocumentFilters, emptyFilters } from "./document-filters";
import { checkbox as checkboxClass } from "@/lib/ui/control";

type Base = components["schemas"]["KnowledgeBaseView"];
type Draft = components["schemas"]["KnowledgeBaseInput"];
type Status = components["schemas"]["KnowledgeBaseStatus"];
type Taxonomy = components["schemas"]["Taxonomy"];
type Suggestion = components["schemas"]["KnowledgeBaseSuggestion"];
const api = browserClient();
const empty: Draft = {
  name: "",
  description: "",
  filters: emptyFilters,
  shared: false,
  local_only: true,
};

export function KnowledgeBases({
  userId,
  initial,
}: {
  userId: number;
  initial: {
    bases: components["schemas"]["KnowledgeBaseList"] | null;
    taxonomy: Taxonomy | null;
    suggestions: Suggestion[] | null;
    statuses: Record<number, Status | null>;
  };
}) {
  const [items, setItems] = useState<Base[]>(initial.bases?.items || []);
  const [statuses, setStatuses] = useState(initial.statuses);
  const [taxonomy, setTaxonomy] = useState(initial.taxonomy);
  const [suggestions, setSuggestions] = useState(initial.suggestions || []);
  const [cursor, setCursor] = useState<string | null>(
    initial.bases?.next_cursor || null,
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(
    initial.bases && initial.taxonomy && initial.suggestions
      ? ""
      : "Knowledge bases could not be loaded. Try again.",
  );
  const [draft, setDraft] = useState<Draft | null>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const editor = useCallback((node: HTMLDivElement | null) => {
    if (node) {
      node.scrollIntoView({ block: "start" });
      node.querySelector("input")?.focus();
    }
  }, []);
  const load = useCallback(async (after?: string) => {
    setLoading(true);
    setError("");
    try {
      const [bases, vocab, offered] = await Promise.all([
        api.GET("/api/kb", {
          params: { query: { cursor: after ? Number(after) : undefined } },
        }),
        api.GET("/api/kb/options"),
        api.GET("/api/kb/suggestions"),
      ]);
      if (!bases.data || !vocab.data || !offered.data) throw new Error();
      setItems((previous) =>
        after ? [...previous, ...bases.data.items] : bases.data.items,
      );
      setCursor(bases.data.next_cursor);
      setTaxonomy(vocab.data);
      setSuggestions(offered.data);
      const entries = await Promise.all(
        bases.data.items.map(async (base) => {
          const response = await api
            .GET("/api/kb/{kb_id}/status", {
              params: { path: { kb_id: base.id } },
            })
            .catch(() => null);
          return [base.id, response?.data || null] as const;
        }),
      );
      setStatuses((previous) =>
        after
          ? { ...previous, ...Object.fromEntries(entries) }
          : Object.fromEntries(entries),
      );
    } catch {
      setError("Knowledge bases could not be loaded. Try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  function start(base?: Base | Suggestion) {
    setEditing(base && "id" in base ? base.id : null);
    setDraft(base && "id" in base ? base : { ...empty, ...base });
    setError("");
  }
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!draft) return;
    setBusy(true);
    setError("");
    const body: Draft = {
      name: draft.name,
      description: draft.description,
      shared: draft.shared,
      local_only: draft.local_only,
      filters: {
        ...emptyFilters,
        ...draft.filters,
        correspondents: (draft.filters?.correspondents || [])
          .map((name) => name.trim())
          .filter(Boolean),
      },
    };
    try {
      const response =
        editing === null
          ? await api.POST("/api/kb", { body })
          : await api.PATCH("/api/kb/{kb_id}", {
              params: { path: { kb_id: editing } },
              body,
            });
      if (!response.data) {
        setError(
          errorMessage(
            (response.error as { error?: { code?: string } })?.error?.code,
          ),
        );
        return;
      }
      setDraft(null);
      setEditing(null);
      await load();
    } catch {
      setError("The knowledge base could not be saved. Try again.");
    } finally {
      setBusy(false);
    }
  }
  async function remove(id: number) {
    setBusy(true);
    setError("");
    try {
      const response = await api.DELETE("/api/kb/{kb_id}", {
        params: { path: { kb_id: id } },
      });
      if (!response.response.ok) throw new Error();
      setConfirmDelete(null);
      if (editing === id) setDraft(null);
      await load();
    } catch {
      setError("The knowledge base could not be deleted. Try again.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="mx-auto max-w-screen-xl space-y-6 p-4 md:p-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Knowledge bases</h1>
          <p className="text-sm text-text-muted">
            Save a document scope for questions and connected agents.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            disabled={loading || busy}
            onClick={() => void load()}
          >
            Refresh status
          </Button>
          <Button disabled={!taxonomy || busy} onClick={() => start()}>
            Create knowledge base
          </Button>
        </div>
      </header>
      <p className="max-w-prose text-sm text-text-muted">
        Sharing a knowledge base shares its filters. Everyone still sees only
        documents they can already access.
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
      {loading && !items.length ? (
        <div
          role="status"
          aria-label="Loading knowledge bases"
          className="h-40 animate-pulse rounded-card border border-border bg-surface-2 motion-reduce:animate-none"
        />
      ) : null}
      {!loading && !error && !items.length && (
        <div className="space-y-2 rounded-card border border-border bg-surface p-4">
          <BookOpen className="size-5" aria-hidden="true" />
          <h2 className="text-md font-semibold">No knowledge bases yet</h2>
          <p className="text-sm text-text-muted">
            Create one to choose which documents an agent can search.
          </p>
        </div>
      )}
      {!draft && suggestions.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-md font-semibold">Suggested scopes</h2>
          <div className="flex flex-wrap gap-2">
            {suggestions.map((suggestion) => (
              <Button
                key={suggestion.name}
                variant="secondary"
                onClick={() => start(suggestion)}
              >
                Create {suggestion.name}
              </Button>
            ))}
          </div>
        </div>
      )}
      {draft && taxonomy && (
        <div
          ref={editor}
          key={editing ?? "new"}
          className="rounded-card border border-border bg-surface p-4"
        >
          <form className="max-w-prose space-y-4" onSubmit={save}>
            <h2 className="text-md font-semibold">
              {editing === null
                ? "Create knowledge base"
                : "Edit knowledge base"}
            </h2>
            <label className="block space-y-1.5 text-sm font-medium">
              Name
              <Input
                required
                maxLength={100}
                value={draft.name}
                onChange={(event) =>
                  setDraft({ ...draft, name: event.target.value })
                }
              />
            </label>
            <label className="block space-y-1.5 text-sm font-medium">
              Description
              <Input
                maxLength={2000}
                value={draft.description}
                onChange={(event) =>
                  setDraft({ ...draft, description: event.target.value })
                }
              />
            </label>
            <DocumentFilters
              value={draft.filters || emptyFilters}
              taxonomy={taxonomy}
              onChange={(filters) => setDraft({ ...draft, filters })}
            />
            <label className="flex min-h-5 items-center gap-2 text-sm">
              <input
                type="checkbox"
                className={checkboxClass}
                checked={draft.shared}
                onChange={(event) =>
                  setDraft({ ...draft, shared: event.target.checked })
                }
              />
              Share this knowledge base
            </label>
            <label className="flex min-h-5 items-center gap-2 text-sm">
              <input
                type="checkbox"
                className={checkboxClass}
                checked={draft.local_only}
                onChange={(event) =>
                  setDraft({ ...draft, local_only: event.target.checked })
                }
              />
              Use local AI only
            </label>
            <p className="text-xs text-text-muted">
              Local AI keeps answers on your network. Restricted documents
              always follow your privacy rules, even when this option is off.
            </p>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="secondary"
                disabled={busy}
                onClick={() => setDraft(null)}
              >
                Cancel
              </Button>
              <Button disabled={busy}>
                {busy ? "Saving…" : "Save knowledge base"}
              </Button>
            </div>
          </form>
        </div>
      )}
      <div className="space-y-4">
        {items.map((base) => {
          const status = statuses[base.id];
          return (
            <article
              key={base.id}
              className="space-y-3 rounded-card border border-border bg-surface p-4"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <h2 className="break-words text-md font-semibold">
                    {base.name}
                  </h2>
                  <p className="break-words text-sm text-text-muted">
                    {base.description}
                  </p>
                </div>
                <span className="flex items-center gap-2 text-xs text-text-muted">
                  <LockKeyhole className="size-4" aria-hidden="true" />
                  {base.local_only
                    ? "Local AI only"
                    : "Configured AI routes"} ·{" "}
                  {base.shared ? "Shared scope" : "Private scope"}
                </span>
              </div>
              {status ? (
                <>
                  <dl className="flex flex-wrap gap-x-6 gap-y-2 text-sm tabular">
                    {[
                      ["Documents", status.documents],
                      ["Indexed", status.embedded],
                      ["Pending", status.pending],
                      ["Failed", status.failed],
                      ["Stale", status.stale],
                    ].map(([label, count]) => (
                      <div key={label}>
                        <dt className="text-xs text-text-muted">{label}</dt>
                        <dd>{count}</dd>
                      </div>
                    ))}
                  </dl>
                  <p className="flex items-center gap-2 text-xs text-text-muted">
                    {status.failed || status.stale ? (
                      <TriangleAlert className="size-4" aria-hidden="true" />
                    ) : status.pending ? (
                      <CircleDashed className="size-4" aria-hidden="true" />
                    ) : (
                      <CircleCheck className="size-4" aria-hidden="true" />
                    )}
                    {status.embedding_model
                      ? `Embedding model: ${status.embedding_model}.`
                      : "No embedding model configured."}{" "}
                    {status.last_indexed_at
                      ? `Last indexed ${new Date(status.last_indexed_at).toLocaleString()}.`
                      : "No documents indexed yet."}
                  </p>
                </>
              ) : (
                <p role="status" className="text-sm text-text-muted">
                  Indexing status unavailable. Refresh to check again.
                </p>
              )}
              {base.owner_id === userId && (
                <div className="flex flex-wrap items-center gap-2">
                  {confirmDelete === base.id ? (
                    <>
                      <p className="text-sm">
                        Delete “{base.name}”? Documents will be kept.
                      </p>
                      <Button
                        variant="secondary"
                        disabled={busy}
                        onClick={() => setConfirmDelete(null)}
                      >
                        Keep knowledge base
                      </Button>
                      <Button
                        variant="danger"
                        disabled={busy}
                        onClick={() => void remove(base.id)}
                      >
                        Confirm delete
                      </Button>
                    </>
                  ) : (
                    <>
                      <Button
                        variant="secondary"
                        aria-label={`Edit ${base.name}`}
                        disabled={busy}
                        onClick={() => start(base)}
                      >
                        Edit
                      </Button>
                      <Button
                        variant="ghost"
                        aria-label={`Delete ${base.name}`}
                        disabled={busy}
                        onClick={() => setConfirmDelete(base.id)}
                      >
                        Delete
                      </Button>
                    </>
                  )}
                </div>
              )}
            </article>
          );
        })}
      </div>
      {cursor && (
        <Button
          variant="secondary"
          disabled={loading}
          onClick={() => void load(cursor)}
        >
          Load more
        </Button>
      )}
      <details className="max-w-prose text-sm">
        <summary className="cursor-pointer font-medium">
          How was this made?
        </summary>
        <p className="mt-2 text-text-muted">
          Knowledge bases save filters over one index. Retrieval combines word
          matches and meaning matches by rank and limits chunks from each
          document. Indexing counts use only documents you can see.
        </p>
        <a
          className="mt-2 inline-block text-primary underline"
          href="https://github.com/d2k-klin/docuhive/blob/main/docs/learn/09-hybrid-search.md"
          target="_blank"
          rel="noreferrer"
        >
          Learn about hybrid retrieval
        </a>
      </details>
    </main>
  );
}
