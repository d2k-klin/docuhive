"use client";

import Link from "next/link";
import { useState } from "react";
import { RotateCcw, ShieldCheck, Trash2 } from "lucide-react";
import type { components } from "@/lib/api/schema";
import { Button } from "@/components/ui/button";
import {
  api,
  ApiError,
  Empty,
  ErrorBox,
  formatDate,
  Page,
  PageHeader,
  Skeleton,
  useApi,
} from "@/components/intel/common";
import { DocumentTable } from "./documents";

type Pending = components["schemas"]["PendingDocument"];
type Row = components["schemas"]["DocumentRow"];

const RETRY =
  " Retry it; if it fails again, an administrator can check the logs.";
const REASONS: Record<string, string> = {
  encrypted:
    "The PDF is password-protected. Remove the password and upload it again.",
  empty_file: "The file is empty.",
  empty_pdf: "The PDF has no pages.",
  too_many_pages: "The document has more than 500 pages.",
  image_too_large: "The image is too large to read.",
  invalid_archive: "The archive file is damaged.",
  archive_expansion_limit: "The archive unpacks to too much data.",
  input_missing: "The staged file is missing. Upload it again.",
  step_timeout: "Reading took too long." + RETRY,
  converter_timeout: "Converting took too long." + RETRY,
  step_crashed: "Reading stopped unexpectedly." + RETRY,
  ocr_fallbacks_exhausted: "No text could be read from it." + RETRY,
};
const FAMILIES: [string, string][] = [
  ["unsupported_type", "This file type is not supported."],
  ["processing_failed", "Reading failed several times." + RETRY],
  ["ocr_exit", "Text recognition failed." + RETRY],
  ["conversion_http_", "The file could not be converted to PDF." + RETRY],
  ["converter_http_", "The file could not be converted to PDF." + RETRY],
];

/** Plain-language reason with a next step; never shows an internal code. */
export function reasonText(reason: string | null | undefined): string {
  if (reason && REASONS[reason]) return REASONS[reason];
  const family = FAMILIES.find(([prefix]) => reason?.startsWith(prefix));
  return family ? family[1] : "It could not be read." + RETRY;
}

/** Documents that could not be read; the original is always kept, so a retry is safe. */
export function QuarantinePage() {
  const list = useApi<Pending[]>("/api/documents/pending");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const items = (list.data || []).filter((doc) => doc.status === "quarantined");
  async function retry(id: string) {
    setError("");
    try {
      await api(`/api/documents/${id}/retry`, { method: "POST" });
      setMessage("Sent for reading again.");
      list.reload();
    } catch (e) {
      setError((e as ApiError).message);
    }
  }
  return (
    <Page>
      <PageHeader
        title="Quarantine"
        description="Files that could not be read. The originals are kept until you retry."
      />
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
      {list.error ? (
        <ErrorBox error={list.error} onRetry={list.reload} />
      ) : list.loading ? (
        <Skeleton rows={4} />
      ) : !items.length ? (
        <Empty
          icon={ShieldCheck}
          text="Nothing in quarantine. Every document was read."
        />
      ) : (
        <ul className="space-y-2">
          {items.map((doc) => (
            <li
              key={doc.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-border bg-surface p-4"
            >
              <div className="min-w-0">
                <Link
                  href={`/documents/${doc.id}`}
                  className="font-medium hover:underline"
                >
                  {doc.title || "Untitled document"}
                </Link>
                <p className="text-sm text-text-muted">
                  {formatDate(doc.added_at)} ·{" "}
                  {reasonText(doc.quarantine_reason)}
                </p>
              </div>
              <Button variant="secondary" onClick={() => void retry(doc.id)}>
                <RotateCcw aria-hidden="true" />
                Retry
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Page>
  );
}

export function TrashPage() {
  const list = useApi<Row[]>("/api/documents/trash");
  const [error, setError] = useState("");
  async function restore(id: string) {
    setError("");
    try {
      await api(`/api/documents/${id}/restore`, { method: "POST" });
      list.reload();
    } catch (e) {
      setError((e as ApiError).message);
    }
  }
  return (
    <Page>
      <PageHeader
        title="Trash"
        description="Deleted documents stay here, with their files, until an administrator removes them."
      />
      {error && (
        <p role="alert" className="mb-4 text-sm text-danger">
          {error}
        </p>
      )}
      {list.error ? (
        <ErrorBox error={list.error} onRetry={list.reload} />
      ) : list.loading ? (
        <Skeleton rows={4} />
      ) : !list.data?.length ? (
        <Empty icon={Trash2} text="The trash is empty." />
      ) : (
        <div className="space-y-3">
          <DocumentTable items={list.data} link={false} />
          <div className="flex flex-wrap gap-2">
            {list.data.map((doc) => (
              <Button
                key={doc.id}
                variant="secondary"
                size="sm"
                onClick={() => void restore(doc.id)}
              >
                <RotateCcw aria-hidden="true" />
                Restore {doc.title || "untitled document"}
              </Button>
            ))}
          </div>
        </div>
      )}
    </Page>
  );
}
