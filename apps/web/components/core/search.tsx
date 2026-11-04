"use client";

import Link from "next/link";
import { useState } from "react";
import { Search as SearchIcon } from "lucide-react";
import type { components } from "@/lib/api/schema";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Empty,
  ErrorBox,
  formatDate,
  Page,
  PageHeader,
  Skeleton,
  useApi,
} from "@/components/intel/common";
import {
  FilterBar,
  filterQuery,
  labelsOf,
  type ListFilters,
} from "./documents";

type Result = components["schemas"]["SearchResult"];
type Taxonomy = components["schemas"]["Taxonomy"];

/** The API marks matches with \u0002 … \u0003; render them as <mark> without HTML injection. */
function Snippet({ text }: { text: string }) {
  const parts = text.split(/(\u0002[^\u0003]*\u0003)/);
  return (
    <p className="max-w-[65ch] text-sm text-text-muted">
      {parts.map((part, index) =>
        part.startsWith("\u0002") ? (
          <mark key={index} className="rounded bg-surface-2 px-0.5 text-text">
            {part.slice(1, -1)}
          </mark>
        ) : (
          <span key={index}>{part}</span>
        ),
      )}
    </p>
  );
}

export function SearchPage({ initial }: { initial: string }) {
  const [input, setInput] = useState(initial);
  const [query, setQuery] = useState(initial);
  const [filters, setFilters] = useState<ListFilters>({
    category: "",
    document_type: "",
    tag: "",
    date_from: "",
    date_to: "",
  });
  const params = filterQuery(filters);
  params.set("q", query);
  const results = useApi<Result[]>(
    query.trim() ? `/api/search?${params}` : null,
  );
  const taxonomy = useApi<Taxonomy>("/api/taxonomy");
  const labels = labelsOf(taxonomy.data);
  return (
    <Page>
      <PageHeader
        title="Search"
        description="Find documents by their words or their meaning."
      />
      <div className="space-y-4">
        <form
          role="search"
          className="flex flex-wrap gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            setQuery(input.trim());
            window.history.replaceState(
              null,
              "",
              `/search?q=${encodeURIComponent(input.trim())}`,
            );
          }}
        >
          <label className="relative min-w-0 flex-1">
            <span className="sr-only">Search your documents</span>
            <SearchIcon
              aria-hidden="true"
              className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-text-subtle"
            />
            <Input
              className="pl-9"
              value={input}
              maxLength={500}
              placeholder="For example: electricity 2025, notice period, insurance number"
              onChange={(event) => setInput(event.target.value)}
            />
          </label>
          <Button type="submit">Search</Button>
        </form>
        <FilterBar
          value={filters}
          taxonomy={taxonomy.data}
          onChange={setFilters}
        />
        {!query.trim() ? (
          <Empty
            icon={SearchIcon}
            text="Type a few words. Spelling mistakes and German or English word forms are fine."
          />
        ) : results.error ? (
          <ErrorBox error={results.error} onRetry={results.reload} />
        ) : results.loading ? (
          <Skeleton rows={5} />
        ) : !results.data?.length ? (
          <Empty
            icon={SearchIcon}
            text="Nothing found. Try other words, fewer filters, or ask a question instead."
            action={
              <Button variant="secondary" asChild>
                <Link href={`/ask?q=${encodeURIComponent(query)}`}>
                  Ask instead
                </Link>
              </Button>
            }
          />
        ) : (
          <ol className="space-y-3" aria-label="Results">
            {results.data.map((hit) => (
              <li
                key={hit.document_id}
                className="rounded-card border border-border bg-surface p-4"
              >
                <Link
                  href={`/documents/${hit.document_id}`}
                  className="font-medium hover:underline"
                >
                  {hit.title || "Untitled document"}
                </Link>
                <p className="mb-1 text-xs text-text-muted tabular">
                  {[
                    hit.document_date && formatDate(hit.document_date),
                    hit.correspondent,
                    hit.category && (labels[hit.category] || hit.category),
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
                {hit.snippet && <Snippet text={hit.snippet} />}
              </li>
            ))}
          </ol>
        )}
      </div>
    </Page>
  );
}
