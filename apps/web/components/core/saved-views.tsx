"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Bookmark, TriangleAlert } from "lucide-react";
import { browserClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { errorMessage } from "@/lib/i18n/errors";
import { checkbox as checkboxClass } from "@/lib/ui/control";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DocumentFilters, emptyFilters } from "./document-filters";

type View = components["schemas"]["SavedViewView"];
type Draft = components["schemas"]["SavedViewInput"];
type Taxonomy = components["schemas"]["Taxonomy"];
const api = browserClient();
const empty: Draft = {
  name: "",
  filters: emptyFilters,
  pinned: true,
  shared: false,
};

export function SavedViews({
  userId,
  initial,
  taxonomy,
}: {
  userId: number;
  initial: View[] | null;
  taxonomy: Taxonomy | null;
}) {
  const router = useRouter();
  const [items, setItems] = useState<View[]>(initial || []);
  const [error, setError] = useState(
    initial && taxonomy ? "" : "Saved views could not be loaded. Try again.",
  );
  const [draft, setDraft] = useState<Draft | null>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    setError("");
    const response = await api.GET("/api/views").catch(() => null);
    if (!response?.data) {
      setError("Saved views could not be loaded. Try again.");
      return;
    }
    setItems(response.data);
    router.refresh(); // the sidebar lists pinned views
  }
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!draft) return;
    setBusy(true);
    setError("");
    const body: Draft = {
      ...draft,
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
          ? await api.POST("/api/views", { body })
          : await api.PATCH("/api/views/{view_id}", {
              params: { path: { view_id: editing } },
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
      setError("The view could not be saved. Try again.");
    } finally {
      setBusy(false);
    }
  }
  async function remove(id: number) {
    setBusy(true);
    setError("");
    try {
      const response = await api.DELETE("/api/views/{view_id}", {
        params: { path: { view_id: id } },
      });
      if (!response.response.ok) throw new Error();
      setConfirmDelete(null);
      await load();
    } catch {
      setError("The view could not be deleted. Try again.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="mx-auto max-w-screen-xl space-y-6 p-4 md:p-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Saved views</h1>
          <p className="text-sm text-text-muted">
            Keep the filters you use often one click away in the sidebar.
          </p>
        </div>
        <Button
          disabled={!taxonomy || busy}
          onClick={() => {
            setEditing(null);
            setDraft(empty);
          }}
        >
          Create view
        </Button>
      </header>
      {error && (
        <div
          role="alert"
          className="flex flex-wrap items-center gap-2 text-sm text-danger"
        >
          <TriangleAlert className="size-4" aria-hidden="true" />
          {error}
          {!draft && (
            <Button variant="secondary" onClick={() => void load()}>
              Retry loading
            </Button>
          )}
        </div>
      )}
      {!error && !items.length && !draft && (
        <div className="space-y-2 rounded-card border border-border bg-surface p-4">
          <Bookmark className="size-5" aria-hidden="true" />
          <h2 className="text-md font-semibold">No saved views yet</h2>
          <p className="text-sm text-text-muted">
            Create one, such as “Unpaid invoices” or “Car”, to pin it to the
            sidebar.
          </p>
        </div>
      )}
      {draft && taxonomy && (
        <div className="rounded-card border border-border bg-surface p-4">
          <form className="max-w-prose space-y-4" onSubmit={save}>
            <h2 className="text-md font-semibold">
              {editing === null ? "Create view" : "Edit view"}
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
            <DocumentFilters
              value={draft.filters || emptyFilters}
              taxonomy={taxonomy}
              onChange={(filters) => setDraft({ ...draft, filters })}
            />
            <label className="flex min-h-5 items-center gap-2 text-sm">
              <input
                type="checkbox"
                className={checkboxClass}
                checked={draft.pinned}
                onChange={(event) =>
                  setDraft({ ...draft, pinned: event.target.checked })
                }
              />
              Pin to the sidebar
            </label>
            <label className="flex min-h-5 items-center gap-2 text-sm">
              <input
                type="checkbox"
                className={checkboxClass}
                checked={draft.shared}
                onChange={(event) =>
                  setDraft({ ...draft, shared: event.target.checked })
                }
              />
              Share this view with the household
            </label>
            <p className="text-xs text-text-muted">
              Sharing shares the filter. Everyone still sees only documents they
              can already open.
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
              <Button disabled={busy}>{busy ? "Saving…" : "Save view"}</Button>
            </div>
          </form>
        </div>
      )}
      <ul className="space-y-3">
        {items.map((view) => (
          <li
            key={view.id}
            className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-border bg-surface p-4"
          >
            <div className="min-w-0">
              <Link
                href={`/views/${view.id}`}
                className="break-words text-md font-semibold text-primary hover:underline"
              >
                {view.name}
              </Link>
              <p className="text-xs text-text-muted">
                {view.pinned ? "Pinned" : "Not pinned"} ·{" "}
                {view.shared ? "Shared" : "Private"}
                {view.owner_id !== userId && " · Shared with you"}
              </p>
            </div>
            {view.owner_id === userId && (
              <div className="flex flex-wrap items-center gap-2">
                {confirmDelete === view.id ? (
                  <>
                    <p className="text-sm">
                      Delete “{view.name}”? Documents will be kept.
                    </p>
                    <Button
                      variant="secondary"
                      disabled={busy}
                      onClick={() => setConfirmDelete(null)}
                    >
                      Keep view
                    </Button>
                    <Button
                      variant="danger"
                      disabled={busy}
                      onClick={() => void remove(view.id)}
                    >
                      Confirm delete
                    </Button>
                  </>
                ) : (
                  <>
                    <Button
                      variant="secondary"
                      aria-label={`Edit ${view.name}`}
                      disabled={busy}
                      onClick={() => {
                        setEditing(view.id);
                        setDraft(view);
                      }}
                    >
                      Edit
                    </Button>
                    <Button
                      variant="ghost"
                      aria-label={`Delete ${view.name}`}
                      disabled={busy}
                      onClick={() => setConfirmDelete(view.id)}
                    >
                      Delete
                    </Button>
                  </>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
    </main>
  );
}
