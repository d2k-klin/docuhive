"use client";

import Link from "next/link";
import { Card, formatDate, useApi } from "@/components/intel/common";

type Similar = { id: string; title: string | null; document_date: string | null; thumbnail_url: string; score: number };

/** Slot: document detail, below the metadata. Renders nothing when empty or unavailable. */
export function SimilarDocuments({ documentId }: { documentId: string }) {
  const { data } = useApi<{ items: Similar[]; semantic_available: boolean }>(
    `/api/ai/similar/${encodeURIComponent(documentId)}?k=8`,
  );
  if (!data?.semantic_available || !data.items.length) return null;
  return (
    <Card title="Similar documents">
      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {data.items.map((d) => (
          <li key={d.id}>
            <Link href={`/documents/${d.id}`} className="block rounded border border-border p-2 hover:border-border-strong">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={d.thumbnail_url} alt="" className="mb-2 aspect-[3/4] w-full rounded bg-surface-2 object-cover"
                onError={(e) => (e.currentTarget.style.visibility = "hidden")} />
              <span className="block truncate text-sm font-medium">{d.title ?? "Document"}</span>
              <span className="text-xs text-text-muted">{formatDate(d.document_date)}</span>
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}
