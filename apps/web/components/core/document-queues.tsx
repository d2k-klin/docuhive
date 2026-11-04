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

const REASONS: Record<string, string> = {
  encrypted:
    "The PDF is password-protected. Remove the password and upload it again.",
  empty_file: "The file is empty.",
  too_many_pages: "The document has more than 500 pages.",
  image_too_large: "The image is too large to read.",
  input_missing: "The staged file is missing.",
  step_timeout: "Reading took too long.",
  converter_timeout: "Converting took too long.",
};

export function reasonText(reason: string | null | undefined): string {
  if (!reason) return "Unknown reason.";
  if (REASONS[reason]) return REASONS[reason];
  if (reason.startsWith("unsupported_type"))
    return "This file type is not supported.";
  if (reason.startsWith("processing_failed"))
    return "Reading failed several times.";
  return reason;
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
          <DocumentTable items={list.data} />
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
