"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  Download,
  History,
  Lock,
  LockOpen,
  RotateCcw,
  ShieldAlert,
  Sparkles,
  Trash2,
} from "lucide-react";
import type { components } from "@/lib/api/schema";
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
  fieldLabel,
  formatDate,
  formatMoney,
  Page,
  PageHeader,
  Skeleton,
  useApi,
} from "@/components/intel/common";
import { DocumentAIPanel } from "@/components/intel/DocumentAIPanel";
import { reasonText } from "./document-queues";
import { labelsOf } from "./documents";

type Detail = components["schemas"]["DocumentDetail"];
type HistoryEntry = components["schemas"]["HistoryEntry"];
type Taxonomy = components["schemas"]["Taxonomy"];
type Draft = {
  title: string;
  document_date: string;
  category: string;
  document_type: string;
  correspondent: string;
  tags: string;
  shared: boolean;
};

const fileUrl = (id: string, kind: string, download = false) =>
  `/api/documents/${id}/file?kind=${kind}${download ? "&download=true" : ""}`;

function draftOf(doc: Detail): Draft {
  return {
    title: doc.title || "",
    document_date: doc.document_date || "",
    category: doc.category || "",
    document_type: doc.document_type || "",
    correspondent: doc.correspondent || "",
    tags: doc.tags.join(", "),
    shared: doc.shared,
  };
}

type Run = { confidence?: number | null; ai_run_id?: number | null };

/** Who set a field: a person (locked against the AI), the AI, or nobody yet. */
function Provenance({
  doc,
  field,
  owner,
  onUnlock,
}: {
  doc: Detail;
  field: string;
  owner: boolean;
  onUnlock: (field: string) => void;
}) {
  if (doc.manual_fields.includes(field)) {
    // manual_fields records that a person locked it, not which household member.
    return (
      <span className="inline-flex items-center gap-1">
        <Badge tone="ok" icon={Lock}>
          Set manually
        </Badge>
        {owner && (
          <Button
            variant="ghost"
            size="icon"
            aria-label={`Let the AI manage ${fieldLabel(field).toLowerCase()} again`}
            title="Let the AI manage this again"
            onClick={() => onUnlock(field)}
          >
            <LockOpen />
          </Button>
        )}
      </span>
    );
  }
  const fact = field.startsWith("facts.") ? doc.facts[field.slice(6)] : null;
  const run = (doc.provenance as Record<string, Run>)[
    fact ? "extract" : "classify"
  ];
  if (!run) return null;
  // Classification stores the category's confidence only; facts carry their own.
  const confidence = fact
    ? fact.confidence
    : field === "category"
      ? run.confidence
      : null;
  const badge = (
    <Badge tone="info" icon={Sparkles}>
      AI{confidence != null ? ` · ${Math.round(confidence * 100)}%` : ""}
    </Badge>
  );
  return run.ai_run_id ? (
    <Link
      href={`/settings/ai/runs/${run.ai_run_id}`}
      aria-label={`AI-set ${fieldLabel(field).toLowerCase()}: how was this made?`}
    >
      {badge}
    </Link>
  ) : (
    badge
  );
}

export function DocumentDetailView({
  id,
  viewerId,
}: {
  id: string;
  viewerId: number;
}) {
  const router = useRouter();
  const doc = useApi<Detail>(`/api/documents/${id}`);
  const history = useApi<HistoryEntry[]>(`/api/documents/${id}/history`);
  const taxonomy = useApi<Taxonomy>("/api/taxonomy");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function save(patch: Record<string, unknown>, done: string) {
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const result = await api<{ document: Detail }>(`/api/documents/${id}`, {
        method: "PATCH",
        json: patch,
      });
      doc.setData(result.document);
      setDraft(null);
      setMessage(done);
      history.reload();
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setSaving(false);
    }
  }

  function submit(current: Detail, value: Draft) {
    const tags = value.tags
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    const patch: Record<string, unknown> = {
      tags_add: tags.filter((t) => !current.tags.includes(t)),
      tags_remove: current.tags.filter((t) => !tags.includes(t)),
    };
    const clear: string[] = [];
    for (const key of [
      "title",
      "document_date",
      "category",
      "document_type",
      "correspondent",
    ] as const) {
      if (value[key] === (current[key] || "")) continue;
      if (value[key]) patch[key] = value[key];
      else clear.push(key);
    }
    if (clear.length) patch.clear_fields = clear;
    if (value.shared !== current.shared) patch.shared = value.shared;
    void save(patch, "Saved. Your changes are locked against the AI.");
  }

  async function trash(restore: boolean) {
    setError("");
    try {
      await api(`/api/documents/${id}/${restore ? "restore" : "trash"}`, {
        method: "POST",
      });
      if (restore) {
        doc.reload();
        setMessage("Restored from the trash.");
      } else router.push("/documents");
    } catch (e) {
      setError((e as ApiError).message);
    }
  }

  if (doc.error) {
    return (
      <Page>
        <ErrorBox error={doc.error} onRetry={doc.reload} />
      </Page>
    );
  }
  if (!doc.data) {
    return (
      <Page>
        <Skeleton rows={8} />
      </Page>
    );
  }
  const d = doc.data;
  const labels = labelsOf(taxonomy.data);
  const editing = draft !== null;
  // Editing, sharing, unlocking and trash are the owner's; shared readers only read.
  const owner = d.owner_id === viewerId;
  const set = (key: keyof Draft) => (event: { target: { value: string } }) =>
    setDraft({ ...(draft as Draft), [key]: event.target.value });
  const unlock = (field: string) =>
    void save(
      { unlock_fields: [field] },
      `${fieldLabel(field)} is managed by the AI again.`,
    );
  return (
    <Page>
      <PageHeader
        title={d.title || "Untitled document"}
        description={[
          d.document_date ? formatDate(d.document_date) : "No date",
          d.correspondent,
          d.pages ? `${d.pages} ${d.pages === 1 ? "page" : "pages"}` : null,
        ]
          .filter(Boolean)
          .join(" · ")}
        actions={
          <>
            {d.files.includes("original") && (
              <Button variant="secondary" asChild>
                <a href={fileUrl(id, "original", true)}>
                  <Download aria-hidden="true" />
                  Original
                </a>
              </Button>
            )}
            {d.files.includes("archive") && (
              <Button variant="secondary" asChild>
                <a href={fileUrl(id, "archive", true)}>
                  <Download aria-hidden="true" />
                  PDF
                </a>
              </Button>
            )}
            {owner &&
              (d.deleted_at ? (
                <Button variant="secondary" onClick={() => void trash(true)}>
                  <RotateCcw aria-hidden="true" />
                  Restore
                </Button>
              ) : (
                <Button variant="danger" onClick={() => void trash(false)}>
                  <Trash2 aria-hidden="true" />
                  Move to trash
                </Button>
              ))}
          </>
        }
      />
      {d.status === "quarantined" && (
        <div
          role="alert"
          className="mb-4 flex flex-wrap items-center gap-3 text-sm"
        >
          <Badge tone="error" icon={ShieldAlert}>
            Could not be read
          </Badge>
          {reasonText(d.quarantine_reason)} The original is kept.
          <Link href="/quarantine" className="text-primary hover:underline">
            Open quarantine
          </Link>
        </div>
      )}
      {d.status === "staged" || d.status === "processing" ? (
        <p role="status" className="mb-4 text-sm text-text-muted">
          {d.status === "processing" ? "Reading text…" : "Waiting to be read…"}{" "}
          This page updates when you reload it.
        </p>
      ) : null}
      {message && (
        <p role="status" className="mb-4 text-sm text-success">
          {message}
        </p>
      )}
      {error && (
        <p role="alert" className="mb-4 text-sm text-danger">
          {error}
        </p>
      )}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <section
          aria-label="Preview"
          className="min-h-[60vh] rounded-card border border-border bg-surface"
        >
          {d.files.includes("archive") ? (
            <iframe
              title={`Preview of ${d.title || "the document"}`}
              src={fileUrl(id, "archive")}
              className="h-[75vh] w-full rounded-card"
            />
          ) : (
            <p className="p-4 text-sm text-text-muted">
              The preview appears once the document has been read.
            </p>
          )}
        </section>
        <div className="space-y-6">
          <Card
            title="Details"
            actions={
              owner &&
              !editing && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setDraft(draftOf(d))}
                >
                  Edit
                </Button>
              )
            }
          >
            {editing ? (
              <form
                className="space-y-4"
                onSubmit={(event) => {
                  event.preventDefault();
                  submit(d, draft);
                }}
              >
                <Field label="Title">
                  <Input
                    value={draft.title}
                    maxLength={120}
                    onChange={set("title")}
                  />
                </Field>
                <Field label="Date">
                  <Input
                    type="date"
                    value={draft.document_date}
                    onChange={set("document_date")}
                  />
                </Field>
                <Field label="Category">
                  <select
                    className={control}
                    value={draft.category}
                    onChange={set("category")}
                  >
                    <option value="">Not set</option>
                    {taxonomy.data?.categories
                      .filter((c) => c.enabled !== false || c.id === d.category)
                      .map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.label}
                        </option>
                      ))}
                  </select>
                </Field>
                <Field label="Type">
                  <select
                    className={control}
                    value={draft.document_type}
                    onChange={set("document_type")}
                  >
                    <option value="">Not set</option>
                    {taxonomy.data?.document_types.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.label}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Sender">
                  <Input
                    value={draft.correspondent}
                    onChange={set("correspondent")}
                  />
                </Field>
                <Field label="Tags" help="Separate tags with commas.">
                  <Input value={draft.tags} onChange={set("tags")} />
                </Field>
                <label className="flex min-h-5 items-center gap-2">
                  <input
                    type="checkbox"
                    className={checkbox}
                    checked={draft.shared}
                    onChange={(e) =>
                      setDraft({ ...draft, shared: e.target.checked })
                    }
                  />
                  Visible to the household
                </label>
                <div className="flex justify-end gap-2">
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => setDraft(null)}
                  >
                    Cancel
                  </Button>
                  <Button type="submit" disabled={saving}>
                    {saving ? "Saving…" : "Save"}
                  </Button>
                </div>
              </form>
            ) : (
              <dl className="space-y-3">
                {(
                  [
                    ["title", d.title],
                    [
                      "document_date",
                      d.document_date ? formatDate(d.document_date) : null,
                    ],
                    [
                      "category",
                      d.category && (labels[d.category] || d.category),
                    ],
                    [
                      "document_type",
                      d.document_type &&
                        (labels[d.document_type] || d.document_type),
                    ],
                    ["correspondent", d.correspondent],
                    ["tags", d.tags.join(", ")],
                  ] as const
                ).map(([field, value]) => (
                  <div key={field}>
                    <dt className="text-sm text-text-muted">
                      {fieldLabel(field)}
                    </dt>
                    <dd className="flex flex-wrap items-center justify-between gap-2">
                      <span className="min-w-0 break-words">
                        {value || "—"}
                      </span>
                      <Provenance
                        doc={d}
                        field={field}
                        owner={owner}
                        onUnlock={unlock}
                      />
                    </dd>
                  </div>
                ))}
                <div>
                  <dt className="text-sm text-text-muted">Shared</dt>
                  <dd>
                    {d.shared ? "Visible to the household" : "Only the owner"}
                  </dd>
                </div>
              </dl>
            )}
          </Card>
          <DocumentAIPanel
            documentId={id}
            canEdit={owner}
            onComplete={doc.reload}
          />
          <Card title="Details found in the document">
            {Object.keys(d.facts).length ? (
              <dl className="space-y-3">
                {Object.entries(d.facts).map(([key, fact]) => (
                  <div key={key}>
                    <dt className="text-sm text-text-muted">
                      {fieldLabel(key)}
                    </dt>
                    <dd className="flex flex-wrap items-center justify-between gap-2">
                      <span className="tabular">
                        {fact.type === "money"
                          ? formatMoney(fact.value, fact.currency)
                          : fact.type === "date"
                            ? formatDate(fact.value)
                            : fact.value}
                      </span>
                      <Provenance
                        doc={d}
                        field={`facts.${key}`}
                        owner={owner}
                        onUnlock={unlock}
                      />
                    </dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="text-sm text-text-muted">
                Amounts, due dates and numbers appear here once the AI has read
                the document.
              </p>
            )}
          </Card>
          <Card title="History">
            {history.data?.length ? (
              <ol className="space-y-2 text-sm">
                {history.data.map((entry, index) => (
                  <li key={index} className="flex gap-2">
                    <History
                      aria-hidden="true"
                      className="mt-0.5 size-4 shrink-0 text-text-muted"
                    />
                    <span>
                      <span className="tabular text-text-muted">
                        {formatDate(entry.at)}
                      </span>{" "}
                      {describe(entry, viewerId)}
                    </span>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-sm text-text-muted">No changes yet.</p>
            )}
          </Card>
        </div>
      </div>
    </Page>
  );
}

function describe(entry: HistoryEntry, viewerId: number): string {
  const who =
    entry.actor === `user:${viewerId}`
      ? "You"
      : entry.actor.startsWith("user:")
        ? "A household member"
        : entry.actor.startsWith("ai:")
          ? "The AI"
          : "DocuHive";
  const fields = Object.keys(entry.after || {})
    .filter((f) => f !== "unlocked")
    .map(fieldLabel);
  switch (entry.action) {
    case "ingest.stored":
      return "Stored in the archive";
    case "ingest.quarantined":
      return "Could not be read; kept in quarantine";
    case "ingest.retry":
      return "Sent for reading again";
    case "trash":
      return `${who} moved it to the trash`;
    case "restore":
      return `${who} restored it`;
    default:
      return fields.length
        ? `${who} changed ${fields.join(", ").toLowerCase()}`
        : `${who} updated it`;
  }
}
