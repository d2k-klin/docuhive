"use client";

import Link from "next/link";
import { useState } from "react";
import {
  FileText,
  LoaderCircle,
  ShieldAlert,
  Upload,
} from "lucide-react";
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
  const set = (key: keyof ListFilters) => (event: { target: { value: string } }) =>
    onChange({ ...value, [key]: event.target.value });
  return (
    <div className="flex flex-wrap items-end gap-2" role="group" aria-label="Filters">
      <label className="w-full sm:w-52">
        <span className="sr-only">Category</span>
        <select className={control} value={value.category} onChange={set("category")}>
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
        <Input type="date" value={value.date_from} onChange={set("date_from")} />
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

export function DocumentTable({
  items,
  selected,
  onSelect,
}: {
  items: DocumentPage["items"];
  selected?: Set<string>;
  onSelect?: (ids: Set<string>) => void;
}) {
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
        <thead className="text-xs font-medium tracking-[0.02em] text-text-muted">
          <tr className="h-9 border-b border-border">
            {onSelect && (
              <th scope="col" className="w-10 px-3">
                <input
                  type="checkbox"
                  className={checkbox}
                  aria-label="Select all on this page"
                  checked={items.length > 0 && items.every((d) => selected?.has(d.id))}
                  onChange={(event) =>
                    onSelect(new Set(event.target.checked ? items.map((d) => d.id) : []))
                  }
                />
              </th>
            )}
            {["Title", "Date", "Sender", "Category", "Tags"].map((label) => (
              <th key={label} scope="col" className="px-3 font-medium">
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((doc) => (
            <tr
              key={doc.id}
              className={
                "h-11 border-b border-border last:border-0 hover:bg-surface-2" +
                (selected?.has(doc.id) ? " shadow-[inset_2px_0_0_var(--primary)]" : "")
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
                <Link href={`/documents/${doc.id}`} className="hover:underline">
                  {doc.title || "Untitled document"}
                </Link>
              </td>
              <td className="whitespace-nowrap px-3 tabular">
                {doc.document_date ? formatDate(doc.document_date) : "No date"}
              </td>
              <td className="break-words px-3">{doc.correspondent || "—"}</td>
              <td className="break-words px-3">{doc.category || "—"}</td>
              <td className="break-words px-3 text-sm text-text-muted">
                {doc.tags.join(", ") || "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PendingStrip({ items }: { items: Pending[] }) {
  if (!items.length) return null;
  return (
    <section aria-label="Documents being processed" className="flex flex-wrap gap-2">
      {items.slice(0, 8).map((doc) =>
        doc.status === "quarantined" ? (
          <Link key={doc.id} href="/quarantine">
            <Badge tone="error" icon={ShieldAlert}>
              {doc.title || "Untitled"}: needs attention
            </Badge>
          </Link>
        ) : (
          <Badge key={doc.id} tone="info" icon={LoaderCircle}>
            {doc.title || "Untitled"}: {doc.status === "processing" ? "Reading text…" : "Waiting…"}
          </Badge>
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
      const result = await api<{ updated: number; skipped: string[] }>("/api/documents/bulk", {
        method: "POST",
        json: {
          ids,
          patch: {
            category: category || null,
            tags_add: tagAdd.trim() ? [tagAdd.trim()] : [],
            tags_remove: tagRemove.trim() ? [tagRemove.trim()] : [],
          },
        },
      });
      onDone(
        `Updated ${result.updated} documents` +
          (result.skipped.length ? `; ${result.skipped.length} are not yours to change` : ""),
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
      <p className="w-full text-sm font-medium">Change {ids.length} selected documents</p>
      <label className="w-full sm:w-52">
        <span className="sr-only">Category</span>
        <select className={control} value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">Keep category</option>
          {taxonomy?.categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.label}
            </option>
          ))}
        </select>
      </label>
      <label className="w-full sm:w-40">
        <span className="sr-only">Add tag</span>
        <Input placeholder="Add tag" value={tagAdd} onChange={(e) => setTagAdd(e.target.value)} />
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
  const items = offset ? [...extra, ...(page.data?.items || [])] : page.data?.items || [];
  const filtered = Object.values(filters).some(Boolean);
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
        description={page.data ? `${page.data.total} documents in your archive` : "Your archive"}
        actions={
          <Button asChild>
            <Link href="/upload">
              <Upload aria-hidden="true" />
              Upload
            </Link>
          </Button>
        }
      />
      <div className="space-y-4">
        <PendingStrip items={pending.data || []} />
        <FilterBar value={filters} taxonomy={taxonomy.data} onChange={changeFilters} />
        {notice && (
          <p role="status" className="text-sm text-success">
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
                <Button variant="secondary" onClick={() => changeFilters(noFilters)}>
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
          <DocumentTable items={items} selected={selected} onSelect={setSelected} />
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
