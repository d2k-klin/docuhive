"use client";

import { useEffect, useState } from "react";
import {
  ChevronRight,
  Folder,
  FolderSync,
  RefreshCw,
  TriangleAlert,
  Unlink,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { checkbox } from "@/lib/ui/control";
import {
  api,
  ApiError,
  Badge,
  Card,
  Empty,
  ErrorBox,
  Page,
  PageHeader,
  Skeleton,
  formatDate,
  useApi,
} from "@/components/intel/common";

type LinkedFolder = {
  id: number;
  label: string;
  path: string;
  owner: string;
  shared: boolean;
  created_at: string;
  last_scan_at: string | null;
  last_error: string | null;
  scanning: boolean;
  counts: Record<string, number>;
};
type Listing = {
  root: string;
  path: string;
  folders: { name: string; path: string }[];
};
type FileRow = {
  path: string;
  state: string;
  error: string | null;
  document_id: string | null;
};

const COUNTS: { state: string; label: string }[] = [
  { state: "linked", label: "analysed" },
  { state: "duplicate", label: "already in the archive" },
  { state: "skipped", label: "not documents" },
  { state: "failed", label: "could not be read" },
  { state: "missing", label: "missing" },
];

/** Folders on the NAS that DocuHive reads where they are (administrators). */
export function LinkedFolders() {
  const list = useApi<LinkedFolder[]>("/api/folders");
  const scanning = (list.data ?? []).some((f) => f.scanning);
  const { reload } = list;
  useEffect(() => {
    if (!scanning) return;
    const timer = setInterval(reload, 5000);
    return () => clearInterval(timer);
  }, [scanning, reload]);
  return (
    <Page narrow>
      <PageHeader
        title="Linked folders"
        description="Folders on your NAS that DocuHive reads and analyses where they are. Your files are never moved, renamed or changed; new files are picked up every few minutes."
      />
      <div className="space-y-4">
        {list.error ? (
          <ErrorBox error={list.error} onRetry={list.reload} />
        ) : list.loading && !list.data ? (
          <Skeleton rows={3} />
        ) : !list.data?.length ? (
          <Empty
            icon={FolderSync}
            text="No folders linked yet. Choose one below, for example the share with your scanned documents."
          />
        ) : (
          list.data.map((f) => (
            <LinkedCard key={f.id} folder={f} onChange={list.reload} />
          ))
        )}
        <AddFolder onAdded={list.reload} />
      </div>
    </Page>
  );
}

function LinkedCard({
  folder: f,
  onChange,
}: {
  folder: LinkedFolder;
  onChange: () => void;
}) {
  const [error, setError] = useState<ApiError | null>(null);
  const [showing, setShowing] = useState<string | null>(null);
  const files = useApi<FileRow[]>(
    showing ? `/api/folders/${f.id}/files?state=${showing}` : null,
  );
  async function run(work: () => Promise<unknown>) {
    setError(null);
    try {
      await work();
      onChange();
    } catch (e) {
      setError(e as ApiError);
    }
  }
  return (
    <Card
      title={f.label}
      actions={
        f.scanning ? (
          <Badge tone="info" icon={RefreshCw}>
            Reading files…
          </Badge>
        ) : f.last_scan_at ? (
          <Badge tone="ok">Read {formatDate(f.last_scan_at)}</Badge>
        ) : null
      }
    >
      <div className="space-y-3 text-sm">
        <p className="break-all text-text-muted">{f.path}</p>
        <p className="text-text-muted">
          Documents belong to {f.owner}
          {f.shared ? " and everyone in the household can see them" : ""}.
        </p>
        {f.last_error && (
          <p role="alert" className="flex items-center gap-2 text-danger">
            <TriangleAlert aria-hidden="true" className="size-4" />
            {f.last_error}
          </p>
        )}
        <ul className="flex flex-wrap gap-x-4 gap-y-1">
          {COUNTS.map(({ state, label }) => {
            const n = f.counts[state] ?? 0;
            if (!n && state !== "linked") return null;
            return (
              <li key={state}>
                {state === "linked" ? (
                  <span className="tabular">
                    {n} {label}
                  </span>
                ) : (
                  <button
                    type="button"
                    className="tabular underline"
                    aria-expanded={showing === state}
                    onClick={() => setShowing(showing === state ? null : state)}
                  >
                    {n} {label}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
        {showing &&
          (files.data ? (
            <ul className="max-h-56 space-y-1 overflow-auto rounded border border-border p-2 text-xs">
              {files.data.map((r) => (
                <li key={r.path} className="break-all">
                  {r.document_id ? (
                    <a
                      className="underline"
                      href={`/documents/${r.document_id}`}
                    >
                      {r.path}
                    </a>
                  ) : (
                    r.path
                  )}
                  {r.error && (
                    <span className="text-text-muted"> · {r.error}</span>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <Skeleton rows={2} />
          ))}
        {error && <ErrorBox error={error} />}
        <div className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            disabled={f.scanning}
            onClick={() =>
              void run(() =>
                api(`/api/folders/${f.id}/scan`, { method: "POST" }),
              )
            }
          >
            <RefreshCw aria-hidden="true" /> Read now
          </Button>
          <Button
            variant="ghost"
            onClick={() => {
              if (
                window.confirm(
                  `Stop following ${f.label}? Its documents stay in DocuHive, and the files stay where they are.`,
                )
              )
                void run(() =>
                  api(`/api/folders/${f.id}`, { method: "DELETE" }),
                );
            }}
          >
            <Unlink aria-hidden="true" /> Stop following
          </Button>
        </div>
      </div>
    </Card>
  );
}

function AddFolder({ onAdded }: { onAdded: () => void }) {
  const [path, setPath] = useState("");
  const listing = useApi<Listing>(
    `/api/system/storage/folders?path=${encodeURIComponent(path)}`,
  );
  const [label, setLabel] = useState("");
  const [shared, setShared] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const parts = path ? path.split("/") : [];
  async function add() {
    setBusy(true);
    setError(null);
    try {
      await api("/api/folders", {
        method: "POST",
        json: { path, label: label || parts[parts.length - 1], shared },
      });
      setPath("");
      setLabel("");
      setShared(false);
      onAdded();
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card title="Link a folder">
      <div className="space-y-4">
        {listing.error ? (
          <ErrorBox error={listing.error} />
        ) : !listing.data ? (
          <Skeleton rows={3} />
        ) : (
          <>
            <nav
              aria-label="Folder"
              className="flex flex-wrap items-center gap-1 text-sm"
            >
              <button
                type="button"
                className="underline"
                onClick={() => setPath("")}
              >
                {listing.data.root}
              </button>
              {parts.map((part, i) => (
                <span key={i} className="flex items-center gap-1">
                  <ChevronRight
                    aria-hidden="true"
                    className="size-4 text-text-muted"
                  />
                  <button
                    type="button"
                    className="underline"
                    onClick={() => setPath(parts.slice(0, i + 1).join("/"))}
                  >
                    {part}
                  </button>
                </span>
              ))}
            </nav>
            {listing.data.folders.length ? (
              <ul className="max-h-64 divide-y divide-border overflow-auto rounded border border-border">
                {listing.data.folders.map((f) => (
                  <li key={f.path}>
                    <button
                      type="button"
                      className="flex min-h-control w-full items-center gap-2 px-3 text-left hover:bg-surface-2"
                      onClick={() => setPath(f.path)}
                    >
                      <Folder
                        aria-hidden="true"
                        className="size-4 text-text-muted"
                      />
                      {f.name}
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-text-muted">
                No folders inside this one.
              </p>
            )}
          </>
        )}
        <label className="block space-y-1.5 text-sm font-medium">
          Name in DocuHive
          <Input
            value={label}
            maxLength={80}
            placeholder={parts[parts.length - 1] || "For example: Scans"}
            onChange={(e) => setLabel(e.target.value)}
          />
        </label>
        <label className="flex min-h-5 items-center gap-2 text-sm">
          <input
            type="checkbox"
            className={checkbox}
            checked={shared}
            onChange={(e) => setShared(e.target.checked)}
          />
          Everyone in the household can see these documents
        </label>
        {error && <ErrorBox error={error} />}
        <Button disabled={busy || !path} onClick={() => void add()}>
          <FolderSync aria-hidden="true" />
          {path ? `Link “${parts[parts.length - 1]}”` : "Open a folder above"}
        </Button>
      </div>
    </Card>
  );
}
