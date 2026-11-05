"use client";

import { useState } from "react";
import { Plus, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { checkbox, control } from "@/lib/ui/control";
import {
  api,
  ApiError,
  Badge,
  Card,
  ErrorBox,
  Field,
  Skeleton,
  useApi,
} from "./common";

type Category = {
  id: string;
  label: string;
  description: string;
  restricted: boolean;
  enabled: boolean;
};
type Taxonomy = { categories: Category[]; preset_ids: string[] };

export function CategorySettings({ admin }: { admin: boolean }) {
  const taxonomy = useApi<Taxonomy>("/api/taxonomy");
  const [selection, setSelection] = useState<Set<string> | null>(null);
  const [label, setLabel] = useState("");
  const [description, setDescription] = useState("");
  const [parent, setParent] = useState("");
  const [restricted, setRestricted] = useState(false);
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [notice, setNotice] = useState("");
  const categories = taxonomy.data?.categories || [];
  const enabled =
    selection ||
    new Set(categories.filter((c) => c.enabled !== false).map((c) => c.id));

  function toggle(id: string, checked: boolean) {
    const next = new Set(enabled);
    for (const c of categories.filter(
      (c) => c.id === id || c.id.startsWith(`${id}/`),
    )) {
      if (checked) next.add(c.id);
      else next.delete(c.id);
    }
    if (checked) {
      const parts = id.split("/");
      for (let i = 1; i < parts.length; i++)
        next.add(parts.slice(0, i).join("/"));
    }
    setSelection(next);
    setNotice("");
  }

  async function save() {
    setBusy(true);
    setError(null);
    setNotice("");
    try {
      await api("/api/taxonomy/categories", {
        method: "PUT",
        json: { enabled_ids: [...enabled] },
      });
      taxonomy.reload();
      setSelection(null);
      setNotice(
        "Category choices saved for the whole archive. New AI analysis uses this list; existing assignments stay as they are.",
      );
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div id="categories" className="mb-6">
      <Card
        title="Document categories"
        actions={
          admin && (
            <Button variant="secondary" onClick={() => setAdding(!adding)}>
              <Plus aria-hidden="true" /> Add category
            </Button>
          )
        }
      >
        <p className="mb-4 max-w-prose text-sm text-text-muted">
          Choose the categories used across your archive, for uploads and
          automatic AI categorisation. Turn off categories you do not need.
          Their existing documents and privacy settings are kept.
        </p>
        {!admin && (
          <p className="mb-4 text-sm text-text-muted">
            An administrator can change this shared list.
          </p>
        )}
        {error && (
          <div className="mb-4">
            <ErrorBox error={error} />
          </div>
        )}
        {notice && (
          <p role="status" className="mb-4 text-sm text-success">
            {notice}
          </p>
        )}
        {taxonomy.error ? (
          <ErrorBox error={taxonomy.error} onRetry={taxonomy.reload} />
        ) : !taxonomy.data ? (
          <Skeleton rows={5} />
        ) : (
          <>
            {admin && (
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={busy}
                  onClick={() =>
                    setSelection(new Set(categories.map((c) => c.id)))
                  }
                >
                  Select all
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={busy}
                  onClick={() =>
                    setSelection(
                      new Set(
                        categories.some((c) => c.id === "other")
                          ? ["other"]
                          : [categories[0]?.id].filter(Boolean),
                      ),
                    )
                  }
                >
                  Clear optional categories
                </Button>
                <span className="text-xs text-text-muted">
                  {enabled.size} selected · Other stays available for documents
                  that do not fit.
                </span>
              </div>
            )}
            <div className="grid gap-x-6 gap-y-1 lg:grid-cols-2">
              {categories.map((c) => (
                <label
                  key={c.id}
                  className={`flex items-start gap-2 rounded py-2 hover:bg-surface-2 ${c.id.includes("/") ? "pl-6" : ""}`}
                >
                  <input
                    className={`${checkbox} mt-1`}
                    type="checkbox"
                    aria-label={`Use ${c.label}`}
                    checked={enabled.has(c.id)}
                    disabled={!admin || busy || c.id === "other"}
                    onChange={(e) => toggle(c.id, e.target.checked)}
                  />
                  <span className="min-w-0">
                    <span className="flex flex-wrap items-center gap-2">
                      <span
                        className={
                          c.id.includes("/") ? "text-sm" : "font-medium"
                        }
                      >
                        {c.id.includes("/")
                          ? `${categories.find((p) => p.id === c.id.slice(0, c.id.lastIndexOf("/")))?.label || ""} › ${c.label}`
                          : c.label}
                      </span>
                      {!taxonomy.data!.preset_ids.includes(c.id) && (
                        <Badge>Custom</Badge>
                      )}
                      {c.restricted && (
                        <span className="inline-flex items-center gap-1 text-xs text-text-muted">
                          <ShieldCheck aria-hidden="true" className="size-3" />{" "}
                          Local AI only
                        </span>
                      )}
                    </span>
                    {c.description && (
                      <span className="block text-xs text-text-muted">
                        {c.description}
                      </span>
                    )}
                  </span>
                </label>
              ))}
            </div>
            {admin && (
              <div className="mt-4 flex justify-end">
                <Button
                  disabled={busy || !selection}
                  onClick={() => void save()}
                >
                  {busy ? "Saving…" : "Save category choices"}
                </Button>
              </div>
            )}
          </>
        )}
        {adding && admin && (
          <form
            className="mt-6 max-w-2xl space-y-4 border-t border-border pt-4"
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError(null);
              setNotice("");
              try {
                const result = await api<Taxonomy>("/api/taxonomy/categories", {
                  method: "POST",
                  json: {
                    label,
                    description,
                    parent_id: parent || null,
                    restricted,
                  },
                });
                if (selection)
                  setSelection(
                    new Set([
                      ...selection,
                      ...result.categories
                        .filter(
                          (c) => !categories.some((old) => old.id === c.id),
                        )
                        .map((c) => c.id),
                    ]),
                  );
                taxonomy.reload();
                setAdding(false);
                setLabel("");
                setDescription("");
                setParent("");
                setRestricted(false);
                setNotice(
                  "Custom category added. It is available for uploads, filters and AI analysis.",
                );
              } catch (err) {
                setError(err as ApiError);
              } finally {
                setBusy(false);
              }
            }}
          >
            <h3 className="font-semibold">Add a custom category</h3>
            <div className="grid gap-4 lg:grid-cols-2">
              <Field label="Category name">
                <Input
                  required
                  maxLength={80}
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                  placeholder="For example, Home business"
                />
              </Field>
              <Field label="Parent category">
                <select
                  className={control}
                  value={parent}
                  onChange={(e) => setParent(e.target.value)}
                >
                  <option value="">No parent</option>
                  {categories
                    .filter((c) => c.enabled !== false)
                    .map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.label}
                      </option>
                    ))}
                </select>
              </Field>
            </div>
            <Field
              label="What belongs here?"
              help="Optional. Helps AI choose the right category."
            >
              <Input
                maxLength={400}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="For example, invoices and receipts for my home business"
              />
            </Field>
            <label className="flex items-center gap-2 text-sm">
              <input
                className={checkbox}
                type="checkbox"
                checked={restricted}
                onChange={(e) => setRestricted(e.target.checked)}
              />{" "}
              Keep documents in this category on local AI only
            </label>
            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="secondary"
                disabled={busy}
                onClick={() => setAdding(false)}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={busy || !label.trim()}>
                {busy ? "Adding…" : "Create category"}
              </Button>
            </div>
          </form>
        )}
      </Card>
    </div>
  );
}
