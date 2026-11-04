"use client";

import * as React from "react";
import Link from "next/link";
import { Check, Inbox, Keyboard, Pencil, Sparkles, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  api,
  ApiError,
  Badge,
  Card,
  Empty,
  ErrorBox,
  fieldLabel,
  formatDate,
  Meter,
  Page,
  PageHeader,
  Skeleton,
  useApi,
} from "@/components/intel/common";
import { control } from "@/lib/ui/control";

type Item = {
  id: number;
  kind: "field" | "new_term" | "notice";
  field: string | null;
  suggested: { value?: unknown; currency?: string; type?: string } | null;
  current: unknown;
  confidence: number | null;
  reason: string | null;
  evidence: string | null;
  ai_run_id: number | null;
};
type Group = {
  document: {
    id: string;
    title: string | null;
    document_date: string | null;
    thumbnail_url: string;
    can_resolve: boolean;
  };
  items: Item[];
};
type Taxonomy = {
  categories: { id: string; label: string }[];
  document_types: { id: string; label: string }[];
};

function show(v: unknown): string {
  if (v === null || v === undefined || v === "") return "–";
  if (Array.isArray(v)) return v.length ? v.join(", ") : "–";
  if (typeof v === "object") {
    const o = v as { value?: unknown; currency?: string };
    return [o.value, o.currency].filter(Boolean).join(" ") || "–";
  }
  return String(v);
}

function Editor({
  item,
  tax,
  onSave,
  onCancel,
}: {
  item: Item;
  tax: Taxonomy | null;
  onSave: (value: unknown, currency?: string) => void;
  onCancel: () => void;
}) {
  const s = item.suggested ?? {};
  const [value, setValue] = React.useState(String(s.value ?? ""));
  const [currency, setCurrency] = React.useState(s.currency ?? "EUR");
  const field = item.field ?? "";
  const options =
    field === "category" ? tax?.categories : field === "document_type" ? tax?.document_types : null;
  const isDate = field === "document_date" || s.type === "date";
  return (
    <form
      className="mt-2 flex flex-wrap items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        onSave(field === "tags" ? value.split(",").map((t) => t.trim()).filter(Boolean) : value,
          s.type === "money" ? currency : undefined);
      }}
    >
      {options ? (
        <select aria-label={fieldLabel(field)} className={`${control} max-w-xs`} value={value}
          onChange={(e) => setValue(e.target.value)} autoFocus>
          {options.map((o) => (
            <option key={o.id} value={o.id}>{o.label} ({o.id})</option>
          ))}
        </select>
      ) : (
        <Input aria-label={fieldLabel(field)} type={isDate ? "date" : "text"}
          inputMode={s.type === "money" || s.type === "number" ? "decimal" : undefined}
          className="max-w-xs [color-scheme:light] dark:[color-scheme:dark]" value={value}
          onChange={(e) => setValue(e.target.value)} autoFocus />
      )}
      {s.type === "money" && (
        <Input aria-label="Currency" className="w-20" maxLength={3} value={currency}
          onChange={(e) => setCurrency(e.target.value.toUpperCase())} />
      )}
      <Button type="submit">Save</Button>
      <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
    </form>
  );
}

export default function ReviewPage() {
  const queue = useApi<{ items: Group[] }>("/api/review/queue?limit=50");
  const { data: tax } = useApi<Taxonomy>("/api/taxonomy");
  const [index, setIndex] = React.useState(0);
  const [focus, setFocus] = React.useState(0);
  const [editing, setEditing] = React.useState<number | null>(null);
  const [error, setError] = React.useState<ApiError | null>(null);
  const [snippet, setSnippet] = React.useState<string | null>(null);
  const [help, setHelp] = React.useState(false);
  const groups = React.useMemo(() => queue.data?.items ?? [], [queue.data]);
  const group = groups[Math.min(index, Math.max(0, groups.length - 1))];
  const fields = group?.items.filter((i) => i.kind === "field") ?? [];

  // Prefetch the next 3 previews so moving on feels instant.
  React.useEffect(() => {
    groups.slice(index + 1, index + 4).forEach((g) => {
      const img = new Image();
      img.src = g.document.thumbnail_url;
    });
  }, [groups, index]);

  const drop = React.useCallback(
    (ids: number[]) => {
      const before = queue.data; // capture for revert on failure
      queue.setData((d) =>
        d && {
          items: d.items
            .map((g) => ({ ...g, items: g.items.filter((i) => !ids.includes(i.id)) }))
            .filter((g) => g.items.length),
        },
      );
      return () => queue.setData(before);
    },
    [queue],
  );

  const act = React.useCallback(
    async (ids: number[], call: () => Promise<unknown>) => {
      setError(null);
      const revert = drop(ids);
      try {
        const res = await call();
        if (res && typeof res === "object" && "snippet" in res)
          setSnippet((res as { snippet: string }).snippet);
      } catch (e) {
        revert();
        setError(e as ApiError);
      }
      setEditing(null);
    },
    [drop],
  );

  const accept = (item: Item, value?: unknown, currency?: string) =>
    act([item.id], () =>
      item.kind === "new_term"
        ? api(`/api/review/terms/${item.id}/accept`, { method: "POST" })
        : api(`/api/review/items/${item.id}/accept`, {
            method: "POST",
            json: value === undefined ? {} : { value, currency },
          }),
    );
  const reject = (item: Item) =>
    act([item.id], () => api(`/api/review/items/${item.id}/reject`, { method: "POST" }));
  const acceptAll = () =>
    group &&
    act(fields.map((i) => i.id), () =>
      api(`/api/review/documents/${group.document.id}/accept-all`, { method: "POST" }),
    );
  const rejectAll = () =>
    group &&
    act(fields.map((i) => i.id), () =>
      api(`/api/review/documents/${group.document.id}/reject-all`, { method: "POST" }),
    );

  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement;
      if (["INPUT", "SELECT", "TEXTAREA"].includes(t.tagName) || e.metaKey || e.ctrlKey) return;
      if (e.key === "j") setIndex((i) => Math.min(i + 1, groups.length - 1));
      else if (e.key === "k") setIndex((i) => Math.max(i - 1, 0));
      else if (e.key === "a" && group?.document.can_resolve) acceptAll();
      else if (e.key === "r" && group?.document.can_resolve) rejectAll();
      else if (e.key === "e" && fields[focus]) setEditing(fields[focus].id);
      else if (e.key === "?") setHelp((h) => !h);
      else if (/^[1-9]$/.test(e.key)) {
        const it = fields[Number(e.key) - 1];
        if (it && group?.document.can_resolve) {
          setFocus(Number(e.key) - 1);
          accept(it);
        }
      } else return;
      e.preventDefault();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <Page>
      <PageHeader
        title="Review"
        description="Check what the AI suggested. Accepted values are locked against future AI changes."
        actions={
          <Button variant="ghost" onClick={() => setHelp((h) => !h)} aria-expanded={help}>
            <Keyboard aria-hidden="true" /> Shortcuts
          </Button>
        }
      />
      {help && (
        <Card className="mb-4">
          <p className="text-sm text-text-muted">
            <kbd>j</kbd>/<kbd>k</kbd> next/previous document · <kbd>a</kbd> accept all ·{" "}
            <kbd>r</kbd> reject all · <kbd>1</kbd>–<kbd>9</kbd> accept a suggestion ·{" "}
            <kbd>e</kbd> edit the focused suggestion · <kbd>?</kbd> this help
          </p>
        </Card>
      )}
      {error && <div className="mb-4"><ErrorBox error={error} /></div>}
      {snippet && (
        <Card title="Add this to overlay/taxonomy.yaml" className="mb-4"
          actions={<Button variant="ghost" size="sm" onClick={() => setSnippet(null)}>Close</Button>}>
          <p className="mb-2 text-sm text-text-muted">
            DocuHive cannot change your private overlay. Add this so the AI can use the term next time.
          </p>
          <pre className="overflow-x-auto rounded bg-surface-2 p-3 font-mono text-sm">{snippet}</pre>
        </Card>
      )}
      {queue.loading && !queue.data ? (
        <Skeleton rows={6} />
      ) : queue.error ? (
        <ErrorBox error={queue.error} onRetry={queue.reload} />
      ) : !group ? (
        <Empty icon={Inbox} text="Nothing to review. New suggestions appear here as documents arrive."
          action={<Button asChild variant="secondary"><Link href="/upload">Upload documents</Link></Button>} />
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          <Card>
            <div className="mb-3 flex items-center justify-between gap-2">
              <Link href={`/documents/${group.document.id}`} className="truncate font-semibold hover:underline">
                {group.document.title ?? "Untitled document"}
              </Link>
              <span className="tabular shrink-0 text-xs text-text-muted">
                {index + 1} / {groups.length}
              </span>
            </div>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={group.document.thumbnail_url} alt="Document preview"
              className="aspect-[3/4] w-full rounded border border-border bg-surface-2 object-contain"
              onError={(e) => (e.currentTarget.style.visibility = "hidden")} />
            <div className="mt-3 flex gap-2">
              <Button variant="secondary" onClick={() => setIndex((i) => Math.max(i - 1, 0))} disabled={index === 0}>Previous</Button>
              <Button variant="secondary" onClick={() => setIndex((i) => Math.min(i + 1, groups.length - 1))} disabled={index >= groups.length - 1}>Next</Button>
            </div>
          </Card>
          <div className="space-y-3">
            {group.items.filter((i) => i.kind === "notice").map((n) => (
              <div key={n.id} role="status" className="flex items-center justify-between gap-3 rounded-card border border-warning bg-surface p-3">
                <span className="flex items-center gap-2"><Badge tone="warn">Notice</Badge>{n.reason}</span>
                <Button variant="ghost" size="sm" onClick={() => reject(n)}>Dismiss</Button>
              </div>
            ))}
            {fields.length > 0 && (
              <Card title="Suggestions" actions={group.document.can_resolve && (
                <div className="flex gap-2">
                  <Button size="sm" onClick={acceptAll}><Check aria-hidden="true" /> Accept all</Button>
                  <Button size="sm" variant="secondary" onClick={rejectAll}>Reject all</Button>
                </div>)}>
                {!group.document.can_resolve && (
                  <p className="mb-2 text-sm text-text-muted">Only the owner of this document can resolve its suggestions.</p>
                )}
                <ol className="divide-y divide-border">
                  {fields.map((item, i) => (
                    <li key={item.id} className={`py-3 ${focus === i ? "border-l-2 border-primary pl-2" : ""}`}
                      onClick={() => setFocus(i)}>
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="min-w-0">
                          <div className="text-sm font-medium">
                            <span className="tabular mr-2 text-xs text-text-subtle">{i + 1}</span>
                            {fieldLabel(item.field ?? "")}
                          </div>
                          <div className="break-words">
                            <span className="text-text-muted line-through decoration-text-subtle">{show(item.current)}</span>
                            <span aria-hidden="true" className="mx-2 text-text-subtle">→</span>
                            <span className="font-medium">{show(item.suggested)}</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {item.confidence !== null && <Meter value={item.confidence} label="Confidence" />}
                          {group.document.can_resolve && (
                            <>
                              <Button size="sm" variant="secondary" aria-label={`Accept ${fieldLabel(item.field ?? "")}`}
                                disabled={item.suggested?.value == null} onClick={() => accept(item)}><Check aria-hidden="true" /></Button>
                              <Button size="sm" variant="ghost" aria-label={`Edit ${fieldLabel(item.field ?? "")}`}
                                onClick={() => setEditing(item.id)}><Pencil aria-hidden="true" /></Button>
                              <Button size="sm" variant="ghost" aria-label={`Reject ${fieldLabel(item.field ?? "")}`}
                                onClick={() => reject(item)}><X aria-hidden="true" /></Button>
                            </>
                          )}
                        </div>
                      </div>
                      {(item.evidence || item.reason) && (
                        <p className="mt-1 max-w-[65ch] text-xs text-text-muted">
                          {item.evidence ? `“${item.evidence}”` : item.reason}
                          {item.ai_run_id && (
                            <> · <Link className="hover:underline" href={`/settings/ai/runs/${item.ai_run_id}`}>How was this made?</Link></>
                          )}
                        </p>
                      )}
                      {editing === item.id && (
                        <Editor item={item} tax={tax} onCancel={() => setEditing(null)}
                          onSave={(v, c) => accept(item, v, c)} />
                      )}
                    </li>
                  ))}
                </ol>
              </Card>
            )}
            {group.items.filter((i) => i.kind === "new_term").map((t) => (
              <div key={t.id} className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-border bg-surface p-3">
                <span className="flex items-center gap-2">
                  <Sparkles aria-hidden="true" className="size-4 text-info" />
                  New {t.field?.split(":")[0].replace("_", " ")} proposed: <strong>{show(t.suggested)}</strong>
                  {t.reason && <span className="text-xs text-text-muted">({t.reason})</span>}
                </span>
                {group.document.can_resolve && (
                  <div className="flex gap-2">
                    <Button size="sm" variant="secondary" onClick={() => accept(t)}>Add</Button>
                    <Button size="sm" variant="ghost" onClick={() => reject(t)}>Ignore</Button>
                  </div>
                )}
              </div>
            ))}
            {group.document.document_date && (
              <p className="text-xs text-text-muted">Document date: {formatDate(group.document.document_date)}</p>
            )}
          </div>
        </div>
      )}
    </Page>
  );
}
