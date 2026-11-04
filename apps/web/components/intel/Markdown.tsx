"use client";

import * as React from "react";
import Link from "next/link";
import { FileText } from "lucide-react";

// ponytail: a small renderer for what the Ask prompt produces (paragraphs, lists, tables,
// **bold**, `code`, [doc:ID]). It builds React elements only, so there is no raw HTML to
// sanitise. Swap in react-markdown + rehype-sanitize if answers need more syntax.

const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|\[doc:[0-9A-Za-z]{10,40}\])/g;

function inline(text: string, titles: Record<string, string>): React.ReactNode[] {
  return text.split(INLINE).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**"))
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`"))
      return (
        <code key={i} className="rounded bg-surface-2 px-1 font-mono text-sm">
          {part.slice(1, -1)}
        </code>
      );
    const cite = part.match(/^\[doc:(.+)\]$/);
    if (cite)
      return <DocChip key={i} id={cite[1]} title={titles[cite[1]]} />;
    return part;
  });
}

export function DocChip({ id, title }: { id: string; title?: string }) {
  return (
    <Link
      href={`/documents/${id}`}
      title={title ?? "Open document"}
      className="mx-0.5 inline-flex h-5 max-w-56 items-center gap-1 rounded-md border border-border bg-surface-2 px-1.5 align-middle text-xs font-medium text-primary hover:border-primary"
    >
      <FileText aria-hidden="true" className="size-3 shrink-0" />
      <span className="truncate">{title ?? "Document"}</span>
    </Link>
  );
}

export function Markdown({
  text,
  titles = {},
}: {
  text: string;
  titles?: Record<string, string>;
}) {
  const blocks = text.trim().split(/\n{2,}/);
  return (
    <div className="max-w-[65ch] space-y-3 leading-relaxed">
      {blocks.map((block, bi) => {
        const lines = block.split("\n");
        if (lines.every((l) => /^\s*\|.*\|\s*$/.test(l)) && lines.length >= 2) {
          const rows = lines
            .filter((l) => !/^\s*\|[\s:|-]+\|\s*$/.test(l))
            .map((l) => l.trim().slice(1, -1).split("|").map((c) => c.trim()));
          const [head, ...body] = rows;
          return (
            <div key={bi} className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs text-text-muted">
                    {head.map((c, i) => (
                      <th key={i} className="px-3 py-2 font-medium">
                        {inline(c, titles)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {body.map((r, ri) => (
                    <tr key={ri} className="border-b border-border">
                      {r.map((c, i) => (
                        <td key={i} className="tabular px-3 py-2">
                          {inline(c, titles)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }
        if (lines.every((l) => /^\s*([-*]|\d+\.)\s+/.test(l))) {
          const ordered = /^\s*\d+\./.test(lines[0]);
          const items = lines.map((l) => l.replace(/^\s*([-*]|\d+\.)\s+/, ""));
          const List = ordered ? "ol" : "ul";
          return (
            <List
              key={bi}
              className={ordered ? "list-decimal space-y-1 pl-5" : "list-disc space-y-1 pl-5"}
            >
              {items.map((it, i) => (
                <li key={i}>{inline(it, titles)}</li>
              ))}
            </List>
          );
        }
        const heading = lines[0].match(/^#{1,4}\s+(.*)$/);
        if (heading && lines.length === 1)
          return (
            <h3 key={bi} className="font-semibold">
              {inline(heading[1], titles)}
            </h3>
          );
        return (
          <p key={bi}>
            {lines.map((l, i) => (
              <React.Fragment key={i}>
                {i > 0 && <br />}
                {inline(l, titles)}
              </React.Fragment>
            ))}
          </p>
        );
      })}
    </div>
  );
}
