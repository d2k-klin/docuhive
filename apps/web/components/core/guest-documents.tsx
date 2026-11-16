"use client";

import { useEffect, useState } from "react";
import { Download, FileText } from "lucide-react";
import type { components } from "@/lib/api/schema";
import { Button } from "@/components/ui/button";
import { formatDate } from "@/components/intel/common";

type GuestPage = components["schemas"]["GuestPage"];

/** What someone without an account sees through a guest link: a list to open or download. */
export function GuestDocuments({ token }: { token: string }) {
  const [page, setPage] = useState<GuestPage | null>(null);
  const [failed, setFailed] = useState(false);
  const base = `/api/guest/${encodeURIComponent(token)}`;
  useEffect(() => {
    fetch(base, { credentials: "omit" })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setPage)
      .catch(() => setFailed(true));
  }, [base]);
  return (
    <main className="mx-auto min-h-screen max-w-2xl space-y-6 p-6">
      <header>
        <FileText className="mb-4 size-5 text-primary" aria-hidden="true" />
        <h1 className="text-xl font-semibold">
          {page ? page.label : "Shared documents"}
        </h1>
        {page && (
          <p className="text-sm text-text-muted">
            Read-only. This link works until {formatDate(page.expires_at)}.
          </p>
        )}
      </header>
      {failed && (
        <p role="alert" className="text-sm text-danger">
          This link has expired or does not exist. Ask the person who sent it
          for a new one.
        </p>
      )}
      {!page && !failed && <p className="text-text-muted">Loading…</p>}
      {page && !page.documents.length && (
        <p className="text-sm text-text-muted">
          No documents are shared through this link any more.
        </p>
      )}
      {page && page.documents.length > 0 && (
        <ul className="divide-y divide-border rounded-card border border-border bg-surface">
          {page.documents.map((d) => (
            <li
              key={d.id}
              className="flex flex-wrap items-center justify-between gap-3 p-4"
            >
              <div>
                <a
                  className="font-medium text-primary hover:underline"
                  href={`${base}/documents/${d.id}/file`}
                  target="_blank"
                  rel="noreferrer"
                >
                  {d.title || "Untitled document"}
                </a>
                <p className="text-sm text-text-muted">
                  {[
                    d.document_date ? formatDate(d.document_date) : null,
                    d.pages
                      ? `${d.pages} ${d.pages === 1 ? "page" : "pages"}`
                      : null,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </div>
              <Button variant="secondary" size="sm" asChild>
                <a href={`${base}/documents/${d.id}/file?download=true`}>
                  <Download aria-hidden="true" />
                  PDF
                </a>
              </Button>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
