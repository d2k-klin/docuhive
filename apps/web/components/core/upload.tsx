"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  CheckCircle2,
  FileUp,
  LoaderCircle,
  ShieldAlert,
  TriangleAlert,
} from "lucide-react";
import type { components } from "@/lib/api/schema";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { checkbox, control } from "@/lib/ui/control";
import { errorMessage } from "@/lib/i18n/errors";
import {
  DocumentAIStatus,
  useAIStatuses,
} from "@/components/intel/DocumentAIStatus";
import { reasonText } from "./document-queues";
import {
  api,
  Badge,
  Field,
  Page,
  PageHeader,
  useApi,
} from "@/components/intel/common";

type Taxonomy = components["schemas"]["Taxonomy"];
type Detail = components["schemas"]["DocumentDetail"];
type Item = {
  key: string;
  name: string;
  state:
    "uploading" | "staged" | "duplicate" | "stored" | "quarantined" | "failed";
  id?: string;
  detail?: string;
};

const POLL_MS = 2500;

/** Same pipeline as email and the scanner folder; category and tags count as your choice. */
export function UploadPage() {
  const taxonomy = useApi<Taxonomy>("/api/taxonomy");
  const picker = useRef<HTMLInputElement>(null);
  const [category, setCategory] = useState("");
  const [tags, setTags] = useState("");
  const [combine, setCombine] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [items, setItems] = useState<Item[]>([]);

  const ai = useAIStatuses(
    items
      .filter((item) => item.state === "stored" && item.id)
      .map((item) => item.id!),
  );

  const update = (key: string, change: Partial<Item>) =>
    setItems((all) =>
      all.map((item) => (item.key === key ? { ...item, ...change } : item)),
    );

  async function send(files: File[], key: string) {
    const query = new URLSearchParams({
      combine: String(combine && files.length > 1),
    });
    if (category) query.set("category", category);
    for (const tag of tags
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean))
      query.append("tags", tag);
    const body = new FormData();
    for (const file of files) body.append("files", file);
    const response = await fetch(`/api/upload?${query}`, {
      method: "POST",
      body,
      headers: { "X-DocuHive-CSRF": "1" },
    }).catch(() => null);
    if (!response?.ok) {
      const payload = await response?.json().catch(() => ({}));
      const code =
        payload?.error?.code || payload?.detail?.code || "upload_failed";
      update(key, { state: "failed", detail: errorMessage(code) });
      return;
    }
    const result = (await response.json()) as {
      document_id: string;
      status: string;
    };
    update(key, {
      id: result.document_id,
      state: result.status === "duplicate" ? "duplicate" : "staged",
    });
  }

  function add(list: FileList | null) {
    const files = Array.from(list || []);
    if (!files.length) return;
    const groups = combine ? [files] : files.map((file) => [file]);
    const fresh = groups.map((group) => ({
      key: crypto.randomUUID(),
      name: group.length > 1 ? `${group.length} pages` : group[0].name,
      state: "uploading" as const,
    }));
    setItems((all) => [...fresh, ...all]);
    groups.forEach((group, index) => void send(group, fresh[index].key));
  }

  // Follow each staged document until it is stored or needs attention; `poll` re-arms the
  // timer after every check, also when nothing changed yet.
  const [poll, setPoll] = useState(0);
  useEffect(() => {
    const waiting = items.filter((item) => item.state === "staged" && item.id);
    if (!waiting.length) return;
    const timer = setTimeout(async () => {
      for (const item of waiting) {
        const doc = await api<Detail>(`/api/documents/${item.id}`).catch(
          () => null,
        );
        if (doc?.status === "stored")
          update(item.key, { state: "stored", detail: doc.title || "" });
        if (doc?.status === "quarantined")
          update(item.key, {
            state: "quarantined",
            detail: reasonText(doc.quarantine_reason),
          });
      }
      setPoll((n) => n + 1);
    }, POLL_MS);
    return () => clearTimeout(timer);
  }, [items, poll]);

  return (
    <Page narrow>
      <PageHeader
        title="Upload"
        description="Uploaded files are read, sorted and stored exactly like mail and scans."
      />
      <div className="space-y-6">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Category" help="Optional. Locked against the AI.">
            <select
              className={control}
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              <option value="">Let the AI decide</option>
              {taxonomy.data?.categories
                .filter((c) => c.enabled !== false)
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.label}
                  </option>
                ))}
            </select>
          </Field>
          <Field label="Tags" help="Optional, separated by commas.">
            <Input value={tags} onChange={(e) => setTags(e.target.value)} />
          </Field>
        </div>
        <label className="flex min-h-5 items-center gap-2">
          <input
            type="checkbox"
            className={checkbox}
            checked={combine}
            onChange={(e) => setCombine(e.target.checked)}
          />
          Combine several photos into one document
        </label>
        <div
          className={
            "flex min-h-32 flex-col items-center justify-center gap-3 rounded-card border border-dashed p-6 text-center " +
            (dragging ? "border-primary bg-surface-2" : "border-border-strong")
          }
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            add(event.dataTransfer.files);
          }}
        >
          <FileUp aria-hidden="true" className="size-5 text-text-muted" />
          <p>Drop PDFs, photos, Office files or emails here</p>
          <Button variant="secondary" onClick={() => picker.current?.click()}>
            Choose files
          </Button>
          <input
            ref={picker}
            type="file"
            multiple
            className="sr-only"
            aria-label="Choose files to upload"
            onChange={(event) => {
              add(event.target.files);
              event.target.value = "";
            }}
          />
        </div>
        {items.length > 0 && (
          <ul className="space-y-2" aria-live="polite">
            {items.map((item) => (
              <li
                key={item.key}
                className="flex flex-wrap items-center justify-between gap-2 rounded-card border border-border bg-surface p-3"
              >
                <span className="min-w-0 break-words">{item.name}</span>
                <div className="flex flex-wrap items-center gap-2">
                  <Status item={item} />
                  {item.state === "stored" && item.id && (
                    <DocumentAIStatus
                      status={ai.items[item.id]}
                      unavailable={ai.error}
                    />
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Page>
  );
}

function Status({ item }: { item: Item }) {
  const link = item.id ? `/documents/${item.id}` : "";
  switch (item.state) {
    case "uploading":
      return (
        <Badge tone="info" icon={LoaderCircle}>
          Uploading…
        </Badge>
      );
    case "staged":
      return (
        <Badge tone="info" icon={LoaderCircle}>
          Reading text…
        </Badge>
      );
    case "duplicate":
      return (
        <Link href={link} className="text-sm text-primary hover:underline">
          Already in your archive
        </Link>
      );
    case "stored":
      return (
        <Link
          href={link}
          className="inline-flex items-center gap-2 text-sm hover:underline"
        >
          <Badge tone="ok" icon={CheckCircle2}>
            Stored
          </Badge>
          {item.detail}
        </Link>
      );
    case "quarantined":
      return (
        <Link
          href="/quarantine"
          className="inline-flex items-center gap-2 text-sm hover:underline"
        >
          <Badge tone="error" icon={ShieldAlert}>
            Needs attention
          </Badge>
          {item.detail}
        </Link>
      );
    default:
      return (
        <Badge tone="error" icon={TriangleAlert}>
          {item.detail || "Upload failed"}
        </Badge>
      );
  }
}
