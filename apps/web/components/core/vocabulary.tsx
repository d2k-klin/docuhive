"use client";

import { useState } from "react";
import { Merge, Pencil, Tags } from "lucide-react";
import type { components } from "@/lib/api/schema";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { control } from "@/lib/ui/control";
import {
  api,
  ApiError,
  Card,
  Empty,
  ErrorBox,
  Page,
  PageHeader,
  Skeleton,
  useApi,
} from "@/components/intel/common";

type Item = components["schemas"]["VocabularyItem"];
type Kind = "tags" | "correspondents";

/** The destination has its own lookup, independent of the list filter above. */
function MergeTarget({
  kind,
  source,
  value,
  onChange,
}: {
  kind: Kind;
  source: Item;
  value: string;
  onChange: (id: string) => void;
}) {
  const [find, setFind] = useState("");
  const options = useApi<Item[]>(
    `/api/vocabulary/${kind}?q=${encodeURIComponent(find)}`,
  );
  return (
    <div className="flex min-w-0 flex-1 flex-wrap gap-2">
      <label className="min-w-40 flex-1">
        <span className="sr-only">Find where to merge {source.name}</span>
        <Input
          placeholder="Find destination"
          value={find}
          onChange={(e) => setFind(e.target.value)}
          autoFocus
        />
      </label>
      <label className="min-w-40 flex-1">
        <span className="sr-only">Merge {source.name} into</span>
        <select
          className={control}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">Merge {source.name} into…</option>
          {options.data
            ?.filter((other) => other.id !== source.id)
            .map((other) => (
              <option key={other.id} value={other.id}>
                {other.name}
              </option>
            ))}
        </select>
      </label>
    </div>
  );
}

function VocabularyList({
  kind,
  title,
  admin,
}: {
  kind: Kind;
  title: string;
  admin: boolean;
}) {
  const [q, setQ] = useState("");
  const list = useApi<Item[]>(
    `/api/vocabulary/${kind}?q=${encodeURIComponent(q)}`,
  );
  const [editing, setEditing] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [merging, setMerging] = useState<number | null>(null);
  const [target, setTarget] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  async function run(
    path: string,
    init: Parameters<typeof api>[1],
    done: string,
  ) {
    setError("");
    try {
      const result = await api<{ documents: number }>(path, init);
      setMessage(`${done} (${result.documents} documents updated).`);
      setEditing(null);
      setMerging(null);
      list.reload();
    } catch (e) {
      setError((e as ApiError).message);
    }
  }
  return (
    <Card title={title}>
      <div className="space-y-3">
        <label className="block">
          <span className="sr-only">Filter {title.toLowerCase()}</span>
          <Input
            placeholder="Filter"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </label>
        {message && (
          <p role="status" className="text-sm text-success">
            {message}
          </p>
        )}
        {error && (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        )}
        {list.error ? (
          <ErrorBox error={list.error} onRetry={list.reload} />
        ) : list.loading && !list.data ? (
          <Skeleton rows={4} />
        ) : !list.data?.length ? (
          <Empty
            icon={Tags}
            text={q ? "Nothing matches." : "Nothing here yet."}
          />
        ) : (
          <ul className="divide-y divide-border">
            {list.data.map((item) => (
              <li
                key={item.id}
                className="flex min-h-11 flex-wrap items-center justify-between gap-2 py-1"
              >
                {editing === item.id ? (
                  <form
                    className="flex w-full flex-wrap gap-2"
                    onSubmit={(event) => {
                      event.preventDefault();
                      void run(
                        `/api/vocabulary/${kind}/${item.id}`,
                        { method: "PATCH", json: { name } },
                        `Renamed to ${name}`,
                      );
                    }}
                  >
                    <label className="min-w-0 flex-1">
                      <span className="sr-only">New name for {item.name}</span>
                      <Input
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        autoFocus
                      />
                    </label>
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => setEditing(null)}
                    >
                      Cancel
                    </Button>
                    <Button type="submit" disabled={!name.trim()}>
                      Rename
                    </Button>
                  </form>
                ) : merging === item.id ? (
                  <form
                    className="flex w-full flex-wrap gap-2"
                    onSubmit={(event) => {
                      event.preventDefault();
                      void run(
                        `/api/vocabulary/${kind}/merge`,
                        {
                          method: "POST",
                          json: {
                            source_ids: [item.id],
                            target_id: Number(target),
                          },
                        },
                        `Merged ${item.name}`,
                      );
                    }}
                  >
                    <MergeTarget
                      kind={kind}
                      source={item}
                      value={target}
                      onChange={setTarget}
                    />
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => setMerging(null)}
                    >
                      Cancel
                    </Button>
                    <Button type="submit" variant="danger" disabled={!target}>
                      Merge {item.documents} documents
                    </Button>
                  </form>
                ) : (
                  <>
                    <span className="min-w-0 break-words">
                      {item.name}{" "}
                      <span className="text-xs text-text-muted tabular">
                        {item.documents}
                      </span>
                    </span>
                    {admin && (
                      <span className="flex gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`Rename ${item.name}`}
                          onClick={() => {
                            setEditing(item.id);
                            setName(item.name);
                          }}
                        >
                          <Pencil />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`Merge ${item.name} into another`}
                          onClick={() => {
                            setMerging(item.id);
                            setTarget("");
                          }}
                        >
                          <Merge />
                        </Button>
                      </span>
                    )}
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}

export function VocabularyPage({ admin }: { admin: boolean }) {
  return (
    <Page>
      <PageHeader
        title="Vocabulary"
        description={
          admin
            ? "Rename tags and senders, or merge duplicates into one. Documents follow automatically."
            : "The tags and senders on documents you can see. An administrator can rename or merge them."
        }
      />
      <div className="grid gap-6 lg:grid-cols-2">
        <VocabularyList kind="tags" title="Tags" admin={admin} />
        <VocabularyList kind="correspondents" title="Senders" admin={admin} />
      </div>
    </Page>
  );
}
