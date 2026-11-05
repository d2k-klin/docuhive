"use client";

import { useState } from "react";
import { CircleCheck, CircleDashed, TriangleAlert } from "lucide-react";
import { browserClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { Button } from "@/components/ui/button";

type Report = components["schemas"]["VaultReport"];
type Storage = components["schemas"]["StorageInfo"];
type Kind = components["schemas"]["VaultProblem"]["kind"];
const api = browserClient();
const problems: Record<Kind, string> = {
  vault_unavailable:
    "Storage is not reachable (check that the NAS is on and the share is mounted)",
  folder_missing: "The document’s folder is missing",
  original_missing: "The original file is missing",
  archive_missing: "The searchable PDF is missing",
  meta_missing: "The description file is missing",
  meta_invalid: "The description file can’t be read or belongs elsewhere",
  checksum_mismatch: "The original has changed since it was stored",
  orphan_folder: "A folder that no document points to",
};

const unavailable: Record<string, string> = {
  not_initialised:
    "No DocuHive vault was found here. Check that the share is mounted.",
  id_mismatch:
    "This folder holds a different vault from the one this archive belongs to.",
  not_writable: "DocuHive can’t write to this storage.",
};

function size(bytes: number): string {
  const gb = bytes / 1024 ** 3;
  return gb >= 1024
    ? `${(gb / 1024).toFixed(1)} TB`
    : `${gb.toFixed(gb >= 10 ? 0 : 1)} GB`;
}

export function VaultHealth({
  initial,
  backup,
  storage,
}: {
  initial: Report | null;
  backup?: components["schemas"]["BackupStatus"] | null;
  storage?: Storage | null;
}) {
  const [queued, setQueued] = useState(false);
  const [error, setError] = useState("");
  async function run(full: boolean) {
    setError("");
    const response = await api
      .POST("/api/system/vault/health", { params: { query: { full } } })
      .catch(() => null);
    if (!response?.response.ok) {
      setError("The check could not be started. Try again.");
      return;
    }
    setQueued(true);
  }
  return (
    <main className="mx-auto max-w-screen-xl space-y-6 p-4 md:p-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Storage health</h1>
          <p className="text-sm text-text-muted">
            Checks that every stored document is complete and unchanged. It
            never changes your files.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => void run(false)}>
            Quick check
          </Button>
          <Button onClick={() => void run(true)}>Full check</Button>
        </div>
      </header>
      {!storage ? (
        <section
          aria-label="Your storage"
          className="space-y-2 rounded-card border border-border bg-surface p-4"
        >
          <h2 className="flex items-center gap-2 text-md font-semibold">
            <TriangleAlert className="size-5 text-danger" aria-hidden="true" />
            Your storage
          </h2>
          <p className="text-sm">
            The storage details could not be loaded.{" "}
            <a href="/settings/storage" className="text-primary underline">
              Reload
            </a>
          </p>
        </section>
      ) : (
        <section
          aria-label="Your storage"
          className="space-y-2 rounded-card border border-border bg-surface p-4"
        >
          <h2 className="flex items-center gap-2 text-md font-semibold">
            {storage.available ? (
              <CircleCheck className="size-5 text-success" aria-hidden="true" />
            ) : (
              <TriangleAlert
                className="size-5 text-danger"
                aria-hidden="true"
              />
            )}
            Your storage
          </h2>
          {!storage.available && (
            <p className="text-sm text-danger">
              {unavailable[storage.reason ?? ""] ?? "Storage is unavailable."}
            </p>
          )}
          <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[max-content_1fr]">
            <dt className="text-text-muted">Location</dt>
            <dd className="break-all font-mono">{storage.location}</dd>
            {storage.kind && (
              <>
                <dt className="text-text-muted">Type</dt>
                <dd>
                  {storage.kind === "network"
                    ? "Network share (NAS)"
                    : "Local disk on this server"}
                </dd>
              </>
            )}
            <dt className="text-text-muted">Vault ID</dt>
            <dd className="break-all font-mono">
              {storage.vault_id ?? "None"}
            </dd>
            <dt className="text-text-muted">Documents</dt>
            <dd className="tabular">{storage.documents}</dd>
            {storage.free_bytes != null && storage.total_bytes != null && (
              <>
                <dt className="text-text-muted">Space</dt>
                <dd className="tabular">
                  {size(storage.free_bytes)} free of {size(storage.total_bytes)}
                </dd>
              </>
            )}
            {(storage.waiting > 0 || !storage.available) && (
              <>
                <dt className="text-text-muted">Waiting</dt>
                <dd>
                  {storage.waiting} uploads kept safe in local staging (
                  <span className="break-all font-mono">
                    {storage.staging_location}
                  </span>
                  ) until the storage accepts them
                </dd>
              </>
            )}
          </dl>
          <p className="text-xs text-text-muted">
            Storage is set when DocuHive is installed, not in the app. To move
            to another share, see the{" "}
            <a
              href="https://github.com/d2k-klin/docuhive/blob/main/docs/setup/installation.md#2-mount-the-vault"
              className="text-primary underline"
              target="_blank"
              rel="noreferrer"
            >
              installation guide
            </a>
            .
          </p>
        </section>
      )}
      <section
        aria-label="Backup status"
        className="space-y-2 rounded-card border border-border bg-surface p-4"
      >
        <h2 className="flex items-center gap-2 text-md font-semibold">
          {backup?.ok && !backup.stale ? (
            <CircleCheck className="size-5 text-success" aria-hidden="true" />
          ) : (
            <TriangleAlert className="size-5" aria-hidden="true" />
          )}
          Backups
        </h2>
        <p className="text-sm">
          {backup?.ok && !backup.stale
            ? "Your latest backup completed."
            : "A recent successful backup could not be confirmed. Check the nightly backup service."}
        </p>
        {backup?.last_success && (
          <p className="text-xs text-text-muted">
            Last successful backup:{" "}
            <time dateTime={backup.last_success}>
              {new Date(backup.last_success)
                .toISOString()
                .replace("T", " ")
                .replace("Z", " UTC")}
            </time>
          </p>
        )}
        <a
          href="https://github.com/d2k-klin/docuhive/blob/main/docs/setup/operations.md#nightly-backups"
          className="text-sm text-primary underline"
          target="_blank"
          rel="noreferrer"
        >
          Set up or check backups
        </a>
      </section>
      <p className="max-w-prose text-sm text-text-muted">
        A full check also reads every original to confirm it is unchanged, so it
        takes longer. It runs on its own once a week.
      </p>
      {queued && (
        <p role="status" className="flex items-center gap-2 text-sm">
          <CircleDashed className="size-4" aria-hidden="true" />
          The check is running in the background. Reload this page in a few
          minutes to see the result.
        </p>
      )}
      {error && (
        <p role="alert" className="flex items-center gap-2 text-sm text-danger">
          <TriangleAlert className="size-4" aria-hidden="true" />
          {error}
        </p>
      )}
      {!initial ? (
        <div className="space-y-2 rounded-card border border-border bg-surface p-4">
          <CircleDashed className="size-5" aria-hidden="true" />
          <h2 className="text-md font-semibold">Not checked yet</h2>
          <p className="text-sm text-text-muted">
            Run a full check to confirm your archive is intact.
          </p>
        </div>
      ) : (
        <section className="space-y-3 rounded-card border border-border bg-surface p-4">
          <h2 className="flex items-center gap-2 text-md font-semibold">
            {initial.problem_count ? (
              <TriangleAlert
                className="size-5 text-danger"
                aria-hidden="true"
              />
            ) : (
              <CircleCheck className="size-5 text-success" aria-hidden="true" />
            )}
            {initial.problem_count
              ? `${initial.problem_count} ${initial.problem_count === 1 ? "problem" : "problems"} found`
              : "Everything is in place"}
          </h2>
          <p className="text-sm text-text-muted tabular">
            {initial.full ? "Full check" : "Quick check"} of {initial.documents}{" "}
            documents, {new Date(initial.checked_at).toLocaleString()}.
          </p>
          {initial.problems.length > 0 && (
            <ul className="space-y-2 text-sm">
              {initial.problems.map((p, index) => (
                <li key={index} className="break-words">
                  {problems[p.kind]}:{" "}
                  <code className="text-xs text-text-muted">{p.path}</code>
                </li>
              ))}
            </ul>
          )}
          {initial.problem_count > initial.problems.length && (
            <p className="text-xs text-text-muted">
              Showing the first {initial.problems.length}. Run{" "}
              <code>docuhive vault check --full</code> on the server for the
              complete list.
            </p>
          )}
        </section>
      )}
    </main>
  );
}
