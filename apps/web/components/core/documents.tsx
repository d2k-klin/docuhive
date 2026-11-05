"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { DateShortcuts } from "./document-filters";
import {
  DocumentAIStatus,
  isAIWorking,
  useAIStatuses,
} from "@/components/intel/DocumentAIStatus";
import { FileText, LoaderCircle, ShieldAlert, Upload } from "lucide-react";
import type { components } from "@/lib/api/schema";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { checkbox, control } from "@/lib/ui/control";
import {
  api,
  ApiError,
  Badge,
  Empty,
  ErrorBox,
  Field,
  formatDate,
  Page,
  PageHeader,
  Skeleton,
  useApi,
} from "@/components/intel/common";

type DocumentPage = components["schemas"]["DocumentPage"];
type Pending = components["schemas"]["PendingDocument"];
type Taxonomy = components["schemas"]["Taxonomy"];

const MAX_BULK = 500; // BulkEdit.ids limit in the API

export type ListFilters = {
  category: string;
  document_type: string;
  tag: string;
  date_from: string;
  date_to: string;
};
const noFilters: ListFilters = {
  category: "",
  document_type: "",
  tag: "",
  date_from: "",
  date_to: "",
};

export function filterQuery(filters: ListFilters): URLSearchParams {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value.trim()) query.set(key, value.trim());
  }
  return query;
}

export function FilterBar({
  value,
  taxonomy,
  onChange,
}: {
  value: ListFilters;
  taxonomy: Taxonomy | null;
  onChange: (value: ListFilters) => void;
}) {
  const set =
    (key: keyof ListFilters) => (event: { target: { value: string } }) =>
      onChange({ ...value, [key]: event.target.value });
  return (
    <div
      className="flex flex-wrap items-end gap-2"
      role="group"
      aria-label="Filters"
    >
      <label className="w-full sm:w-52">
        <span className="sr-only">Category</span>
        <select
          className={control}
          value={value.category}
          onChange={set("category")}
        >
          <option value="">All categories</option>
          {taxonomy?.categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.label}
            </option>
          ))}
        </select>
      </label>
      <label className="w-full sm:w-44">
        <span className="sr-only">Document type</span>
        <select
          className={control}
          value={value.document_type}
          onChange={set("document_type")}
        >
          <option value="">All types</option>
          {taxonomy?.document_types.map((t) => (
            <option key={t.id} value={t.id}>
              {t.label}
            </option>
          ))}
        </select>
      </label>
      <label className="w-full sm:w-40">
        <span className="sr-only">Tag</span>
        <Input placeholder="Tag" value={value.tag} onChange={set("tag")} />
      </label>
      <label className="w-full sm:w-40">
        <span className="sr-only">From date</span>
        <Input
          type="date"
          value={value.date_from}
          onChange={set("date_from")}
        />
      </label>
      <label className="w-full sm:w-40">
        <span className="sr-only">To date</span>
        <Input type="date" value={value.date_to} onChange={set("date_to")} />
      </label>
      {Object.values(value).some(Boolean) && (
        <Button variant="ghost" onClick={() => onChange(noFilters)}>
          Clear filters
        </Button>
      )}
    </div>
  );
}

/** Category and type ids to their labels, e.g. "utilities/electricity" -> "Electricity". */
export function labelsOf(taxonomy: Taxonomy | null): Record<string, string> {
  const labels: Record<string, string> = {};
  for (const c of taxonomy?.categories || []) labels[c.id] = c.label;
  for (const t of taxonomy?.document_types || []) labels[t.id] = t.label;
  return labels;
}

export function DocumentTable({
  items,
  selected,
  onSelect,
  labels = {},
  link = true,
  onAIComplete,
}: {
  items: DocumentPage["items"];
  selected?: Set<string>;
  onSelect?: (ids: Set<string>) => void;
  labels?: Record<string, string>;
  /** Trashed documents have no detail page until they are restored. */
  link?: boolean;
  onAIComplete?: () => void;
}) {
  const progress = useAIStatuses(link ? items.map((d) => d.id) : []);
  const active = Object.values(progress.items).some(isAIWorking);
  const wasActive = useRef(false);
  useEffect(() => {
    if (wasActive.current && !active) onAIComplete?.();
    wasActive.current = active;
  }, [active, onAIComplete]);
  const toggle = (id: string) => {
    if (!selected || !onSelect) return;
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onSelect(next);
  };
  return (
    <div className="overflow-x-auto rounded-card border border-border bg-surface">
      <table className="w-full text-left text-base">
        {link && progress.error && (
          <caption className="p-3 text-left text-sm">
            AI progress could not be refreshed.{" "}
            <Button variant="ghost" size="sm" onClick={progress.reload}>
              Retry status
            </Button>
          </caption>
        )}
        <thead className="text-xs font-medium tracking-[0.02em] text-text-muted">
          <tr className="h-9 border-b border-border">
            {onSelect && (
              <th scope="col" className="w-10 px-3">
                <input
                  type="checkbox"
                  className={checkbox}
                  aria-label="Select all on this page"
                  checked={
                    items.length > 0 && items.every((d) => selected?.has(d.id))
                  }
                  onChange={(event) =>
                    onSelect(
                      new Set(
                        event.target.checked ? items.map((d) => d.id) : [],
                      ),
                    )
                  }
                />
              </th>
            )}
            {["Title", "Date", "Sender", "Category", "Tags"].map((label) => (
              <th key={label} scope="col" className="px-3 font-medium">
                {label}
              </th>
            ))}
            {link && (
              <th scope="col" className="px-3 font-medium">
                AI status
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {items.map((doc) => (
            <tr
              key={doc.id}
              className={
                "h-11 border-b border-border last:border-0 hover:bg-surface-2" +
                (selected?.has(doc.id)
                  ? " shadow-[inset_2px_0_0_var(--primary)]"
                  : "")
              }
            >
              {onSelect && (
                <td className="px-3">
                  <input
                    type="checkbox"
                    className={checkbox}
                    aria-label={`Select ${doc.title || "untitled document"}`}
                    checked={selected?.has(doc.id) || false}
                    onChange={() => toggle(doc.id)}
                  />
                </td>
              )}
              <td className="max-w-80 break-words px-3">
                {link ? (
                  <Link
                    href={`/documents/${doc.id}`}
                    className="hover:underline"
                  >
                    {doc.title || "Untitled document"}
                  </Link>
                ) : (
                  doc.title || "Untitled document"
                )}
              </td>
              <td className="whitespace-nowrap px-3 tabular">
                {formatDate(doc.document_date || doc.added_at.slice(0, 10))}
                {!doc.document_date && (
                  <span className="block text-xs text-text-muted">
                    Upload date
                  </span>
                )}
              </td>
              <td className="break-words px-3">{doc.correspondent || "—"}</td>
              <td className="break-words px-3">
                {progress.items[doc.id]?.category_label ||
                  (doc.category ? labels[doc.category] || doc.category : "—")}
              </td>
              <td className="break-words px-3 text-sm text-text-muted">
                {doc.tags.join(", ") || "—"}
              </td>
              {link && (
                <td className="px-3 py-2">
                  <DocumentAIStatus
                    status={progress.items[doc.id]}
                    unavailable={progress.error}
                  />
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PendingTitle({ title }: { title: string | null }) {
  return (
    <span className="min-w-0 max-w-48 truncate" title={title || undefined}>
      {title || "Untitled"}
    </span>
  );
}

function PendingStrip({ items }: { items: Pending[] }) {
  if (!items.length) return null;
  return (
    <section
      aria-label="Documents being processed"
      className="flex flex-wrap gap-2"
    >
      {items.slice(0, 8).map((doc) =>
        doc.status === "quarantined" ? (
          <Link
            key={doc.id}
            href="/quarantine"
            className="flex min-w-0 max-w-full items-center gap-2 text-sm"
          >
            <PendingTitle title={doc.title} />
            <Badge tone="error" icon={ShieldAlert}>
              Needs attention
            </Badge>
          </Link>
        ) : (
          <span
            key={doc.id}
            className="flex min-w-0 max-w-full items-center gap-2 text-sm"
          >
            <PendingTitle title={doc.title} />
            <Badge tone="info" icon={LoaderCircle}>
              {doc.status === "processing" ? "Reading text…" : "Waiting…"}
            </Badge>
          </span>
        ),
      )}
    </section>
  );
}

function BulkEdit({
  ids,
  taxonomy,
  onDone,
}: {
  ids: string[];
  taxonomy: Taxonomy | null;
  onDone: (message: string) => void;
}) {
  const [category, setCategory] = useState("");
  const [tagAdd, setTagAdd] = useState("");
  const [tagRemove, setTagRemove] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function apply() {
    setBusy(true);
    setError("");
    try {
      const patch = {
        category: category || null,
        tags_add: tagAdd.trim() ? [tagAdd.trim()] : [],
        tags_remove: tagRemove.trim() ? [tagRemove.trim()] : [],
      };
      let updated = 0;
      let skipped = 0;
      // The API takes at most MAX_BULK ids per request.
      for (let start = 0; start < ids.length; start += MAX_BULK) {
        const result = await api<{ updated: number; skipped: string[] }>(
          "/api/documents/bulk",
          {
            method: "POST",
            json: { ids: ids.slice(start, start + MAX_BULK), patch },
          },
        );
        updated += result.updated;
        skipped += result.skipped.length;
      }
      onDone(
        `Updated ${updated} documents` +
          (skipped ? `; ${skipped} are not yours to change` : ""),
      );
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section
      aria-label="Edit selected documents"
      className="flex flex-wrap items-end gap-2 rounded-card border border-border bg-surface p-4"
    >
      <p className="w-full text-sm font-medium">
        Change {ids.length} selected documents
      </p>
      <label className="w-full sm:w-52">
        <span className="sr-only">Category</span>
        <select
          className={control}
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        >
          <option value="">Keep category</option>
          {taxonomy?.categories
            .filter((c) => c.enabled !== false)
            .map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
        </select>
      </label>
      <label className="w-full sm:w-40">
        <span className="sr-only">Add tag</span>
        <Input
          placeholder="Add tag"
          value={tagAdd}
          onChange={(e) => setTagAdd(e.target.value)}
        />
      </label>
      <label className="w-full sm:w-40">
        <span className="sr-only">Remove tag</span>
        <Input
          placeholder="Remove tag"
          value={tagRemove}
          onChange={(e) => setTagRemove(e.target.value)}
        />
      </label>
      <Button
        disabled={busy || !(category || tagAdd.trim() || tagRemove.trim())}
        onClick={() => void apply()}
      >
        {busy ? "Saving…" : `Apply to ${ids.length} documents`}
      </Button>
      {error && (
        <p role="alert" className="w-full text-sm text-danger">
          {error}
        </p>
      )}
    </section>
  );
}

export function Documents() {
  const router = useRouter();
  const [viewName, setViewName] = useState<string | null>(null);
  const [savingView, setSavingView] = useState(false);
  const [viewError, setViewError] = useState<ApiError | null>(null);
  const [filters, setFilters] = useState<ListFilters>(noFilters);
  const [offset, setOffset] = useState(0);
  const [extra, setExtra] = useState<DocumentPage["items"]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [notice, setNotice] = useState("");
  const query = filterQuery(filters);
  query.set("offset", String(offset));
  const page = useApi<DocumentPage>(`/api/documents?${query}`);
  const pending = useApi<Pending[]>("/api/documents/pending");
  const taxonomy = useApi<Taxonomy>("/api/taxonomy");
  const items = offset
    ? [...extra, ...(page.data?.items || [])]
    : page.data?.items || [];
  const filtered = Object.values(filters).some(Boolean);
  const { reload: reloadPage } = page;
  const { reload: reloadPending } = pending;
  const hasPending = !!pending.data?.length;
  const hadPending = useRef(false);
  useEffect(() => {
    if (hadPending.current && !hasPending) reloadPage();
    hadPending.current = hasPending;
    if (!hasPending) return;
    const timer = setInterval(() => {
      reloadPage();
      reloadPending();
    }, 2500);
    return () => clearInterval(timer);
  }, [hasPending, reloadPage, reloadPending]);
  function changeFilters(next: ListFilters) {
    setFilters(next);
    setOffset(0);
    setExtra([]);
    setSelected(new Set());
  }
  return (
    <Page>
      <PageHeader
        title="Documents"
        description={
          page.data
            ? `${page.data.total} ${filtered ? "matching documents" : "documents in your archive"}`
            : "Your archive"
        }
        actions={
          <>
            <Button asChild variant="secondary">
              <Link href="/vocabulary#categories">Categories</Link>
            </Button>
            <Button asChild>
              <Link href="/upload">
                <Upload aria-hidden="true" />
                Upload
              </Link>
            </Button>
          </>
        }
      />
      <div className="space-y-4">
        <PendingStrip items={pending.data || []} />
        <FilterBar
          value={filters}
          taxonomy={taxonomy.data}
          onChange={changeFilters}
        />
        <div className="flex flex-wrap items-center gap-2">
          <DateShortcuts
            value={filters}
            onChange={(range) => changeFilters({ ...filters, ...range })}
          />
          {filtered && (
            <Button
              variant="secondary"
              onClick={() =>
                setViewName(
                  `${labelsOf(taxonomy.data)[filters.category] || "Documents"}${filters.date_from ? ` · ${filters.date_from} to ${filters.date_to}` : ""}`,
                )
              }
            >
              Save this view
            </Button>
          )}
        </div>
        <p className="text-xs text-text-muted">
          Categories include their subcategories. Dates use the date on the
          document, or the upload date if missing.
        </p>
        {viewError && <ErrorBox error={viewError} />}
        {viewName !== null && (
          <form
            className="flex flex-wrap items-end gap-3 rounded-card border border-border bg-surface p-4"
            onSubmit={async (e) => {
              e.preventDefault();
              setSavingView(true);
              setViewError(null);
              try {
                await api("/api/views", {
                  method: "POST",
                  json: {
                    name: viewName,
                    pinned: true,
                    shared: false,
                    filters: {
                      categories: filters.category ? [filters.category] : [],
                      document_types: filters.document_type
                        ? [filters.document_type]
                        : [],
                      tags: filters.tag ? [filters.tag] : [],
                      date_from: filters.date_from || null,
                      date_to: filters.date_to || null,
                    },
                  },
                });
                setViewName(null);
                setNotice(
                  "View saved. Open it from the sidebar whenever you need it.",
                );
                router.refresh();
              } catch (err) {
                setViewError(err as ApiError);
              } finally {
                setSavingView(false);
              }
            }}
          >
            <Field label="View name">
              <Input
                required
                maxLength={100}
                value={viewName}
                onChange={(e) => setViewName(e.target.value)}
              />
            </Field>
            <Button
              type="button"
              variant="secondary"
              disabled={savingView}
              onClick={() => setViewName(null)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={savingView || !viewName.trim()}>
              {savingView ? "Saving…" : "Save view"}
            </Button>
          </form>
        )}
        {notice && (
          <p role="status" className="text-sm text-text">
            {notice}
          </p>
        )}
        {selected.size > 0 && (
          <BulkEdit
            ids={[...selected]}
            taxonomy={taxonomy.data}
            onDone={(message) => {
              setNotice(message);
              setSelected(new Set());
              setOffset(0);
              setExtra([]);
              page.reload();
            }}
          />
        )}
        {page.error ? (
          <ErrorBox error={page.error} onRetry={page.reload} />
        ) : page.loading && !items.length ? (
          <Skeleton rows={6} />
        ) : !items.length ? (
          <Empty
            icon={FileText}
            text={
              filtered
                ? "No documents match these filters."
                : "Your archive is empty. Upload a document, or connect a mailbox or scanner folder."
            }
            action={
              filtered ? (
                <Button
                  variant="secondary"
                  onClick={() => changeFilters(noFilters)}
                >
                  Clear filters
                </Button>
              ) : (
                <Button asChild>
                  <Link href="/upload">Upload documents</Link>
                </Button>
              )
            }
          />
        ) : (
          <DocumentTable
            items={items}
            selected={selected}
            onSelect={setSelected}
            labels={labelsOf(taxonomy.data)}
            onAIComplete={page.reload}
          />
        )}
        {page.data?.next_offset != null && (
          <Button
            variant="secondary"
            disabled={page.loading}
            onClick={() => {
              setExtra(items);
              setOffset(page.data?.next_offset || 0);
            }}
          >
            {page.loading ? "Loading…" : "Load more"}
          </Button>
        )}
      </div>
    </Page>
  );
}

export { Field };
