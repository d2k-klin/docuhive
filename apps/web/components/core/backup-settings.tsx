"use client";

import { useState } from "react";
import {
  CircleCheck,
  HardDriveDownload,
  LoaderCircle,
  TriangleAlert,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { checkbox } from "@/lib/ui/control";
import {
  api,
  ApiError,
  Badge,
  ErrorBox,
  Skeleton,
  useApi,
} from "@/components/intel/common";

type Options = {
  time: string;
  days: number[];
  keep: { daily: number; weekly: number; monthly: number; dumps: number };
  check_percent: number;
  include: { staging: boolean; plugins: boolean; linked_folders: boolean };
  updated_at?: string | null;
  updated_by?: string | null;
};
type Settings = {
  options: Options;
  status: {
    at: string | null;
    ok: boolean;
    last_success: string | null;
    stale: boolean;
    targets: { target: number; ok: boolean }[];
    included: string[];
    running_since: string | null;
    error: string | null;
  };
  request: { requested_at: string; by: string } | null;
  next_run: string | null;
  allowed_age_hours: number;
};

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const ERRORS: Record<string, string> = {
  backup_pause_failed: "DocuHive could not be paused for the backup.",
  backup_dump_failed: "The database could not be saved.",
  backup_backup_failed:
    "A backup target could not be written. Is the disk connected?",
  backup_restart_failed:
    "DocuHive did not start again after the backup. Check the server.",
};
const GUIDE =
  "https://github.com/d2k-klin/docuhive/blob/main/docs/setup/operations.md#nightly-backups";

function when(value: string | null | undefined): string {
  return value
    ? new Date(value).toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "—";
}

function included(item: string): string {
  if (item.startsWith("linked:")) return `${item.slice(7)} linked folders`;
  return (
    {
      vault: "documents",
      database: "database",
      staging: "files waiting to be read",
      plugins: "plugins",
    }[item] ?? item
  );
}

/** Storage health → Backup: what is backed up and when. Where to and the password stay on
 * the server (backup.env). */
export function BackupSettings() {
  const data = useApi<Settings>("/api/system/backup/options");
  const [draft, setDraft] = useState<Options | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [notice, setNotice] = useState("");
  if (data.error) return <ErrorBox error={data.error} onRetry={data.reload} />;
  if (!data.data) return <Skeleton rows={4} />;
  const s = data.data;
  const o = draft ?? s.options;
  const healthy = s.status.ok && !s.status.stale;
  const edit = (change: Partial<Options>) => setDraft({ ...o, ...change });

  async function run(work: () => Promise<Settings>, done: string) {
    setBusy(true);
    setError(null);
    setNotice("");
    try {
      data.setData(await work());
      setDraft(null);
      setNotice(done);
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setBusy(false);
    }
  }

  const number = (
    label: string,
    value: number,
    set: (n: number) => void,
    min: number,
    max: number,
    help?: string,
  ) => (
    <label className="block space-y-1.5 text-sm font-medium">
      {label}
      <Input
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(e) => set(Number(e.target.value))}
      />
      {help && (
        <span className="block text-xs font-normal text-text-muted">
          {help}
        </span>
      )}
    </label>
  );

  return (
    <section
      aria-label="Backups"
      className="space-y-4 rounded-card border border-border bg-surface p-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h2 className="flex items-center gap-2 text-md font-semibold">
            {healthy ? (
              <CircleCheck className="size-5 text-success" aria-hidden="true" />
            ) : (
              <TriangleAlert
                className="size-5 text-warning"
                aria-hidden="true"
              />
            )}
            Backups
          </h2>
          <p className="text-sm">
            {s.status.at === null
              ? "No backup has run yet. Set up the backup job on the server once; after that everything is chosen here."
              : healthy
                ? "Your latest backup completed."
                : (s.status.error && ERRORS[s.status.error]) ||
                  "A recent successful backup could not be confirmed."}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {s.status.running_since ? (
            <Badge tone="info" icon={LoaderCircle}>
              Running since {when(s.status.running_since)}
            </Badge>
          ) : s.request ? (
            <Badge tone="info">Starting: asked by {s.request.by}</Badge>
          ) : null}
          <Button
            variant="secondary"
            disabled={busy || Boolean(s.request || s.status.running_since)}
            onClick={() =>
              void run(
                () =>
                  api<Settings>("/api/system/backup/run", { method: "POST" }),
                "Asked the server to back up now. It starts within seconds, or at the next quarter hour.",
              )
            }
          >
            <HardDriveDownload aria-hidden="true" /> Back up now
          </Button>
        </div>
      </div>
      <dl className="grid gap-3 text-sm md:grid-cols-3">
        <div>
          <dt className="text-text-muted">Last successful backup</dt>
          <dd>{when(s.status.last_success)}</dd>
        </div>
        <div>
          <dt className="text-text-muted">Next backup</dt>
          <dd>{when(s.next_run)}</dd>
        </div>
        <div>
          <dt className="text-text-muted">Targets</dt>
          <dd className="flex flex-wrap gap-1">
            {s.status.targets.length
              ? s.status.targets.map((t) => (
                  <Badge key={t.target} tone={t.ok ? "ok" : "error"}>
                    Target {t.target}
                  </Badge>
                ))
              : "—"}
          </dd>
        </div>
        {s.status.included.length > 0 && (
          <div className="md:col-span-3">
            <dt className="text-text-muted">The last backup included</dt>
            <dd>{s.status.included.map(included).join(", ")}</dd>
          </div>
        )}
      </dl>
      <form
        className="space-y-4 border-t border-border pt-4"
        onSubmit={(e) => {
          e.preventDefault();
          void run(
            () =>
              api<Settings>("/api/system/backup/options", {
                method: "PUT",
                json: o,
              }),
            "Saved. The server follows it from the next check.",
          );
        }}
      >
        <h3 className="text-sm font-semibold">When</h3>
        <fieldset className="flex flex-wrap gap-x-4 gap-y-2">
          <legend className="sr-only">Days</legend>
          {DAYS.map((day, index) => (
            <label
              key={day}
              className="flex min-h-5 items-center gap-2 text-sm"
            >
              <input
                type="checkbox"
                className={checkbox}
                checked={o.days.includes(index)}
                onChange={(e) =>
                  edit({
                    days: e.target.checked
                      ? [...o.days, index].sort()
                      : o.days.filter((d) => d !== index),
                  })
                }
              />
              {day}
            </label>
          ))}
        </fieldset>
        <label className="block max-w-48 space-y-1.5 text-sm font-medium">
          Time (the server&apos;s clock)
          <Input
            type="time"
            required
            value={o.time}
            onChange={(e) => edit({ time: e.target.value })}
          />
        </label>
        <p className="text-xs text-text-muted">
          A backup that could not run (the server was off) runs at the next
          check. You are warned when the last success is older than{" "}
          {Math.round(s.allowed_age_hours / 24)} days.
        </p>
        <h3 className="text-sm font-semibold">What to include</h3>
        <p className="text-xs text-text-muted">
          Your documents and the database are always included.
        </p>
        {(
          [
            ["staging", "Files still waiting to be read"],
            [
              "plugins",
              "Installed plugins and your own files in their custom/ folders",
            ],
            [
              "linked_folders",
              "Files in linked folders (can be large; DocuHive's searchable copies are always included)",
            ],
          ] as const
        ).map(([key, label]) => (
          <label key={key} className="flex min-h-5 items-center gap-2 text-sm">
            <input
              type="checkbox"
              className={checkbox}
              checked={o.include[key]}
              onChange={(e) =>
                edit({ include: { ...o.include, [key]: e.target.checked } })
              }
            />
            {label}
          </label>
        ))}
        <h3 className="text-sm font-semibold">How long to keep</h3>
        <div className="grid gap-4 md:grid-cols-4">
          {number(
            "Daily backups",
            o.keep.daily,
            (n) => edit({ keep: { ...o.keep, daily: n } }),
            1,
            365,
          )}
          {number(
            "Weekly",
            o.keep.weekly,
            (n) => edit({ keep: { ...o.keep, weekly: n } }),
            0,
            520,
          )}
          {number(
            "Monthly",
            o.keep.monthly,
            (n) => edit({ keep: { ...o.keep, monthly: n } }),
            0,
            240,
          )}
          {number(
            "Database copies",
            o.keep.dumps,
            (n) => edit({ keep: { ...o.keep, dumps: n } }),
            1,
            365,
          )}
        </div>
        <div className="max-w-64">
          {number(
            "Verify stored data every 4 weeks (%)",
            o.check_percent,
            (n) => edit({ check_percent: n }),
            0,
            100,
            "Reads back this share of the backup to prove it can be restored. 0 switches it off.",
          )}
        </div>
        {error && <ErrorBox error={error} />}
        {notice && (
          <p role="status" className="text-sm text-text-muted">
            {notice}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" disabled={busy || !draft || !o.days.length}>
            Save
          </Button>
          {s.options.updated_by && (
            <span className="text-xs text-text-muted">
              Last changed by {s.options.updated_by},{" "}
              {when(s.options.updated_at)}
            </span>
          )}
        </div>
      </form>
      <p className="text-xs text-text-muted">
        Where backups go (a USB disk, a cloud bucket) and their password stay on
        the server, in backup.env, and are never shown here.{" "}
        <a
          href={GUIDE}
          className="text-primary underline"
          target="_blank"
          rel="noreferrer"
        >
          Set up the backup job
        </a>
      </p>
    </section>
  );
}
