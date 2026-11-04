"use client";

import { useState } from "react";
import { ListPlus, TriangleAlert } from "lucide-react";
import { browserClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { errorMessage } from "@/lib/i18n/errors";
import { checkbox as checkboxClass, control } from "@/lib/ui/control";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type Field = components["schemas"]["CustomFieldView"];
type Draft = components["schemas"]["CustomFieldInput"];
type DocumentType = components["schemas"]["DocumentType"];
const api = browserClient();
const types: { id: Draft["type"]; label: string }[] = [
  { id: "string", label: "Text" },
  { id: "date", label: "Date" },
  { id: "money", label: "Amount" },
  { id: "number", label: "Number" },
  { id: "iban", label: "IBAN" },
];
const empty: Draft = {
  name: "",
  label: "",
  type: "string",
  description: "",
  document_types: [],
  remind_days_before: [],
};

/** "Warranty end" -> "warranty_end", the name extracted values are stored under. */
function slug(label: string) {
  return label
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^[^a-z]+|_+$/g, "")
    .slice(0, 60);
}

export function CustomFields({
  admin,
  initial,
  documentTypes,
}: {
  admin: boolean;
  initial: Field[] | null;
  documentTypes: DocumentType[] | null;
}) {
  const [items, setItems] = useState<Field[]>(initial || []);
  const [error, setError] = useState(
    initial && documentTypes
      ? ""
      : "Custom fields could not be loaded. Try again.",
  );
  const [draft, setDraft] = useState<Draft | null>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const [days, setDays] = useState("");
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const typeLabel = Object.fromEntries(
    (documentTypes || []).map((t) => [t.id, t.label]),
  );

  async function load() {
    setError("");
    const response = await api.GET("/api/custom-fields").catch(() => null);
    if (!response?.data) {
      setError("Custom fields could not be loaded. Try again.");
      return;
    }
    setItems(response.data);
  }
  function start(field?: Field) {
    setEditing(field?.id ?? null);
    setDraft(field || empty);
    setDays((field?.remind_days_before || []).join(", "));
    setError("");
  }
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!draft) return;
    const remind = days
      .split(",")
      .map((value) => Number(value.trim()))
      .filter((value) => Number.isInteger(value) && value > 0);
    const body = {
      ...draft,
      name: draft.name || slug(draft.label),
      remind_days_before: draft.type === "date" ? remind : [],
    };
    setBusy(true);
    setError("");
    try {
      const response =
        editing === null
          ? await api.POST("/api/custom-fields", { body })
          : await api.PATCH("/api/custom-fields/{field_id}", {
              params: { path: { field_id: editing } },
              body: {
                label: body.label,
                description: body.description,
                document_types: body.document_types,
                remind_days_before: body.remind_days_before,
              },
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
      setError("The field could not be saved. Try again.");
    } finally {
      setBusy(false);
    }
  }
  async function remove(id: number) {
    setBusy(true);
    setError("");
    try {
      const response = await api.DELETE("/api/custom-fields/{field_id}", {
        params: { path: { field_id: id } },
      });
      if (!response.response.ok) throw new Error();
      setConfirmDelete(null);
      await load();
    } catch {
      setError("The field could not be deleted. Try again.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="mx-auto max-w-screen-xl space-y-6 p-4 md:p-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Custom fields</h1>
          <p className="text-sm text-text-muted">
            Details you want pulled from documents, next to the built-in ones.
          </p>
        </div>
        {admin && (
          <Button disabled={!documentTypes || busy} onClick={() => start()}>
            Add field
          </Button>
        )}
      </header>
      <p className="max-w-prose text-sm text-text-muted">
        The AI fills these in for new documents, they appear in review when it
        is unsure, and Ask can answer questions about them.
        {!admin && " Only an administrator can add or change them."}
      </p>
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
          <ListPlus className="size-5" aria-hidden="true" />
          <h2 className="text-md font-semibold">No custom fields yet</h2>
          <p className="text-sm text-text-muted">
            Add one, such as “Warranty end” or “Policy number”.
          </p>
        </div>
      )}
      {draft && documentTypes && (
        <div className="rounded-card border border-border bg-surface p-4">
          <form className="max-w-prose space-y-4" onSubmit={save}>
            <h2 className="text-md font-semibold">
              {editing === null ? "Add field" : "Edit field"}
            </h2>
            <label className="block space-y-1.5 text-sm font-medium">
              Label
              <Input
                required
                maxLength={100}
                value={draft.label}
                onChange={(event) =>
                  setDraft({ ...draft, label: event.target.value })
                }
              />
            </label>
            {editing === null && (
              <label className="block space-y-1.5 text-sm font-medium">
                Type
                <select
                  className={control}
                  value={draft.type}
                  onChange={(event) =>
                    setDraft({
                      ...draft,
                      type: event.target.value as Draft["type"],
                    })
                  }
                >
                  {types.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.label}
                    </option>
                  ))}
                </select>
                <span className="block text-xs font-normal text-text-muted">
                  The type can’t be changed later.
                </span>
              </label>
            )}
            <label className="block space-y-1.5 text-sm font-medium">
              Hint for the AI
              <Input
                maxLength={500}
                value={draft.description}
                placeholder="For example: the date the manufacturer warranty ends"
                onChange={(event) =>
                  setDraft({ ...draft, description: event.target.value })
                }
              />
            </label>
            <fieldset className="space-y-2">
              <legend className="mb-2 text-sm font-medium">
                Document types
              </legend>
              <p className="text-xs text-text-muted">
                Leave all unchecked to look for this field in every document
                type.
              </p>
              <div className="flex max-h-48 flex-wrap gap-x-6 gap-y-2 overflow-auto">
                {documentTypes.map((t) => (
                  <label
                    key={t.id}
                    className="flex min-h-5 items-center gap-2 text-sm"
                  >
                    <input
                      type="checkbox"
                      className={checkboxClass}
                      checked={(draft.document_types || []).includes(t.id)}
                      onChange={(event) =>
                        setDraft({
                          ...draft,
                          document_types: event.target.checked
                            ? [...(draft.document_types || []), t.id]
                            : (draft.document_types || []).filter(
                                (id) => id !== t.id,
                              ),
                        })
                      }
                    />
                    {t.label}
                  </label>
                ))}
              </div>
            </fieldset>
            {draft.type === "date" && (
              <label className="block space-y-1.5 text-sm font-medium">
                Remind me (days before)
                <Input
                  inputMode="numeric"
                  value={days}
                  placeholder="30, 7"
                  onChange={(event) => setDays(event.target.value)}
                />
                <span className="block text-xs font-normal text-text-muted">
                  Up to five numbers between 1 and 365, separated by commas.
                </span>
              </label>
            )}
            <div className="flex gap-2">
              <Button
                type="button"
                variant="secondary"
                disabled={busy}
                onClick={() => setDraft(null)}
              >
                Cancel
              </Button>
              <Button disabled={busy}>{busy ? "Saving…" : "Save field"}</Button>
            </div>
          </form>
        </div>
      )}
      <ul className="space-y-3">
        {items.map((field) => (
          <li
            key={field.id}
            className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-border bg-surface p-4"
          >
            <div className="min-w-0">
              <h2 className="break-words text-md font-semibold">
                {field.label}
              </h2>
              <p className="break-words text-xs text-text-muted">
                {types.find((t) => t.id === field.type)?.label} ·{" "}
                {field.document_types?.length
                  ? field.document_types
                      .map((id) => typeLabel[id] || id)
                      .join(", ")
                  : "All document types"}
                {field.remind_days_before?.length
                  ? ` · Reminders ${field.remind_days_before.join(", ")} days before`
                  : ""}
              </p>
            </div>
            {admin && (
              <div className="flex flex-wrap items-center gap-2">
                {confirmDelete === field.id ? (
                  <>
                    <p className="text-sm">
                      Delete “{field.label}”? Values already found stay on their
                      documents.
                    </p>
                    <Button
                      variant="secondary"
                      disabled={busy}
                      onClick={() => setConfirmDelete(null)}
                    >
                      Keep field
                    </Button>
                    <Button
                      variant="danger"
                      disabled={busy}
                      onClick={() => void remove(field.id)}
                    >
                      Confirm delete
                    </Button>
                  </>
                ) : (
                  <>
                    <Button
                      variant="secondary"
                      aria-label={`Edit ${field.label}`}
                      disabled={busy}
                      onClick={() => start(field)}
                    >
                      Edit
                    </Button>
                    <Button
                      variant="ghost"
                      aria-label={`Delete ${field.label}`}
                      disabled={busy}
                      onClick={() => setConfirmDelete(field.id)}
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
