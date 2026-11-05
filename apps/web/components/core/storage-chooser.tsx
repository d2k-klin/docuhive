"use client";

import { useState } from "react";
import { Folder, FolderPlus, ChevronRight } from "lucide-react";
import { browserClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge, useApi } from "@/components/intel/common";

type Listing = components["schemas"]["Listing"];
type Entry = components["schemas"]["Folder"];
const api = browserClient();

const states: Record<
  Entry["state"],
  { label: string; tone: "ok" | "warn" | "error" | "muted"; usable: boolean }
> = {
  empty: { label: "Empty", tone: "ok", usable: true },
  this_vault: { label: "This archive’s vault", tone: "ok", usable: true },
  other_vault: { label: "Another archive", tone: "error", usable: false },
  not_empty: { label: "Has other files", tone: "warn", usable: false },
  not_writable: { label: "Read-only", tone: "error", usable: false },
};

function message(error: unknown): string {
  const body = error as { error?: { message?: string } } | undefined;
  return body?.error?.message ?? "That did not work. Try again.";
}

export function StorageChooser({ onClose }: { onClose(): void }) {
  const [path, setPath] = useState("");
  const listingApi = useApi<Listing>(
    `/api/system/storage/folders?path=${encodeURIComponent(path)}`,
  );
  const listing = listingApi.data;
  const [picked, setPicked] = useState<Entry | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function open(where: string) {
    setError("");
    setPicked(null);
    setPath(where);
  }

  async function create() {
    setBusy(true);
    const { error } = await api.POST("/api/system/storage/folders", {
      body: { path, name },
    });
    setBusy(false);
    if (error) setError(message(error));
    else {
      setName("");
      listingApi.reload();
    }
  }

  async function choose() {
    if (!picked) return;
    setBusy(true);
    const { error } = await api.POST("/api/system/storage/choose", {
      body: { path: picked.path },
    });
    setBusy(false);
    if (error) setError(message(error));
    else window.location.reload();
  }

  const crumbs = path ? path.split("/") : [];
  return (
    <section
      aria-label="Choose storage"
      className="space-y-3 rounded-card border border-border bg-surface p-4"
    >
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-md font-semibold">Choose storage</h2>
        <Button variant="ghost" size="sm" onClick={onClose}>
          Close
        </Button>
      </div>
      <p className="text-sm text-text-muted">
        Pick a folder on a mounted share or disk. An empty folder becomes a new
        vault while your archive has no documents; your archive’s own vault can
        be picked again at a new place. Nothing is moved or deleted.
      </p>
      <nav
        aria-label="Folder path"
        className="flex flex-wrap items-center gap-1 text-sm"
      >
        <button
          className="font-mono text-primary underline"
          onClick={() => open("")}
        >
          {listing?.root ?? "Storage"}
        </button>
        {crumbs.map((part, i) => (
          <span key={i} className="flex items-center gap-1">
            <ChevronRight className="size-3" aria-hidden="true" />
            <button
              className="font-mono text-primary underline"
              onClick={() => open(crumbs.slice(0, i + 1).join("/"))}
            >
              {part}
            </button>
          </span>
        ))}
      </nav>
      {(error || listingApi.error) && (
        <p role="alert" className="text-sm text-danger">
          {error || listingApi.error?.message}
        </p>
      )}
      <ul className="divide-y divide-border rounded-card border border-border">
        {listing?.folders.length === 0 && (
          <li className="p-3 text-sm text-text-muted">No folders here.</li>
        )}
        {listing?.folders.map((f) => {
          const s = states[f.state];
          const current = listing.current === f.path;
          return (
            <li key={f.path} className="flex flex-wrap items-center gap-2 p-2">
              <button
                className="flex min-w-0 flex-1 items-center gap-2 text-left text-sm"
                onClick={() => open(f.path)}
              >
                <Folder className="size-4 shrink-0" aria-hidden="true" />
                <span className="truncate">{f.name}</span>
              </button>
              <Badge tone={current ? "info" : s.tone}>
                {current ? "In use" : s.label}
              </Badge>
              <Button
                size="sm"
                variant="secondary"
                disabled={!s.usable || current}
                onClick={() => setPicked(f)}
              >
                Use this folder
              </Button>
            </li>
          );
        })}
      </ul>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex-1 text-sm">
          <span className="mb-1 block">New folder here</span>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="docuhive"
          />
        </label>
        <Button
          variant="secondary"
          disabled={busy || !name.trim()}
          onClick={() => void create()}
        >
          <FolderPlus aria-hidden="true" /> Create
        </Button>
      </div>
      {picked && (
        <div
          role="alertdialog"
          className="space-y-2 rounded-card border border-warning p-3"
        >
          <p className="text-sm">
            {picked.state === "this_vault"
              ? `DocuHive will use your archive’s vault at “${picked.path}” from now on.`
              : `DocuHive will create a new, empty vault in “${picked.path}” and store all new documents there.`}{" "}
            Update the nightly backup to this folder too (installation guide,
            step 8).
          </p>
          <div className="flex gap-2">
            <Button disabled={busy} onClick={() => void choose()}>
              Switch storage
            </Button>
            <Button variant="ghost" onClick={() => setPicked(null)}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
